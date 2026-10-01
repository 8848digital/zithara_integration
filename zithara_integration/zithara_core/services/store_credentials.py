# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""
Store credential lifecycle: check with Zithara, approve, save from an email.

    Awaiting Credentials -> (credentials saved) -> Not Verified
    Not Verified -> (check OK) -> Active, or Pending Approval for emailed
    credentials when approval is required -> (approve) -> Active
    any check failure -> Invalid Credentials
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from zithara_integration.zithara_core.services.client import ZitharaClient
from zithara_integration.zithara_core.services.client_response import ZitharaError


class StoreCredentials:
	"""Credential actions for one Zithara Store."""

	def __init__(self, store: str):
		"""
		Load the store.

		Parameters:
		        store (str, required): Zithara Store name.

		Returns:
		        None
		"""
		self.store = frappe.get_doc("Zithara Store", store)
		self.settings = frappe.get_cached_doc("Zithara Settings")

	def verify(self) -> bool:
		"""
		Ask Zithara for a token with the saved credentials and set the status.

		Returns:
		        bool: True when Zithara accepted the credentials.
		"""
		store = self.store
		if not (store.client_id and store.get_password("client_secret", raise_exception=False)):
			frappe.throw(_("Enter the Client ID and Client Secret first"))

		try:
			ZitharaClient.for_store(store.name).test_connection()
		except ZitharaError as error:
			self.__set_status("Invalid Credentials", last_error=str(error))
			return False

		self.__set_status(
			"Pending Approval" if self.__needs_approval() else "Active",
			last_verified_on=now_datetime(),
			last_error=None,
		)
		return True

	def approve(self) -> None:
		"""
		Put checked, emailed credentials live.

		Returns:
		        None
		"""
		if self.store.status != "Pending Approval":
			frappe.throw(_("Only stores pending approval can be approved"))
		self.__set_status("Active", approved_by=frappe.session.user)

	def save_from_email(self, client_id: str, client_secret: str, communication: str) -> None:
		"""
		Store credentials read from Zithara's email, then check them.

		Parameters:
		        client_id (str, required): Client id from the email.
		        client_secret (str, required): Client secret from the email.
		        communication (str, required): The email (Communication) they came from.

		Returns:
		        None
		"""
		store = self.store
		store.update(
			{
				"client_id": client_id,
				"client_secret": client_secret,
				"credentials_source": "Email",
				"source_email": communication,
				"approved_by": None,
			}
		)
		store.flags.from_email = True
		store.save(ignore_permissions=True)
		self.verify()

	def __needs_approval(self) -> bool:
		"""
		Emailed credentials wait for approval when the settings ask for it;
		credentials typed in by an admin are already approved by them.

		Returns:
		        bool: Whether approval is needed.
		"""
		return (
			self.store.credentials_source == "Email"
			and bool(self.settings.require_approval)
			and not self.store.approved_by
		)

	def __set_status(self, status: str, **values) -> None:
		"""
		Save a system-set status (the store's validate keeps it only with this flag).

		Parameters:
		        status (str, required): New status.
		        **values: Other fields to update.

		Returns:
		        None
		"""
		self.store.update({"status": status, **values})
		self.store.flags.system_status = True
		self.store.save(ignore_permissions=True)


def request_credentials(store: str) -> None:
	"""
	Email Zithara for a store's credentials. The email is linked to the store,
	so Zithara's reply is matched to it automatically.

	Parameters:
	        store (str, required): Zithara Store name.

	Returns:
	        None
	"""
	settings = frappe.get_cached_doc("Zithara Settings")
	if not settings.zithara_contact_email:
		frappe.throw(_("Set the Zithara Contact Email in Zithara Settings"))

	store_doc = frappe.get_doc("Zithara Store", store)
	subject, message = __request_email(store_doc, settings.request_email_template)
	frappe.sendmail(
		recipients=[settings.zithara_contact_email],
		subject=subject,
		message=message,
		reference_doctype="Zithara Store",
		reference_name=store_doc.name,
		now=True,
	)
	store_doc.db_set("credentials_requested_on", now_datetime())


def __request_email(store_doc, template: str | None) -> tuple[str, str]:
	"""
	Subject and body of the credential request, from the Email Template when set.

	Parameters:
	        store_doc (Document, required): Zithara Store.
	        template (str, optional): Email Template name.

	Returns:
	        tuple[str, str]: (subject, HTML message).
	"""
	if template:
		email = frappe.get_doc("Email Template", template).get_formatted_email(store_doc.as_dict())
		return email["subject"], email["message"]

	company = frappe.defaults.get_global_default("company") or ""
	subject = _("Zithara credentials request: {0}").format(store_doc.store_code)
	message = _(
		"Hello Zithara team,<br><br>We have opened a new store and need its POS API "
		"credentials (client id and client secret).<br><br>"
		"Store code: {0}<br>Store name: {1}<br>Company: {2}<br><br>"
		"Please reply to this email with the credentials.<br><br>Thank you."
	).format(store_doc.store_code, store_doc.store_name or store_doc.store_code, company)
	return subject, message
