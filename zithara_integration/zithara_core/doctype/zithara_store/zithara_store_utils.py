# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Validation and status rules for Zithara Store."""

import frappe
from frappe import _

from zithara_integration.zithara_core.services.client import clear_cached_token

# Set only by the system (checks, approval, email import); never from the form.
SYSTEM_FIELDS = (
	"status",
	"last_verified_on",
	"approved_by",
	"credentials_source",
	"source_email",
	"credentials_requested_on",
	"last_error",
)


def validate_store(doc) -> None:
	"""
	Default the store DocType, block duplicate links, keep system fields
	system-owned and derive the status.

	Parameters:
	        doc (Document, required): Zithara Store.

	Returns:
	        None
	"""
	if doc.reference_name and not doc.reference_doctype:
		doc.reference_doctype = frappe.get_cached_doc("Zithara Settings").store_doctype
	__validate_unique_link(doc)

	if not doc.flags.system_status:
		__restore_system_fields(doc)
	doc.flags.credentials_changed = __credentials_changed(doc)
	if doc.flags.credentials_changed and not doc.flags.from_email:
		# Typed in by an admin: that admin vouches for them.
		doc.credentials_source = "Manual"
		doc.source_email = None
		doc.approved_by = None
	doc.status = __status(doc)


def after_store_update(doc) -> None:
	"""
	Forget cached tokens for the old and new client id after a credential change.

	Parameters:
	        doc (Document, required): Zithara Store.

	Returns:
	        None
	"""
	if not doc.flags.credentials_changed:
		return
	before = doc.get_doc_before_save()
	clear_cached_token(doc.client_id)
	if before and before.client_id != doc.client_id:
		clear_cached_token(before.client_id)


def __validate_unique_link(doc) -> None:
	"""
	One Zithara Store per ERPNext store.

	Parameters:
	        doc (Document, required): Zithara Store.

	Returns:
	        None
	"""
	if not doc.reference_name:
		return
	other = frappe.db.get_value(
		"Zithara Store",
		{
			"reference_doctype": doc.reference_doctype,
			"reference_name": doc.reference_name,
			"name": ("!=", doc.name),
		},
	)
	if other:
		frappe.throw(_("{0} is already linked to Zithara Store {1}").format(doc.reference_name, other))


def __restore_system_fields(doc) -> None:
	"""
	Undo edits to system fields coming from the form or API.

	Parameters:
	        doc (Document, required): Zithara Store.

	Returns:
	        None
	"""
	before = doc.get_doc_before_save()
	for fieldname in SYSTEM_FIELDS:
		if doc.flags.from_email and fieldname in ("credentials_source", "source_email", "approved_by"):
			continue
		doc.set(fieldname, before.get(fieldname) if before else doc.meta.get_field(fieldname).default)


def __credentials_changed(doc) -> bool:
	"""
	True when the client id changed or a new secret was typed (an unchanged
	Password field comes back as asterisks).

	Parameters:
	        doc (Document, required): Zithara Store.

	Returns:
	        bool: Whether the credentials changed.
	"""
	before = doc.get_doc_before_save()
	new_secret = bool(doc.client_secret) and not doc.is_dummy_password(doc.client_secret)
	id_changed = (before.client_id if before else None) != doc.client_id
	return bool(new_secret or (id_changed and doc.client_id))


def __has_credentials(doc) -> bool:
	"""
	Client id plus a secret, either just typed or already stored.

	Parameters:
	        doc (Document, required): Zithara Store.

	Returns:
	        bool: Whether both credentials are present.
	"""
	if not doc.client_id:
		return False
	if doc.client_secret and not doc.is_dummy_password(doc.client_secret):
		return True
	return not doc.is_new() and bool(doc.get_password("client_secret", raise_exception=False))


def __status(doc) -> str:
	"""
	Status from the flags and credentials. System-set statuses (checks,
	approval) are kept; a credential change always needs a new check.

	Parameters:
	        doc (Document, required): Zithara Store.

	Returns:
	        str: Store status.
	"""
	if doc.disabled:
		return "Disabled"
	if not __has_credentials(doc):
		return "Awaiting Credentials"
	if doc.flags.system_status:
		return doc.status
	if doc.flags.credentials_changed or doc.status in ("Disabled", "Awaiting Credentials"):
		return "Not Verified"
	return doc.status
