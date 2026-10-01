# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import frappe
from frappe import _

from zithara_integration.utils.api_handlers.response_formatter import api_response
from zithara_integration.zithara_core.services.client_response import ZitharaError
from zithara_integration.zithara_core.services.loyalty import active_store
from zithara_integration.zithara_core.services.loyalty import get_points as fetch_points
from zithara_integration.zithara_core.services.loyalty import max_points_for
from zithara_integration.zithara_core.services.redemption import Redemption
from zithara_integration.zithara_core.services.store_resolver import resolve_store


@frappe.whitelist(methods=["GET"])
def get_points(
	customer: str | None = None,
	store: str | None = None,
	invoice_doctype: str | None = None,
	invoice: str | None = None,
):
	"""
	        Read a customer's Zithara points balance and the merchant's redeem rule.
	        Pass an invoice to use its customer and store (the reply then also has max_points:
	        the most points whose value fits in the invoice), or a customer (and optionally a
	        store; the default store is used otherwise).

	        **Endpoint:** `/api/method/zithara_integration.zithara_core.api.v1.loyalty.get_points`
	        **HTTP Method:** GET
	        **Parameters:**
	                - customer (str, optional): Customer name (required without an invoice)
	                - store (str, optional): Zithara Store to ask as
	                - invoice_doctype (str, optional): "Sales Invoice" or "POS Invoice"
	                - invoice (str, optional): Invoice name
	        **Response:**
	```json
	                {"status": true, "status_code": 200, "message": "Points fetched",
	                 "data": {"customer": "CUST-001", "store": "STORE-01", "points": 4096,
	                          "zithara_customer_id": "150719", "max_points": 1500,
	                          "redeem_rule": {"points": 1000, "amount": 2000, "min_redeem_limit": 1000}},
	                 "errors": null}
	```
	"""
	if invoice_doctype and invoice:
		doc = frappe.get_doc(invoice_doctype, invoice)
		doc.check_permission("read")
		customer, store = doc.customer, store or resolve_store(doc)
	if not customer:
		frappe.throw(_("Customer is required"))
	frappe.has_permission("Customer", "read", customer, throw=True)
	try:
		data = fetch_points(customer, active_store(store))
	except ZitharaError as error:
		return api_response(status=False, code=200, message=str(error), errors=error.payload)
	if invoice_doctype and invoice:
		fits = max_points_for(doc.grand_total, data["redeem_rule"])
		data["max_points"] = min(data["points"], fits) if fits is not None else data["points"]
	return api_response(message=_("Points fetched"), data=data)


@frappe.whitelist(methods=["POST"])
def send_otp(invoice_doctype: str, invoice: str, points: int):
	"""
	        Start a points redemption on a draft invoice: Zithara texts the customer an OTP.
	        Never retried automatically (each call sends an SMS); a new OTP for the same invoice
	        is allowed after a minute.

	        **Endpoint:** `/api/method/zithara_integration.zithara_core.api.v1.loyalty.send_otp`
	        **HTTP Method:** POST
	        **Parameters:**
	                - invoice_doctype (str, required): "Sales Invoice" or "POS Invoice"
	                - invoice (str, required): Saved draft invoice name
	                - points (int, required): Points to redeem
	        **Response:**
	```json
	                {"status": true, "status_code": 200, "message": "OTP sent to the customer",
	                 "data": {"redemption": "ZRD-00001", "status": "OTP Sent", "points": 1000,
	                          "amount": 0, "sent_to": "919876543210", "error": null}, "errors": null}
	```
	"""
	frappe.has_permission(invoice_doctype, "write", invoice, throw=True)
	log = Redemption(invoice_doctype, invoice).send_otp(points)
	return __reply(log, _("OTP sent to the customer"))


@frappe.whitelist(methods=["POST"])
def verify_otp(invoice_doctype: str, invoice: str, redemption: str, otp: str):
	"""
	        Finish a redemption with the customer's OTP. Zithara deducts the points and returns
	        their value, which is added to the invoice's additional discount. A wrong OTP fails
	        this redemption; send a new OTP to try again.

	        **Endpoint:** `/api/method/zithara_integration.zithara_core.api.v1.loyalty.verify_otp`
	        **HTTP Method:** POST
	        **Parameters:**
	                - invoice_doctype (str, required): "Sales Invoice" or "POS Invoice"
	                - invoice (str, required): The draft invoice the OTP was sent for
	                - redemption (str, required): Zithara Redemption from send_otp
	                - otp (str, required): OTP the customer received
	        **Response:**
	```json
	                {"status": true, "status_code": 200, "message": "Points redeemed",
	                 "data": {"redemption": "ZRD-00001", "status": "Redeemed", "points": 1000,
	                          "amount": 2000.0, "sent_to": "919876543210", "error": null}, "errors": null}
	```
	"""
	frappe.has_permission(invoice_doctype, "write", invoice, throw=True)
	log = Redemption(invoice_doctype, invoice).verify_otp(redemption, otp)
	return __reply(log, _("Points redeemed"))


def __reply(log, success_message: str) -> dict:
	"""
	API reply for a redemption step: failed when Zithara refused it.

	Parameters:
	        log (Document, required): Zithara Redemption.
	        success_message (str, required): Message when the step succeeded.

	Returns:
	        dict: Standard response envelope.
	"""
	failed = log.status == "Failed"
	return api_response(
		status=not failed,
		code=200,
		message=log.error if failed else success_message,
		data={
			"redemption": log.name,
			"status": log.status,
			"points": log.points,
			"amount": log.amount,
			"sent_to": log.sent_to,
			"error": log.error,
		},
	)
