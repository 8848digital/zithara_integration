# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""doc_events for every DocType: new stores get a Zithara Store and a credential request."""

import frappe

from zithara_integration.zithara_core.services.store_onboarding import is_new_store


def after_insert(doc, method=None):
	"""
	For a new record of the Store DocType, queue its Zithara onboarding. Exits
	after a cached settings lookup for every other insert.

	Parameters:
	        doc (Document, required): The inserted document.
	        method (str, optional): Hook event name passed by Frappe.

	Returns:
	        None
	"""
	if frappe.flags.in_install or frappe.flags.in_migrate or not is_new_store(doc):
		return
	frappe.enqueue(
		"zithara_integration.zithara_core.tasks.onboard_store",
		doctype=doc.doctype,
		name=doc.name,
		enqueue_after_commit=True,
	)
