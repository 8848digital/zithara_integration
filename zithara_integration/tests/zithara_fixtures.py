# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Shared test setup: settings, an active store and fake Zithara replies."""

from unittest.mock import MagicMock, patch

import frappe

from zithara_integration.tests.erpnext_fixtures import WALK_IN, ensure_masters
from zithara_integration.zithara_core.services.client import clear_cached_token

CLIENT = "zithara_integration.zithara_core.services.client.requests"
STORE = "ZT-STORE"
CLIENT_ID = "zt-client-id"
CLIENT_SECRET = "zt-client-secret"


def setup_zithara(**settings_values) -> None:
	"""
	Enable Zithara (live mode, HTTP mocked by the tests) with one active store
	used as the default store, plus a test customer and items.

	Parameters:
	        **settings_values: Zithara Settings overrides.

	Returns:
	        None
	"""
	ensure_masters()
	__store()
	settings = frappe.get_single("Zithara Settings")
	settings.update(
		{
			"enabled": 1,
			"test_mode": 0,
			"environment": "Sandbox",
			"base_url": "https://dev-pos-api.zithara.com",
			"max_retries": 0,
			"max_sync_attempts": 5,
			"store_doctype": "POS Profile",
			"invoice_store_field": "pos_profile",
			"default_store": STORE,
			"sync_sales_invoice": 1,
			"sync_pos_invoice": 1,
			"phone_country_code": "91",
			"skip_customers": [{"customer": WALK_IN}],
			"import_credentials_from_email": 0,
			"request_credentials_automatically": 0,
			**settings_values,
		}
	)
	settings.save()
	clear_cached_token(CLIENT_ID)


def fresh_store(code: str, **values):
	"""
	Insert a Zithara Store, replacing one left by an earlier test (IntegrationTestCase
	rolls back per class, not per test).

	Parameters:
	        code (str, required): Store code.
	        **values: Other fields.

	Returns:
	        Document: The new store.
	"""
	if frappe.db.exists("Zithara Store", code):
		frappe.delete_doc("Zithara Store", code, force=True)
	return frappe.get_doc({"doctype": "Zithara Store", "store_code": code, **values}).insert()


def run_jobs_inline():
	"""
	Patch frappe.enqueue so this app's background jobs run immediately (tests
	never commit, so after-commit jobs would never start).

	Returns:
	        patch: Active patcher; stop it in tearDown.
	"""

	def run_now(method, **kwargs):
		"""
		Call this app's jobs directly with their own arguments; other apps'
		jobs are dropped (they are not under test).

		Parameters:
		        method (str | callable, required): Dotted path of the job.
		        **kwargs: Job arguments plus enqueue options (dropped).

		Returns:
		        None
		"""
		if not (isinstance(method, str) and method.startswith("zithara_integration.")):
			return
		for option in ("queue", "enqueue_after_commit", "now", "timeout", "job_id"):
			kwargs.pop(option, None)
		frappe.get_attr(method)(**kwargs)

	patcher = patch("frappe.enqueue", side_effect=run_now)
	patcher.start()
	return patcher


def zithara_reply(status_code: int = 200, body=None) -> MagicMock:
	"""
	Fake HTTP response.

	Parameters:
	        status_code (int, optional): HTTP status.
	        body (dict | list, optional): JSON body.

	Returns:
	        MagicMock: Response-like object.
	"""
	response = MagicMock()
	response.status_code = status_code
	response.json.return_value = body if body is not None else {}
	response.text = frappe.as_json(body or {})
	return response


def token_reply() -> MagicMock:
	"""
	Fake successful token response.

	Returns:
	        MagicMock: Response with access_token and expires_in.
	"""
	return zithara_reply(200, {"access_token": "token-123", "expires_in": 3600})


def __store() -> None:
	"""
	An active store with credentials (status set as if already checked).

	Returns:
	        None
	"""
	if frappe.db.exists("Zithara Store", STORE):
		frappe.delete_doc("Zithara Store", STORE, force=True)
	store = frappe.get_doc(
		{
			"doctype": "Zithara Store",
			"store_code": STORE,
			"store_name": "Test Store",
			"client_id": CLIENT_ID,
			"client_secret": CLIENT_SECRET,
		}
	).insert()
	store.status = "Active"
	store.flags.system_status = True
	store.save()
