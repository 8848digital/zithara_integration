# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""
Redeem Zithara points on a draft invoice: Zithara texts the customer an OTP,
the cashier enters it, Zithara deducts the points and returns the rupee value,
which is applied as a discount. Every attempt is kept as a Zithara Redemption.
Neither call is ever retried automatically: each initiate sends a real SMS and
each complete consumes the OTP.
"""

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, now_datetime

from zithara_integration.zithara_core.services.client import ZitharaClient
from zithara_integration.zithara_core.services.client_response import ZitharaError
from zithara_integration.zithara_core.services.loyalty import (
	COMPLETE_REDEMPTION_PATH,
	INITIATE_REDEMPTION_PATH,
	customer_identity,
	ensure_points_fit,
	ensure_redemption_enabled,
	identity_fields,
)
from zithara_integration.zithara_core.services.redemption_invoice import apply_redemption
from zithara_integration.zithara_core.services.store_resolver import resolve_store

# A new OTP for the same invoice only after this many seconds (each one is an SMS).
OTP_RESEND_SECONDS = 60


class Redemption:
	"""Points redemption for one draft Sales Invoice / POS Invoice."""

	def __init__(self, invoice_doctype: str, invoice: str):
		"""
		Load the invoice and check it can take a redemption.

		Parameters:
		        invoice_doctype (str, required): "Sales Invoice" or "POS Invoice".
		        invoice (str, required): Invoice name (saved draft).

		Returns:
		        None
		"""
		if invoice_doctype not in ("Sales Invoice", "POS Invoice"):
			frappe.throw(_("Points can only be redeemed on a Sales Invoice or POS Invoice"))
		self.invoice = frappe.get_doc(invoice_doctype, invoice)
		self.__check_invoice()
		self.store = resolve_store(self.invoice)
		if not self.store:
			frappe.throw(_("No active Zithara Store for this invoice"))

	def send_otp(self, points: int):
		"""
		Ask Zithara to text the customer an OTP for redeeming these points.

		Parameters:
		        points (int, required): Points to redeem.

		Returns:
		        Document: The Zithara Redemption (OTP Sent, or Failed with the error).
		"""
		points = cint(points)
		if points <= 0:
			frappe.throw(_("Enter the number of points to redeem"))
		self.__check_resend_wait()
		ensure_points_fit(self.invoice.customer, self.store, points, self.invoice.grand_total)

		identity = customer_identity(self.invoice.customer)
		body = {"points": points, **identity_fields(identity, "initiate")}
		log = self.__new_log(points, body)
		try:
			reply = self.__client().call("POST", INITIATE_REDEMPTION_PATH, body, retry=False)
		except ZitharaError as error:
			return self.__fail(log, error)

		data = (reply.get("data") if isinstance(reply, dict) else None) or {}
		log.session_id = data.get("sessionId") or data.get("sessionID")
		log.sent_to = data.get("sentTo")
		log.response_payload = frappe.as_json(reply)
		log.save(ignore_permissions=True)
		return log

	def verify_otp(self, redemption: str, otp: str):
		"""
		Send the customer's OTP; on success apply the redeemed value as a discount.

		Parameters:
		        redemption (str, required): Zithara Redemption in status OTP Sent.
		        otp (str, required): OTP the customer received.

		Returns:
		        Document: The Zithara Redemption (Redeemed, or Failed with the error).
		"""
		log = frappe.get_doc("Zithara Redemption", redemption)
		if (log.reference_doctype, log.reference_name) != (self.invoice.doctype, self.invoice.name):
			frappe.throw(_("This redemption belongs to another invoice"))
		if log.status != "OTP Sent":
			frappe.throw(_("This OTP request is {0}; send a new OTP").format(_(log.status)))
		otp = (otp or "").strip()
		if not otp:
			frappe.throw(_("Enter the OTP the customer received"))

		identity = customer_identity(self.invoice.customer)
		body = {"points": log.points, "otp": otp, **identity_fields(identity, "complete")}
		if log.session_id:
			body["sessionId"] = log.session_id
		try:
			reply = self.__client().call("POST", COMPLETE_REDEMPTION_PATH, body, retry=False)
		except ZitharaError as error:
			return self.__fail(log, error)

		data = (reply.get("data") if isinstance(reply, dict) else None) or {}
		log.status = "Redeemed"
		log.amount = flt(data.get("amount"))
		log.completed_on = now_datetime()
		log.response_payload = frappe.as_json(reply)
		log.save(ignore_permissions=True)
		# The points are gone on Zithara now: keep the record even if the invoice save fails.
		_keep()
		try:
			apply_redemption(self.invoice, log)
		except Exception as error:
			frappe.db.rollback()
			log.reload()
			log.db_set("error", _("Points redeemed but the discount was not applied: {0}").format(error))
			_keep()
			raise
		return log

	def __check_invoice(self) -> None:
		"""
		Only a saved draft sale with a customer, not yet redeemed, qualifies.

		Returns:
		        None
		"""
		invoice = self.invoice
		if invoice.docstatus != 0 or invoice.is_return:
			frappe.throw(
				_("Points can only be redeemed on a draft sale, not a return or submitted invoice")
			)
		if not invoice.customer:
			frappe.throw(_("Select the customer first"))
		if invoice.get("zithara_redemption"):
			frappe.throw(_("Points were already redeemed on this invoice"))
		ensure_redemption_enabled()
		settings = frappe.get_cached_doc("Zithara Settings")
		if invoice.customer in {row.customer for row in settings.skip_customers}:
			frappe.throw(_("Customer {0} is excluded from Zithara").format(invoice.customer))

	def __check_resend_wait(self) -> None:
		"""
		Block a new OTP while the last one for this invoice is under a minute old.

		Returns:
		        None
		"""
		recent = frappe.db.exists(
			"Zithara Redemption",
			{
				"reference_doctype": self.invoice.doctype,
				"reference_name": self.invoice.name,
				"status": "OTP Sent",
				"creation": (">", add_to_date(now_datetime(), seconds=-OTP_RESEND_SECONDS)),
			},
		)
		if recent:
			frappe.throw(_("An OTP was just sent. Wait a minute before sending another."))

	def __new_log(self, points: int, body: dict):
		"""
		Record the OTP request before calling Zithara.

		Parameters:
		        points (int, required): Points to redeem.
		        body (dict, required): Initiate request body (holds no OTP).

		Returns:
		        Document: New Zithara Redemption in status OTP Sent.
		"""
		return frappe.get_doc(
			{
				"doctype": "Zithara Redemption",
				"status": "OTP Sent",
				"reference_doctype": self.invoice.doctype,
				"reference_name": self.invoice.name,
				"customer": self.invoice.customer,
				"store": self.store,
				"points": points,
				"request_payload": frappe.as_json(body),
			}
		).insert(ignore_permissions=True)

	def __fail(self, log, error: ZitharaError):
		"""
		Mark the redemption Failed with Zithara's reason.

		Parameters:
		        log (Document, required): Zithara Redemption.
		        error (ZitharaError, required): What Zithara answered.

		Returns:
		        Document: The failed Zithara Redemption.
		"""
		log.status = "Failed"
		log.error = str(error)
		log.response_payload = frappe.as_json(error.payload) if error.payload else None
		log.save(ignore_permissions=True)
		return log

	def __client(self) -> ZitharaClient:
		"""
		Zithara client authenticated as the invoice's store.

		Returns:
		        ZitharaClient: Client for self.store.
		"""
		return ZitharaClient.for_store(self.store)


def _keep() -> None:
	"""
	Commit now, so a redemption Zithara already processed is never rolled back
	with a later error. Skipped in tests, which roll back on purpose.

	Returns:
	        None
	"""
	if not frappe.flags.in_test:
		frappe.db.commit()  # nosemgrep
