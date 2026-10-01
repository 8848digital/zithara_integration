# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Build the Zithara Create Order body from a Sales Invoice or POS Invoice."""

import frappe
from frappe.utils import flt, get_datetime, get_system_timezone

from zithara_integration.zithara_core.services.payments import invoice_transactions
from zithara_integration.zithara_core.services.redemption_invoice import redemption_attributes
from zithara_integration.zithara_core.services.value_format import (
	money,
	normalize_phone,
	product_id,
)


class OrderPayload:
	"""Zithara Create Order body for one submitted invoice."""

	def __init__(self, invoice):
		"""
		Keep the invoice and the settings that shape the payload.

		Parameters:
		        invoice (Document, required): Submitted Sales Invoice / POS Invoice.

		Returns:
		        None
		"""
		self.invoice = invoice
		self.settings = frappe.get_cached_doc("Zithara Settings")

	def build(self) -> dict:
		"""
		Compose the full Create Order body. Redemption fields stay at their
		"no redemption" defaults.

		Returns:
		        dict: Create Order body.
		"""
		created_at = self.__created_at()
		return {
			"customer": self.__customer(),
			"order_line_item": [self.__line(row) for row in self.invoice.items],
			"order": self.__order(created_at),
			"transactions": invoice_transactions(self.invoice, created_at),
			"visit": {},
			"createVisit": False,
			"validateOTP": False,
			"points": 0,
			"otp": "",
			"sessionId": "",
			"timezone": get_system_timezone(),
		}

	def __customer(self) -> dict:
		"""
		Customer block: ERPNext customer id as Zithara's platform customer id.

		Returns:
		        dict: Zithara customer block.
		"""
		customer = frappe.get_cached_doc("Customer", self.invoice.customer)
		full_name = (customer.customer_name or self.invoice.customer_name or "").strip()
		first_name, _space, last_name = full_name.partition(" ")
		phone = normalize_phone(
			self.invoice.get("contact_mobile") or customer.get("mobile_no"),
			self.settings.phone_country_code,
		)
		return {
			"platform_customer_id": customer.name,
			"phone_number": phone,
			"whatsapp_phone_number": phone,
			"first_name": first_name,
			"last_name": last_name.strip(),
			"name": full_name,
			"email": self.invoice.get("contact_email") or customer.get("email_id") or "",
			"custom_attributes": {
				"gender": _field_text(customer, self.settings.gender_field),
				"date_of_birth": _field_text(customer, self.settings.date_of_birth_field),
			},
		}

	def __line(self, row) -> dict:
		"""
		One line item. The row name is globally unique, as Zithara requires for
		platform_line_item_id.

		Parameters:
		        row (Document, required): Invoice item row.

		Returns:
		        dict: Zithara line item.
		"""
		list_price = flt(row.price_list_rate) or flt(row.rate)
		discount = max(list_price - flt(row.rate), 0) * flt(row.qty)
		return {
			"status": "",
			"platform_line_item_id": row.name,
			"price": money(list_price),
			"taxable": True,
			"discount_amount": money(discount),
			"name": row.item_name,
			"product_name": row.item_name,
			"sku": row.item_code,
			"product_id": product_id(row.item_code),
			"gift_card": False,
			"quantity": flt(row.qty),
			"custom_attributes": {},
		}

	def __order(self, created_at: str) -> dict:
		"""
		Order header with totals. Subtotal = total - tax, as in the reference.

		Parameters:
		        created_at (str, required): Naive local datetime "YYYY-MM-DD HH:MM:SS".

		Returns:
		        dict: Zithara order block.
		"""
		invoice = self.invoice
		total = money(invoice.rounded_total or invoice.grand_total)
		tax = money(invoice.total_taxes_and_charges)
		line_discounts = sum(
			max(flt(row.price_list_rate) - flt(row.rate), 0) * flt(row.qty) for row in invoice.items
		)
		return {
			"visit_id": None,
			"status": "paid",
			"current_total_price": total,
			"current_subtotal_price": money(total - tax),
			"current_total_discounts": money(flt(invoice.discount_amount) + line_discounts),
			"current_total_tax": tax,
			"currency": invoice.currency,
			"platform_order_id": invoice.name,
			"name": invoice.name,
			"created_at": created_at,
			"billing_address": {},
			"shipping_address": {},
			"payment_status": "",
			"fulfillment_status": "",
			"invoice_url": "",
			"note": False,
			"custom_attributes": {"pos_reference": invoice.name, **redemption_attributes(invoice)},
		}

	def __created_at(self) -> str:
		"""
		Posting date and time as a naive local datetime (Zithara takes the
		timezone separately).

		Returns:
		        str: "YYYY-MM-DD HH:MM:SS".
		"""
		posted = get_datetime(f"{self.invoice.posting_date} {self.invoice.posting_time or '00:00:00'}")
		return posted.strftime("%Y-%m-%d %H:%M:%S")


def _field_text(doc, fieldname: str | None) -> str:
	"""
	Read an optional, configurable field as text ("" when unset or missing).

	Parameters:
	        doc (Document, required): Source document.
	        fieldname (str, optional): Field to read.

	Returns:
	        str: Field value as text.
	"""
	if not fieldname:
		return ""
	value = doc.get(fieldname)
	return str(value) if value else ""
