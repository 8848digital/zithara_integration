# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""doc_events for Sales Invoice: send paid sales and returns to Zithara, guard redeemed points."""

from zithara_integration.zithara_core.services.order_sync import OrderSync
from zithara_integration.zithara_core.services.redemption_invoice import (
	block_delete,
	validate_redemption,
)


def on_submit(doc, method=None):
	"""
	Queue the Zithara order (fully paid sale) or cancellation (return).

	Parameters:
	        doc (Document, required): The submitted Sales Invoice.
	        method (str, optional): Hook event name passed by Frappe.

	Returns:
	        None
	"""
	OrderSync().on_invoice_submit(doc)


def on_cancel(doc, method=None):
	"""
	Queue a full cancellation on Zithara for a cancelled sale.

	Parameters:
	        doc (Document, required): The cancelled Sales Invoice.
	        method (str, optional): Hook event name passed by Frappe.

	Returns:
	        None
	"""
	OrderSync().on_invoice_cancel(doc)


def validate(doc, method=None):
	"""
	Keep redeemed Zithara points (customer and discount) intact.

	Parameters:
	        doc (Document, required): The Sales Invoice being saved.
	        method (str, optional): Hook event name passed by Frappe.

	Returns:
	        None
	"""
	validate_redemption(doc)


def on_trash(doc, method=None):
	"""
	Refuse to delete a draft whose Zithara points are already redeemed.

	Parameters:
	        doc (Document, required): The Sales Invoice being deleted.
	        method (str, optional): Hook event name passed by Frappe.

	Returns:
	        None
	"""
	block_delete(doc)
