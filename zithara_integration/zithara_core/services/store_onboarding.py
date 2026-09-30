# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""
New store in ERPNext -> Zithara Store created and credentials requested from
Zithara by email (when "Request for New Stores Automatically" is on).
"""

import frappe
from frappe import _

from zithara_integration.zithara_core.services.notify import notify
from zithara_integration.zithara_core.services.store_credentials import request_credentials


def is_new_store(doc) -> bool:
	"""
	Cheap check run on every insert: is this a new record of the Store DocType
	with automatic requests switched on?

	Parameters:
	        doc (Document, required): The inserted document.

	Returns:
	        bool: Whether a Zithara Store should be created for it.
	"""
	if doc.doctype in ("Zithara Store", "Zithara Sync Log", "Communication"):
		return False
	settings = frappe.get_cached_doc("Zithara Settings")
	return bool(
		settings.enabled
		and settings.request_credentials_automatically
		and doc.doctype == settings.store_doctype
	)


def onboard_store(doctype: str, name: str) -> None:
	"""
	Create the Zithara Store for a new ERPNext store and email Zithara for its
	credentials. Runs in the background; a failed email is reported, not raised.

	Parameters:
	        doctype (str, required): Store DocType, e.g. POS Profile.
	        name (str, required): The new store record.

	Returns:
	        None
	"""
	if frappe.db.exists("Zithara Store", {"reference_doctype": doctype, "reference_name": name}):
		return

	store = frappe.get_doc(
		{
			"doctype": "Zithara Store",
			"store_code": name,
			"store_name": name,
			"reference_doctype": doctype,
			"reference_name": name,
		}
	).insert(ignore_permissions=True)

	try:
		request_credentials(store.name)
	except Exception:
		frappe.log_error(title=_("Zithara credential request failed: {0}").format(store.name))
		notify(
			_("Could not email Zithara for {0}'s credentials").format(store.name),
			"Zithara Store",
			store.name,
		)
