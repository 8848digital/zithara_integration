# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import frappe
from frappe import _

from zithara_integration.utils.api_handlers.response_formatter import api_response
from zithara_integration.zithara_core.services.store_credentials import StoreCredentials
from zithara_integration.zithara_core.services.store_credentials import (
	request_credentials as send_credential_request,
)


@frappe.whitelist(methods=["POST"])
def test_connection(store: str):
	"""
	        Check a Zithara Store's credentials by asking Zithara for an access token,
	        and update the store's status (Active, Pending Approval or Invalid Credentials).

	        **Endpoint:** `/api/method/zithara_integration.zithara_core.api.v1.store.test_connection`
	        **HTTP Method:** POST
	        **Parameters:**
	                - store (str, required): Zithara Store name (its store code)
	        **Response:**
	```json
	                {"status": true, "status_code": 200, "message": "Zithara accepted the credentials",
	                 "data": {"store": "STORE-01", "status": "Active", "last_error": null}, "errors": null}
	```
	"""
	frappe.has_permission("Zithara Store", "write", store, throw=True)
	accepted = StoreCredentials(store).verify()
	return api_response(
		status=accepted,
		code=200,
		message=_("Zithara accepted the credentials")
		if accepted
		else _("Zithara rejected the credentials"),
		data=__store_state(store),
	)


@frappe.whitelist(methods=["POST"])
def approve(store: str):
	"""
	        Approve a store whose emailed credentials passed the check, putting it live.

	        **Endpoint:** `/api/method/zithara_integration.zithara_core.api.v1.store.approve`
	        **HTTP Method:** POST
	        **Parameters:**
	                - store (str, required): Zithara Store name in status Pending Approval
	        **Response:**
	```json
	                {"status": true, "status_code": 200, "message": "Store approved",
	                 "data": {"store": "STORE-01", "status": "Active", "last_error": null}, "errors": null}
	```
	"""
	frappe.has_permission("Zithara Store", "write", store, throw=True)
	StoreCredentials(store).approve()
	return api_response(message=_("Store approved"), data=__store_state(store))


@frappe.whitelist(methods=["POST"])
def request_credentials(store: str):
	"""
	        Email Zithara (Zithara Contact Email in settings) for a store's credentials.
	        Zithara's reply is matched to the store automatically.

	        **Endpoint:** `/api/method/zithara_integration.zithara_core.api.v1.store.request_credentials`
	        **HTTP Method:** POST
	        **Parameters:**
	                - store (str, required): Zithara Store name
	        **Response:**
	```json
	                {"status": true, "status_code": 200, "message": "Credential request sent to Zithara",
	                 "data": {"store": "STORE-01", "status": "Awaiting Credentials", "last_error": null}, "errors": null}
	```
	"""
	frappe.has_permission("Zithara Store", "write", store, throw=True)
	send_credential_request(store)
	return api_response(message=_("Credential request sent to Zithara"), data=__store_state(store))


def __store_state(store: str) -> dict:
	"""
	Current status fields of a store for API replies.

	Parameters:
	        store (str, required): Zithara Store name.

	Returns:
	        dict: {"store", "status", "last_error"}.
	"""
	status, last_error = frappe.db.get_value("Zithara Store", store, ["status", "last_error"])
	return {"store": store, "status": status, "last_error": last_error}
