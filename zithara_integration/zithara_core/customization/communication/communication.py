# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""doc_events for Communication: pick up Zithara's credential emails."""

import frappe


def after_insert(doc, method=None):
	"""
	Queue reading of incoming emails when credential import is on. The
	cheap checks run here; the email is read in the background.

	Parameters:
	        doc (Document, required): The new Communication.
	        method (str, optional): Hook event name passed by Frappe.

	Returns:
	        None
	"""
	if doc.sent_or_received != "Received" or doc.communication_type != "Communication":
		return
	if not frappe.get_cached_doc("Zithara Settings").import_credentials_from_email:
		return
	frappe.enqueue(
		"zithara_integration.zithara_core.tasks.read_credential_email",
		communication=doc.name,
		enqueue_after_commit=True,
	)
