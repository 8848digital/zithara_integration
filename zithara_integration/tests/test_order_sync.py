# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Invoices and payments become Zithara orders; returns and cancellations cancel them."""

from unittest.mock import patch

from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

import frappe
from frappe.tests import IntegrationTestCase

from zithara_integration.tests.erpnext_fixtures import (
	WALK_IN,
	make_invoice,
	pay_invoice,
	sync_logs,
)
from zithara_integration.tests.zithara_fixtures import (
	CLIENT,
	STORE,
	run_jobs_inline,
	setup_zithara,
	token_reply,
	zithara_reply,
)
from zithara_integration.zithara_core.services.order_sync import OrderSync
from zithara_integration.zithara_core.services.store_resolver import resolve_store
from zithara_integration.zithara_core.tasks import retry_failed_syncs

CREATED = {"status": 201, "message": "order created", "orderId": "702355"}
CANCELLED = {"success": True, "message": "order cancelled"}


class TestOrderSync(IntegrationTestCase):
	"""End-to-end: ERPNext documents -> queued logs -> (mocked) Zithara calls."""

	def setUp(self):
		"""
		Enable Zithara, run jobs inline and mock Zithara's HTTP API.

		Returns:
		        None
		"""
		setup_zithara()
		self.jobs = run_jobs_inline()
		self.token = patch(f"{CLIENT}.get", return_value=token_reply()).start()
		self.api = patch(f"{CLIENT}.request", side_effect=self.__zithara).start()
		self.replies = []

	def tearDown(self):
		"""
		Stop all patches.

		Returns:
		        None
		"""
		patch.stopall()

	def test_order_sent_once_invoice_is_paid(self):
		"""An unpaid invoice waits; the settling payment sends the full order."""
		invoice = make_invoice()
		self.assertEqual(sync_logs(invoice), [])

		entry = pay_invoice(invoice)
		[log] = sync_logs(invoice)
		self.assertEqual((log.action, log.status, log.store), ("Create Order", "Success", STORE))
		self.assertEqual(log.zithara_order_id, "702355")

		body = self.api.call_args.kwargs["json"]
		self.assertEqual(body["order"]["platform_order_id"], invoice.name)
		self.assertEqual(body["customer"]["phone_number"], "919876543210")
		self.assertEqual(body["customer"]["custom_attributes"]["gender"], "Female")
		self.assertEqual(
			[line["platform_line_item_id"] for line in body["order_line_item"]],
			[row.name for row in invoice.items],
		)
		self.assertEqual(body["order_line_item"][0]["discount_amount"], 200)
		self.assertEqual(body["transactions"][0]["platform_transaction_id"], entry.name)
		self.assertEqual(body["transactions"][0]["transaction_final_amount"], invoice.grand_total)
		self.assertEqual(self.api.call_args.kwargs["headers"]["Authorization"], "token-123")

	def test_order_not_sent_twice(self):
		"""A second event for an already-sent invoice does not queue another order."""
		invoice = make_invoice()
		entry = pay_invoice(invoice)
		OrderSync().on_payment_submit(entry)
		self.assertEqual(len(sync_logs(invoice)), 1)

	def test_skipped_customer_not_sent(self):
		"""Invoices of skipped customers (e.g. walk-in) never reach Zithara."""
		invoice = make_invoice(customer=WALK_IN)
		pay_invoice(invoice)
		self.assertEqual(sync_logs(invoice), [])

	def test_invoice_without_store_is_logged_as_skipped(self):
		"""No active store: nothing is sent, but the gap is visible in the log."""
		setup_zithara(default_store=None)
		invoice = make_invoice()
		pay_invoice(invoice)
		[log] = sync_logs(invoice)
		self.assertEqual(log.status, "Skipped")
		self.api.assert_not_called()

	def test_partial_return_cancels_returned_lines(self):
		"""Returning one of two lines cancels just that line on Zithara."""
		invoice = make_invoice()
		pay_invoice(invoice)
		credit_note = make_sales_return(invoice.name)
		credit_note.items = credit_note.items[:1]
		credit_note.insert()
		credit_note.submit()

		[log] = sync_logs(credit_note, "Cancel Order")
		self.assertEqual(log.status, "Success")
		body = frappe.parse_json(log.request_payload)
		self.assertEqual(body["type"], "partial")
		self.assertEqual(body["platform_order_id"], invoice.name)
		self.assertEqual(body["platform_line_item_ids"], [invoice.items[0].name])

	def test_full_return_cancels_whole_order(self):
		"""Returning every line cancels the whole order."""
		invoice = make_invoice()
		pay_invoice(invoice)
		credit_note = make_sales_return(invoice.name)
		credit_note.insert()
		credit_note.submit()

		[log] = sync_logs(credit_note, "Cancel Order")
		self.assertEqual(frappe.parse_json(log.request_payload)["type"], "complete")

	def test_return_of_unsent_sale_is_ignored(self):
		"""A return against a sale Zithara never received has nothing to cancel."""
		invoice = make_invoice()
		credit_note = make_sales_return(invoice.name)
		credit_note.insert()
		credit_note.submit()
		self.assertEqual(sync_logs(credit_note), [])

	def test_cancelled_invoice_cancels_order(self):
		"""Cancelling a sale that reached Zithara cancels the order there."""
		invoice = make_invoice()
		pay_invoice(invoice)
		OrderSync().on_invoice_cancel(invoice)

		[log] = sync_logs(invoice, "Cancel Order")
		self.assertEqual(log.status, "Success")
		self.assertEqual(
			frappe.parse_json(log.request_payload), {"platform_order_id": invoice.name, "type": "complete"}
		)

	def test_duplicate_order_counts_as_done(self):
		"""Zithara's 409 (order already exists) is treated as success."""
		self.replies = [zithara_reply(409, {"success": False, "message": "duplicate"})]
		invoice = make_invoice()
		pay_invoice(invoice)
		self.assertEqual(sync_logs(invoice)[0].status, "Duplicate")

	def test_server_error_is_retried_by_scheduler(self):
		"""A 5xx failure is retryable and the hourly job sends it again."""
		self.replies = [zithara_reply(503, {"message": "down"})]
		invoice = make_invoice()
		pay_invoice(invoice)
		log = sync_logs(invoice)[0]
		self.assertEqual((log.status, log.retryable, log.attempts), ("Failed", 1, 1))

		retry_failed_syncs()
		log.reload()
		self.assertEqual((log.status, log.attempts), ("Success", 2))

	def test_rejected_order_is_not_retried(self):
		"""A 4xx rejection needs a fix, so the scheduler leaves it alone."""
		self.replies = [zithara_reply(400, {"message": "bad phone"})]
		invoice = make_invoice()
		pay_invoice(invoice)
		retry_failed_syncs()
		log = sync_logs(invoice)[0]
		self.assertEqual((log.status, log.retryable, log.attempts), ("Failed", 0, 1))
		self.assertIn("bad phone", log.error)

	def test_store_found_from_invoice_field(self):
		"""The invoice's store field picks the matching active store."""
		company = frappe.defaults.get_global_default("company")
		setup_zithara(store_doctype="Company", invoice_store_field="company", default_store=None)
		store = frappe.get_doc(
			{
				"doctype": "Zithara Store",
				"store_code": "ZT-COMPANY",
				"reference_doctype": "Company",
				"reference_name": company,
				"client_id": "company-id",
				"client_secret": "company-secret",
			}
		).insert()
		invoice = frappe._dict(company=company)
		self.assertIsNone(resolve_store(invoice))

		store.status = "Active"
		store.flags.system_status = True
		store.save()
		self.assertEqual(resolve_store(invoice), "ZT-COMPANY")

	def __zithara(self, method, url, **kwargs):
		"""
		Fake Zithara: queued replies first, then success for create / cancel.

		Parameters:
		        method (str, required): HTTP method.
		        url (str, required): Full URL.
		        **kwargs: requests options.

		Returns:
		        MagicMock: Fake response.
		"""
		if self.replies:
			return self.replies.pop(0)
		return zithara_reply(200, CANCELLED) if url.endswith("/cancel") else zithara_reply(201, CREATED)
