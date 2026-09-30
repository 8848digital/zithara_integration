# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Background and scheduled jobs for Zithara."""

import frappe

from zithara_integration.zithara_core.services.credential_email import CredentialEmail
from zithara_integration.zithara_core.services.order_sync import enqueue_log
from zithara_integration.zithara_core.services.store_onboarding import (
	onboard_store as _onboard_store,
)
from zithara_integration.zithara_core.services.sync_runner import SyncRunner

RETRY_BATCH = 200


def send_sync_log(log_name: str) -> None:
	"""
	Send one queued Zithara Sync Log.

	Parameters:
	        log_name (str, required): Zithara Sync Log name.

	Returns:
	        None
	"""
	SyncRunner(log_name).run()


def retry_failed_syncs() -> None:
	"""
	Hourly: re-queue failed syncs that can succeed on retry, up to the attempt
	limit in Zithara Settings.

	Returns:
	        None
	"""
	settings = frappe.get_cached_doc("Zithara Settings")
	if not (settings.enabled and settings.max_sync_attempts):
		return
	logs = frappe.get_all(
		"Zithara Sync Log",
		filters={"status": "Failed", "retryable": 1, "attempts": ("<", settings.max_sync_attempts)},
		pluck="name",
		order_by="creation asc",
		limit=RETRY_BATCH,
	)
	for log_name in logs:
		enqueue_log(log_name)


def read_credential_email(communication: str) -> None:
	"""
	Read a store's credentials from an incoming email.

	Parameters:
	        communication (str, required): Communication name.

	Returns:
	        None
	"""
	CredentialEmail(communication).process()


def onboard_store(doctype: str, name: str) -> None:
	"""
	Create a Zithara Store for a new ERPNext store and request its credentials.

	Parameters:
	        doctype (str, required): Store DocType.
	        name (str, required): Store record name.

	Returns:
	        None
	"""
	_onboard_store(doctype, name)
