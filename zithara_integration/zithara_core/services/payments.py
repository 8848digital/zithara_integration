# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""
Payments of an invoice, as Zithara transactions. Zithara silently drops an order
sent without transactions, so orders are only sent once the invoice is paid.
"""

import frappe
from frappe.utils import flt

# Sub-rupee rounding between payments and the invoice total is ignored.
PAID_TOLERANCE = 1.0


def is_fully_paid(invoice) -> bool:
	"""
	True when nothing is left to pay on the invoice.

	Parameters:
	        invoice (Document, required): Sales Invoice / POS Invoice.

	Returns:
	        bool: Whether the invoice is fully paid.
	"""
	return flt(invoice.outstanding_amount) <= PAID_TOLERANCE


def invoice_transactions(invoice, created_at: str) -> list[dict]:
	"""
	One Zithara transaction per payment: POS payment rows, allocated advances
	and Payment Entries against the invoice.

	Parameters:
	        invoice (Document, required): Sales Invoice / POS Invoice.
	        created_at (str, required): Naive local datetime used for every row.

	Returns:
	        list[dict]: Zithara transactions (at least one).
	"""
	payments = __pos_payments(invoice) + __advances(invoice) + __payment_entries(invoice)
	if not payments:
		# Paid without a payment row (e.g. settled by a credit note): Zithara still
		# needs one transaction, so the invoice total is reported as adjusted.
		payments = [
			{"mode": "Adjusted", "amount": invoice.rounded_total or invoice.grand_total, "ref": ""}
		]

	return [
		{
			"status": "paid",
			"transaction_mode": payment["mode"],
			"transaction_final_amount": round(flt(payment["amount"]), 2),
			"transaction_original_amount": round(flt(payment["amount"]), 2),
			"platform_transaction_id": payment["ref"] or f"{invoice.name}#{index}",
			"created_at": created_at,
			"financial_status": "",
			"transaction_type": "",
			"custom_attributes": {"transaction_ref_id": payment["ref"]},
		}
		for index, payment in enumerate(payments, start=1)
	]


def __pos_payments(invoice) -> list[dict]:
	"""
	POS payment rows, minus the change handed back (taken from the cash row).

	Parameters:
	        invoice (Document, required): Invoice with a `payments` table.

	Returns:
	        list[dict]: {"mode", "amount", "ref"} per paid row.
	"""
	rows = [row for row in invoice.get("payments") or [] if flt(row.amount) > 0]
	payments = [{"mode": row.mode_of_payment, "amount": flt(row.amount), "ref": ""} for row in rows]

	change = flt(invoice.get("change_amount"))
	if change and payments:
		cash_index = next(
			(index for index, row in enumerate(rows) if row.get("type") == "Cash"), len(payments) - 1
		)
		payments[cash_index]["amount"] -= change
	return payments


def __advances(invoice) -> list[dict]:
	"""
	Advance payments allocated on the invoice.

	Parameters:
	        invoice (Document, required): Invoice with an `advances` table.

	Returns:
	        list[dict]: {"mode", "amount", "ref"} per allocated advance.
	"""
	return [
		{
			"mode": __payment_entry_mode(row.reference_name)
			if row.reference_type == "Payment Entry"
			else "Advance",
			"amount": flt(row.allocated_amount),
			"ref": row.reference_name or "",
		}
		for row in invoice.get("advances") or []
		if flt(row.allocated_amount) > 0
	]


def __payment_entries(invoice) -> list[dict]:
	"""
	Submitted Payment Entries allocated to the invoice after it was created.

	Parameters:
	        invoice (Document, required): Sales Invoice / POS Invoice.

	Returns:
	        list[dict]: {"mode", "amount", "ref"} per Payment Entry.
	"""
	advance_refs = {row.reference_name for row in invoice.get("advances") or []}
	entry = frappe.qb.DocType("Payment Entry")
	reference = frappe.qb.DocType("Payment Entry Reference")
	rows = (
		frappe.qb.from_(reference)
		.join(entry)
		.on(entry.name == reference.parent)
		.select(entry.name, entry.mode_of_payment, reference.allocated_amount)
		.where(
			(reference.reference_doctype == invoice.doctype)
			& (reference.reference_name == invoice.name)
			& (entry.docstatus == 1)
		)
		.orderby(entry.posting_date)
		.run(as_dict=True)
	)
	return [
		{"mode": row.mode_of_payment or "Payment Entry", "amount": row.allocated_amount, "ref": row.name}
		for row in rows
		if row.name not in advance_refs and flt(row.allocated_amount) > 0
	]


def __payment_entry_mode(payment_entry: str) -> str:
	"""
	Mode of payment of a Payment Entry.

	Parameters:
	        payment_entry (str, required): Payment Entry name.

	Returns:
	        str: Mode of payment, or "Advance" when unset.
	"""
	return frappe.db.get_value("Payment Entry", payment_entry, "mode_of_payment") or "Advance"
