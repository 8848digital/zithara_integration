# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""
Read a store's Zithara credentials from Zithara's email and save them.
Only emails from an allowed sender are read, and the credentials still have to
pass a live check with Zithara, so a spoofed email cannot put a store live.
"""

import re

import frappe
from frappe import _
from frappe.utils import strip_html

from zithara_integration.zithara_core.services.notify import notify
from zithara_integration.zithara_core.services.store_credentials import StoreCredentials

REDACTED = "[secret removed - stored securely on Zithara Store {0}]"


class CredentialEmail:
	"""One incoming email that may carry a store's Zithara credentials."""

	def __init__(self, communication: str):
		"""
		Load the email and the email-reading rules.

		Parameters:
		        communication (str, required): Communication name.

		Returns:
		        None
		"""
		self.email = frappe.get_doc("Communication", communication)
		self.settings = frappe.get_cached_doc("Zithara Settings")

	def is_candidate(self) -> bool:
		"""
		Incoming email, on the configured account, from an allowed sender and
		matching the subject rule.

		Returns:
		        bool: Whether the email should be read.
		"""
		email, settings = self.email, self.settings
		if not settings.import_credentials_from_email:
			return False
		if email.communication_type != "Communication" or email.sent_or_received != "Received":
			return False
		if (
			settings.credential_email_account and email.email_account != settings.credential_email_account
		):
			return False
		if not sender_allowed(email.sender, settings.allowed_senders):
			return False
		return not settings.subject_pattern or bool(
			re.search(settings.subject_pattern, email.subject or "")
		)

	def process(self) -> str | None:
		"""
		Extract the credentials, save them on the matching store and check them.

		Returns:
		        str | None: Zithara Store updated, or None when nothing was read.
		"""
		if not self.is_candidate():
			return None

		text = email_text(self.email.content)
		client_id = first_group(self.settings.client_id_pattern, text)
		client_secret = first_group(self.settings.client_secret_pattern, text)
		if not (client_id and client_secret):
			self.__report(_("Could not read a client id and secret from email {0}").format(self.email.name))
			return None

		store = self.__store(text)
		if not store:
			self.__report(
				_("Email {0} has credentials but no store could be identified").format(self.email.name)
			)
			return None

		credentials = StoreCredentials(store)
		credentials.save_from_email(client_id, client_secret, self.email.name)
		if self.settings.redact_credential_email:
			self.__redact(client_secret, store)

		status = frappe.db.get_value("Zithara Store", store, "status")
		notify(
			_("Zithara credentials received for {0}: {1}").format(store, _(status)),
			"Zithara Store",
			store,
		)
		return store

	def __store(self, text: str) -> str | None:
		"""
		The store the email is for: the store a credential request was sent for
		(the reply is linked to it), else the store named in the email. An
		unknown store name creates a new store for an admin to link.

		Parameters:
		        text (str, required): Plain email text.

		Returns:
		        str | None: Zithara Store name.
		"""
		if self.email.reference_doctype == "Zithara Store" and self.email.reference_name:
			return self.email.reference_name

		identifier = first_group(self.settings.store_pattern, text)
		if not identifier:
			return None
		return find_store(identifier) or _new_store(identifier)

	def __redact(self, client_secret: str, store: str) -> None:
		"""
		Blank the secret out of the saved email; the store keeps it encrypted.

		Parameters:
		        client_secret (str, required): The secret to remove.
		        store (str, required): Zithara Store name, mentioned in the placeholder.

		Returns:
		        None
		"""
		placeholder = REDACTED.format(store)
		for fieldname in ("content", "text_content"):
			value = self.email.get(fieldname)
			if value and client_secret in value:
				frappe.db.set_value(
					"Communication",
					self.email.name,
					fieldname,
					value.replace(client_secret, placeholder),
					update_modified=False,
				)

	def __report(self, message: str) -> None:
		"""
		Tell the admins an email looked like Zithara's but could not be used.

		Parameters:
		        message (str, required): What went wrong.

		Returns:
		        None
		"""
		notify(message, "Communication", self.email.name)


def sender_allowed(sender: str | None, allowed_senders: str | None) -> bool:
	"""
	Match a sender against one-per-line addresses or "@domain" entries.

	Parameters:
	        sender (str, optional): Sender address.
	        allowed_senders (str, optional): Allowed senders, one per line.

	Returns:
	        bool: Whether the sender is allowed.
	"""
	address = (sender or "").strip().lower()
	if not address:
		return False
	for entry in (allowed_senders or "").splitlines():
		entry = entry.strip().lower()
		if entry and (address == entry or (entry.startswith("@") and address.endswith(entry))):
			return True
	return False


def email_text(content: str | None) -> str:
	"""
	Plain text of an HTML email, one line per paragraph / line break.

	Parameters:
	        content (str, optional): Email HTML.

	Returns:
	        str: Plain text.
	"""
	with_breaks = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", content or "")
	return strip_html(with_breaks).replace("&nbsp;", " ")


def first_group(pattern: str | None, text: str) -> str | None:
	"""
	Group 1 of the first match of a pattern, stripped.

	Parameters:
	        pattern (str, optional): Regular expression with one capture group.
	        text (str, required): Text to search.

	Returns:
	        str | None: The captured text, or None.
	"""
	if not pattern:
		return None
	match = re.search(pattern, text)
	return match.group(1).strip() if match and match.group(1) else None


def find_store(identifier: str) -> str | None:
	"""
	Find a store by store code, Zithara store id, store name or linked store.

	Parameters:
	        identifier (str, required): Text naming the store.

	Returns:
	        str | None: Zithara Store name.
	"""
	for fieldname in ("store_code", "zithara_store_id", "store_name", "reference_name"):
		store = frappe.db.get_value("Zithara Store", {fieldname: identifier})
		if store:
			return store
	return None


def _new_store(identifier: str) -> str:
	"""
	Create a store for credentials that name a store we do not know yet.

	Parameters:
	        identifier (str, required): Store text from the email.

	Returns:
	        str: New Zithara Store name.
	"""
	store = frappe.get_doc(
		{"doctype": "Zithara Store", "store_code": identifier[:140], "store_name": identifier[:140]}
	).insert(ignore_permissions=True)
	return store.name
