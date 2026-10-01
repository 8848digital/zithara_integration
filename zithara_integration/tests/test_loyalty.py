# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Loyalty points: balance, OTP redemption on a draft invoice, and its guards."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from zithara_integration.tests.erpnext_fixtures import make_invoice, pay_invoice, sync_logs
from zithara_integration.tests.zithara_fixtures import (
	CLIENT,
	STORE,
	run_jobs_inline,
	setup_zithara,
	token_reply,
	zithara_reply,
)
from zithara_integration.zithara_core.services.loyalty import get_points
from zithara_integration.zithara_core.services.redemption import Redemption

PHONE = "919876543210"
# 1000 points = 1000 rupees; the test invoice totals 2000.
RULE = {"points": 1000, "amount": 1000}
POINTS_REPLY = {
	"success": True,
	"status": 200,
	"data": {
		"points": 4096,
		"customer_id": "150719",
		"config": {"conversion": [{"redeem": RULE}]},
	},
}
OTP_SENT = {"success": True, "status": 200, "data": {"sentTo": PHONE, "sessionID": "session-1"}}
REDEEMED = {"success": True, "status": 200, "data": {"amount": 500}}
BAD_OTP = {"success": False, "status": 400, "message": "Invalid OTP"}


class TestLoyalty(IntegrationTestCase):
	"""Loyalty calls against a mocked Zithara."""

	def setUp(self):
		"""
		Enable Zithara, run jobs inline and mock Zithara's HTTP API.

		Returns:
		        None
		"""
		setup_zithara(enable_loyalty_redemption=1)
		self.jobs = run_jobs_inline()
		patch(f"{CLIENT}.get", return_value=token_reply()).start()
		self.api = patch(f"{CLIENT}.request", side_effect=self.__zithara).start()
		self.replies = {"loyalty-points": zithara_reply(200, POINTS_REPLY)}

	def tearDown(self):
		"""
		Stop all patches.

		Returns:
		        None
		"""
		patch.stopall()

	def __zithara(self, method, url, **kwargs):
		"""
		Answer a Zithara call with the reply set for its endpoint.

		Parameters:
		        method (str, required): HTTP method.
		        url (str, required): Full URL.
		        **kwargs: requests options.

		Returns:
		        MagicMock: Fake response.
		"""
		for fragment, reply in self.replies.items():
			if fragment in url:
				return reply
		return zithara_reply(201, {"status": 201, "orderId": "1"})

	def __initiate_calls(self) -> int:
		"""
		How many OTP requests reached Zithara.

		Returns:
		        int: Number of initiate-redemption calls.
		"""
		return sum("initiate-redemption" in call.args[1] for call in self.api.call_args_list)

	def test_points_balance_looked_up_by_phone(self):
		"""The balance query identifies the customer by phone and passes the redeem rule on."""
		invoice = make_invoice(submit=False)
		data = get_points(invoice.customer, STORE)
		self.assertEqual((data["points"], data["redeem_rule"]), (4096, RULE))
		url = self.api.call_args.args[1]
		self.assertIn(f"/v1/customer/loyalty-points?phone={PHONE}", url)

	def test_redeem_applies_discount_and_marks_order(self):
		"""OTP sent, OTP verified: the value becomes a discount and the order says so."""
		invoice = make_invoice(submit=False)
		grand_total = invoice.grand_total

		self.replies["initiate"] = zithara_reply(200, OTP_SENT)
		log = Redemption(invoice.doctype, invoice.name).send_otp(500)
		self.assertEqual((log.status, log.session_id, log.sent_to), ("OTP Sent", "session-1", PHONE))
		body = self.api.call_args.kwargs["json"]
		self.assertEqual(body, {"points": 500, "phone_number": PHONE})

		self.replies["complete"] = zithara_reply(200, REDEEMED)
		log = Redemption(invoice.doctype, invoice.name).verify_otp(log.name, "123456")
		self.assertEqual((log.status, log.amount), ("Redeemed", 500))
		body = self.api.call_args.kwargs["json"]
		self.assertEqual(body["otp"], "123456")
		self.assertEqual(body["sessionId"], "session-1")
		self.assertNotIn("123456", log.request_payload or "")

		invoice.reload()
		self.assertEqual((invoice.zithara_redemption, invoice.zithara_redeemed_amount), (log.name, 500))
		self.assertEqual(flt(invoice.grand_total), flt(grand_total) - 500)

		invoice.submit()
		pay_invoice(invoice)
		[sync] = sync_logs(invoice)
		attributes = frappe.parse_json(sync.request_payload)["order"]["custom_attributes"]
		self.assertEqual(attributes["cashback_redeemption_amount"], 500)
		self.assertTrue(attributes["cashback_redeemption_order"])

	def test_wrong_otp_fails_without_discount(self):
		"""Zithara refuses the OTP: the redemption fails and the invoice is untouched."""
		invoice = make_invoice(submit=False)
		self.replies["initiate"] = zithara_reply(200, OTP_SENT)
		log = Redemption(invoice.doctype, invoice.name).send_otp(500)

		self.replies["complete"] = zithara_reply(200, BAD_OTP)
		log = Redemption(invoice.doctype, invoice.name).verify_otp(log.name, "000000")
		self.assertEqual((log.status, log.error), ("Failed", "Invalid OTP"))
		invoice.reload()
		self.assertFalse(invoice.zithara_redemption)
		with self.assertRaises(frappe.ValidationError):
			Redemption(invoice.doctype, invoice.name).verify_otp(log.name, "123456")

	def test_otp_request_never_retried(self):
		"""A server error on initiate is not retried: a retry would text the customer again."""
		setup_zithara(max_retries=2, enable_loyalty_redemption=1)
		invoice = make_invoice(submit=False)
		self.replies["initiate"] = zithara_reply(503, {"message": "down"})
		log = Redemption(invoice.doctype, invoice.name).send_otp(500)
		self.assertEqual(log.status, "Failed")
		self.assertEqual(self.__initiate_calls(), 1)

	def test_points_worth_more_than_invoice_refused_before_otp(self):
		"""2500 points = 2500 on a 2000 invoice: refused before any SMS, as is more than the balance."""
		invoice = make_invoice(submit=False)
		self.replies["initiate"] = zithara_reply(200, OTP_SENT)
		with self.assertRaisesRegex(frappe.ValidationError, "at most 2000 points"):
			Redemption(invoice.doctype, invoice.name).send_otp(2500)
		low = {**POINTS_REPLY, "data": {**POINTS_REPLY["data"], "points": 300}}
		self.replies["loyalty-points"] = zithara_reply(200, low)
		with self.assertRaisesRegex(frappe.ValidationError, "only 300 points"):
			Redemption(invoice.doctype, invoice.name).send_otp(500)
		self.assertEqual(self.__initiate_calls(), 0)

	def test_new_otp_waits_a_minute(self):
		"""A second OTP for the same invoice right away is refused."""
		invoice = make_invoice(submit=False)
		self.replies["initiate"] = zithara_reply(200, OTP_SENT)
		Redemption(invoice.doctype, invoice.name).send_otp(500)
		with self.assertRaises(frappe.ValidationError):
			Redemption(invoice.doctype, invoice.name).send_otp(500)

	def test_switched_off_by_default(self):
		"""With Enable Points Redemption off, no loyalty call reaches Zithara."""
		setup_zithara(enable_loyalty_redemption=0)
		invoice = make_invoice(submit=False)
		with self.assertRaises(frappe.ValidationError):
			get_points(invoice.customer, STORE)
		with self.assertRaises(frappe.ValidationError):
			Redemption(invoice.doctype, invoice.name)
		self.api.assert_not_called()

	def test_only_draft_sales_qualify(self):
		"""Submitted invoices can't take a redemption."""
		invoice = make_invoice()
		with self.assertRaises(frappe.ValidationError):
			Redemption(invoice.doctype, invoice.name)

	def test_redeemed_invoice_is_protected(self):
		"""After redemption the discount can't shrink, the customer can't change, the draft can't be deleted."""
		invoice = make_invoice(submit=False)
		self.replies["initiate"] = zithara_reply(200, OTP_SENT)
		log = Redemption(invoice.doctype, invoice.name).send_otp(500)
		self.replies["complete"] = zithara_reply(200, REDEEMED)
		Redemption(invoice.doctype, invoice.name).verify_otp(log.name, "123456")

		invoice.reload()
		invoice.discount_amount = 100
		with self.assertRaises(frappe.ValidationError):
			invoice.save()
		invoice.reload()
		with self.assertRaises(frappe.ValidationError):
			invoice.delete()
		with self.assertRaises(frappe.ValidationError):
			Redemption(invoice.doctype, invoice.name)
