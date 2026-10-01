# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Redeemed points on the invoice: the discount, and guards that keep it intact."""

import frappe
from frappe import _
from frappe.utils import flt

from zithara_integration.zithara_core.services.value_format import money


def apply_redemption(invoice, redemption) -> None:
	"""
	Add the redeemed value to the invoice's additional discount and link the
	redemption. A percentage discount is frozen to its amount first, otherwise
	ERPNext would recompute the amount from the percentage and drop ours.

	Parameters:
	        invoice (Document, required): Draft Sales Invoice / POS Invoice.
	        redemption (Document, required): Zithara Redemption in status Redeemed.

	Returns:
	        None
	"""
	amount = min(flt(redemption.amount), flt(invoice.grand_total))
	if flt(redemption.amount) - amount > 0.01:
		# Only possible when Zithara sent no redeem rule to check against up front.
		redemption.db_set(
			"error",
			_("Only {0} of the redeemed {1} fit in the invoice; the rest was not applied").format(
				amount, flt(redemption.amount)
			),
		)
	invoice.additional_discount_percentage = 0
	invoice.discount_amount = flt(invoice.discount_amount) + amount
	invoice.zithara_redemption = redemption.name
	invoice.zithara_redeemed_points = redemption.points
	invoice.zithara_redeemed_amount = amount
	invoice.save(ignore_permissions=True)


def validate_redemption(invoice) -> None:
	"""
	Once points are redeemed (they are gone on Zithara), the customer and the
	points discount must stay as they were.

	Parameters:
	        invoice (Document, required): Sales Invoice / POS Invoice being saved.

	Returns:
	        None
	"""
	if invoice.is_return or not invoice.get("zithara_redemption"):
		return
	redemption = frappe.db.get_value(
		"Zithara Redemption", invoice.zithara_redemption, ["customer", "status"], as_dict=True
	)
	if not redemption or redemption.status != "Redeemed":
		frappe.throw(_("Zithara Redemption {0} is not redeemed").format(invoice.zithara_redemption))
	if redemption.customer != invoice.customer:
		frappe.throw(
			_("Points were redeemed for {0}; the customer can't be changed").format(redemption.customer)
		)
	if flt(invoice.discount_amount) + 0.01 < flt(invoice.zithara_redeemed_amount):
		frappe.throw(
			_(
				"The additional discount includes {0} of redeemed Zithara points and can't go below it"
			).format(frappe.format(invoice.zithara_redeemed_amount, {"fieldtype": "Currency"}))
		)


def block_delete(invoice) -> None:
	"""
	A draft holding redeemed points can't be deleted: the points are already
	spent on Zithara and there is no API to give them back.

	Parameters:
	        invoice (Document, required): Sales Invoice / POS Invoice being deleted.

	Returns:
	        None
	"""
	if invoice.get("zithara_redemption"):
		frappe.throw(
			_("This invoice holds redeemed Zithara points ({0}). Submit it instead of deleting it.").format(
				invoice.zithara_redemption
			)
		)


def redemption_attributes(invoice) -> dict:
	"""
	Redemption details added to the order's custom_attributes (same keys the
	previous backend reserved), so Zithara sees which orders used points.

	Parameters:
	        invoice (Document, required): Sales Invoice / POS Invoice.

	Returns:
	        dict: Extra custom_attributes; empty when no points were redeemed.
	"""
	if not invoice.get("zithara_redemption"):
		return {}
	return {
		"cashback_redeemption_order": True,
		"cashback_redeemption_amount": money(invoice.zithara_redeemed_amount),
		"redeemed_points": invoice.zithara_redeemed_points,
	}
