# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Bell notifications for the Zithara admins (the Notify Role in Zithara Settings)."""

import frappe
from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification


def notify(subject: str, document_type: str, document_name: str) -> None:
	"""
	Send a system notification to every enabled user with the Notify Role.

	Parameters:
	        subject (str, required): Notification text.
	        document_type (str, required): DocType the notification opens.
	        document_name (str, required): Document the notification opens.

	Returns:
	        None
	"""
	role = frappe.get_cached_doc("Zithara Settings").notify_role or "System Manager"
	role_users = frappe.get_all(
		"Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent"
	)
	users = frappe.get_all(
		"User", filters={"name": ("in", [*role_users, "Administrator"]), "enabled": 1}, pluck="name"
	)

	enqueue_create_notification(
		users,
		{
			"type": "Alert",
			"subject": subject,
			"document_type": document_type,
			"document_name": document_name,
		},
	)
