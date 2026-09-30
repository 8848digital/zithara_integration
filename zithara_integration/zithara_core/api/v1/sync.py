# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import frappe
from frappe import _

from zithara_integration.utils.api_handlers.response_formatter import api_response
from zithara_integration.zithara_core.services.client import ZitharaClient
from zithara_integration.zithara_core.services.store_resolver import resolve_store
from zithara_integration.zithara_core.services.sync_runner import SyncRunner


@frappe.whitelist(methods=["POST"])
def retry(log: str):
	"""
	        Send a failed or skipped Zithara Sync Log again, right now.

	        **Endpoint:** `/api/method/zithara_integration.zithara_core.api.v1.sync.retry`
	        **HTTP Method:** POST
	        **Parameters:**
	                - log (str, required): Zithara Sync Log name
	        **Response:**
	```json
	                {"status": true, "status_code": 200, "message": "Sent to Zithara",
	                 "data": {"log": "ZSL-00001", "status": "Success", "error": null}, "errors": null}
	```
	"""
	frappe.has_permission("Zithara Sync Log", "write", log, throw=True)
	log_doc = frappe.get_doc("Zithara Sync Log", log)
	if log_doc.status not in ("Failed", "Skipped"):
		frappe.throw(_("Only failed or skipped syncs can be retried"))
	if log_doc.status == "Skipped":
		__assign_store(log_doc)

	SyncRunner(log).run()
	status, error = frappe.db.get_value("Zithara Sync Log", log, ["status", "error"])
	succeeded = status in ("Success", "Duplicate")
	return api_response(
		status=succeeded,
		code=200,
		message=_("Sent to Zithara") if succeeded else _("Zithara sync failed"),
		data={"log": log, "status": status, "error": error},
	)


@frappe.whitelist(methods=["GET"])
def check_order(log: str):
	"""
	        Read the order back from Zithara (no changes on either side), e.g. to see
	        the points Zithara credited.

	        **Endpoint:** `/api/method/zithara_integration.zithara_core.api.v1.sync.check_order`
	        **HTTP Method:** GET
	        **Parameters:**
	                - log (str, required): Zithara Sync Log name
	        **Response:**
	```json
	                {"status": true, "status_code": 200, "message": "Order found on Zithara",
	                 "data": {"found": true, "order": {"platform_order_id": "ACC-SINV-2026-00001", "points_credited": 120}},
	                 "errors": null}
	```
	"""
	frappe.has_permission("Zithara Sync Log", "read", log, throw=True)
	log_doc = frappe.get_doc("Zithara Sync Log", log)
	if not log_doc.store:
		frappe.throw(_("This sync has no Zithara Store"))

	reply = ZitharaClient.for_store(log_doc.store).get_order(log_doc.platform_order_id)
	order = (reply[0] if reply else None) if isinstance(reply, list) else reply
	return api_response(
		status=bool(order),
		code=200,
		message=_("Order found on Zithara") if order else _("Order not found on Zithara"),
		data={"found": bool(order), "order": order},
	)


def __assign_store(log_doc) -> None:
	"""
	A skipped sync had no active store; look again (e.g. after a store went live).

	Parameters:
	        log_doc (Document, required): Zithara Sync Log.

	Returns:
	        None
	"""
	store = resolve_store(frappe.get_doc(log_doc.reference_doctype, log_doc.reference_name))
	if not store:
		frappe.throw(_("There is still no active Zithara Store for this invoice"))
	log_doc.db_set({"store": store, "status": "Failed", "error": None})
