# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""ERPNext test documents: customers, items, invoices and payments."""

import frappe
from frappe.utils import nowdate

CUSTOMER = "_Zithara Test Customer"
WALK_IN = "_Zithara Walk-In"
ITEMS = ("_ZT Ring", "_ZT Chain")


def ensure_masters() -> None:
	"""
	Test customers (one with a mobile number) and non-stock items.

	Returns:
	        None
	"""
	for name, mobile in ((CUSTOMER, "098765 43210"), (WALK_IN, "")):
		if not frappe.db.exists("Customer", name):
			frappe.get_doc(
				{"doctype": "Customer", "customer_name": name, "mobile_no": mobile, "gender": "Female"}
			).insert()
	for item_code in ITEMS:
		if not frappe.db.exists("Item", item_code):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": item_code,
					"item_name": item_code,
					"item_group": "All Item Groups",
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			).insert()


def make_invoice(customer: str = CUSTOMER, submit: bool = True, **values):
	"""
	Create an unpaid Sales Invoice for two service items.

	Parameters:
	        customer (str, optional): Customer name.
	        submit (bool, optional): Submit it.
	        **values: Sales Invoice field overrides.

	Returns:
	        Document: The Sales Invoice.
	"""
	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": customer,
			"company": _company(),
			"posting_date": nowdate(),
			"due_date": nowdate(),
			"items": [
				{"item_code": ITEMS[0], "qty": 1, "rate": 1000, "price_list_rate": 1200},
				{"item_code": ITEMS[1], "qty": 2, "rate": 500},
			],
			**values,
		}
	)
	invoice.insert()
	if submit:
		invoice.submit()
	return invoice


def pay_invoice(invoice):
	"""
	Pay an invoice in full with a Payment Entry.

	Parameters:
	        invoice (Document, required): Submitted Sales Invoice.

	Returns:
	        Document: Submitted Payment Entry.
	"""
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	entry = get_payment_entry("Sales Invoice", invoice.name)
	entry.reference_no = "UTR-001"
	entry.reference_date = nowdate()
	entry.insert()
	entry.submit()
	return entry


def sync_logs(invoice, action: str | None = None) -> list:
	"""
	Zithara Sync Logs of an invoice, oldest first.

	Parameters:
	        invoice (Document, required): Invoice.
	        action (str, optional): Only this action.

	Returns:
	        list: Log documents.
	"""
	filters = {"reference_doctype": invoice.doctype, "reference_name": invoice.name}
	if action:
		filters["action"] = action
	names = frappe.get_all("Zithara Sync Log", filters=filters, pluck="name", order_by="creation asc")
	return [frappe.get_doc("Zithara Sync Log", name) for name in names]


def _company() -> str:
	"""
	The site's default company (set by the setup wizard).

	Returns:
	        str: Company name.
	"""
	return frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name")[0]
