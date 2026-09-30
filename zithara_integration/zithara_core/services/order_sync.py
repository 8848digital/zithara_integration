# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""
Decide which invoice events go to Zithara and queue them as Zithara Sync Logs.
Nothing here calls Zithara; the queued log is sent by a background job, so a
Zithara problem never blocks a sale.
"""

import frappe
from frappe import _

from zithara_integration.zithara_core.services.cancel_payload import cancel_payload
from zithara_integration.zithara_core.services.payments import is_fully_paid
from zithara_integration.zithara_core.services.store_resolver import resolve_store

CREATE = "Create Order"
CANCEL = "Cancel Order"
# Logs in these states mean the order already reached (or is on its way to) Zithara.
SENT_STATES = ("Queued", "Success", "Duplicate")
INVOICE_TOGGLES = {"Sales Invoice": "sync_sales_invoice", "POS Invoice": "sync_pos_invoice"}


class OrderSync:
	"""Turns invoice / payment events into queued Zithara Sync Logs."""

	def __init__(self):
		"""
		Load the settings once per event.

		Returns:
		        None
		"""
		self.settings = frappe.get_cached_doc("Zithara Settings")

	def on_invoice_submit(self, invoice) -> None:
		"""
		A sale is sent once fully paid (later payments are caught by
		on_payment_submit); a return cancels the original order.

		Parameters:
		        invoice (Document, required): Submitted Sales Invoice / POS Invoice.

		Returns:
		        None
		"""
		if not self.__applies_to(invoice):
			return
		if invoice.is_return:
			self.__queue_return(invoice)
		elif is_fully_paid(invoice):
			self.__queue_create(invoice)

	def on_invoice_cancel(self, invoice) -> None:
		"""
		Cancelling a sale that reached Zithara cancels the whole order there.

		Parameters:
		        invoice (Document, required): Cancelled Sales Invoice / POS Invoice.

		Returns:
		        None
		"""
		store = None if invoice.is_return else self.__sent_store(invoice)
		if not store:
			return
		body = {"platform_order_id": invoice.name, "type": "complete"}
		queue_log(invoice, CANCEL, store, body)

	def on_payment_submit(self, payment) -> None:
		"""
		A payment can be the one that settles an unpaid invoice: send it now.

		Parameters:
		        payment (Document, required): Submitted Payment Entry or Journal Entry.

		Returns:
		        None
		"""
		if not self.settings.enabled:
			return
		for doctype, name in paid_invoices(payment):
			invoice = frappe.get_doc(doctype, name)
			if invoice.docstatus == 1 and not invoice.is_return and self.__applies_to(invoice):
				if is_fully_paid(invoice):
					self.__queue_create(invoice)

	def __applies_to(self, invoice) -> bool:
		"""
		Integration on, invoice type enabled, not a consolidated POS summary
		(its POS Invoices were already sent), and not a skipped customer.

		Parameters:
		        invoice (Document, required): Sales Invoice / POS Invoice.

		Returns:
		        bool: Whether the invoice should be synced.
		"""
		settings = self.settings
		if not (settings.enabled and settings.get(INVOICE_TOGGLES.get(invoice.doctype, ""))):
			return False
		if invoice.get("is_consolidated"):
			return False
		skipped = {row.customer for row in settings.skip_customers or []}
		return invoice.customer not in skipped

	def __queue_create(self, invoice) -> None:
		"""
		Queue a Create Order unless one was already sent for this invoice.

		Parameters:
		        invoice (Document, required): Fully paid invoice.

		Returns:
		        None
		"""
		if self.__was_sent(invoice, CREATE):
			return
		queue_log(invoice, CREATE, resolve_store(invoice))

	def __queue_return(self, invoice) -> None:
		"""
		Queue a Cancel Order for the original sale of a return.

		Parameters:
		        invoice (Document, required): Submitted return invoice.

		Returns:
		        None
		"""
		original = frappe._dict(doctype=invoice.doctype, name=invoice.return_against)
		store = self.__sent_store(original)
		body = cancel_payload(invoice)
		# Nothing to cancel on Zithara if the original sale never reached it.
		if body and store:
			queue_log(invoice, CANCEL, store, body)

	def __sent_store(self, invoice) -> str | None:
		"""
		Store an invoice's order was sent with, when it reached Zithara.

		Parameters:
		        invoice (Document | dict, required): Invoice (doctype and name).

		Returns:
		        str | None: Zithara Store name, or None when never sent.
		"""
		return frappe.db.get_value(
			"Zithara Sync Log",
			{
				"reference_doctype": invoice.doctype,
				"reference_name": invoice.name,
				"action": CREATE,
				"status": ("in", SENT_STATES),
			},
			"store",
		)

	def __was_sent(self, invoice, action: str) -> bool:
		"""
		True when a log for this invoice and action is queued or succeeded.

		Parameters:
		        invoice (Document, required): Invoice.
		        action (str, required): CREATE or CANCEL.

		Returns:
		        bool: Whether it was already sent.
		"""
		return bool(
			frappe.db.exists(
				"Zithara Sync Log",
				{
					"reference_doctype": invoice.doctype,
					"reference_name": invoice.name,
					"action": action,
					"status": ("in", SENT_STATES),
				},
			)
		)


def paid_invoices(payment) -> list[tuple[str, str]]:
	"""
	Invoices a Payment Entry (references) or Journal Entry (accounts) pays.

	Parameters:
	        payment (Document, required): Payment Entry or Journal Entry.

	Returns:
	        list[tuple[str, str]]: Distinct (invoice doctype, invoice name) pairs.
	"""
	if payment.doctype == "Journal Entry":
		pairs = [(row.reference_type, row.reference_name) for row in payment.get("accounts") or []]
	else:
		pairs = [(row.reference_doctype, row.reference_name) for row in payment.get("references") or []]
	return list(dict.fromkeys(pair for pair in pairs if pair[0] in INVOICE_TOGGLES and pair[1]))


def queue_log(invoice, action: str, store: str | None, body: dict | None = None) -> str:
	"""
	Create a Zithara Sync Log and send it in the background after the commit.
	Without an active store the log is kept as Skipped, so the gap is visible.

	Parameters:
	        invoice (Document, required): Source invoice.
	        action (str, required): CREATE or CANCEL.
	        store (str, optional): Zithara Store to send as.
	        body (dict, optional): Request body (Create Order bodies are built when sent).

	Returns:
	        str: Zithara Sync Log name.
	"""
	log = frappe.get_doc(
		{
			"doctype": "Zithara Sync Log",
			"reference_doctype": invoice.doctype,
			"reference_name": invoice.name,
			"action": action,
			"store": store,
			"platform_order_id": (body or {}).get("platform_order_id") or invoice.name,
			"status": "Queued" if store else "Skipped",
			"request_payload": frappe.as_json(body) if body else None,
			"error": None if store else _("No active Zithara Store for this invoice"),
		}
	).insert(ignore_permissions=True)

	if store:
		enqueue_log(log.name)
	return log.name


def enqueue_log(log_name: str) -> None:
	"""
	Send a Zithara Sync Log in a background job once the transaction commits.

	Parameters:
	        log_name (str, required): Zithara Sync Log name.

	Returns:
	        None
	"""
	frappe.enqueue(
		"zithara_integration.zithara_core.tasks.send_sync_log",
		log_name=log_name,
		queue="short",
		enqueue_after_commit=True,
	)
