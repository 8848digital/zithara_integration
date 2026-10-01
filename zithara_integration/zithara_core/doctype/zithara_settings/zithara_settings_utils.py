# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Validation for Zithara Settings."""

import re
from urllib.parse import urlparse

import frappe
from frappe import _

BASE_URLS = {
	"Sandbox": "https://dev-pos-api.zithara.com",
	"Production": "https://pos-api.zithara.com",
}
PATTERN_FIELDS = ("subject_pattern", "store_pattern", "client_id_pattern", "client_secret_pattern")
# The subject rule only has to match; the others must capture the value in group 1.
CAPTURE_FIELDS = ("store_pattern", "client_id_pattern", "client_secret_pattern")
LOCAL_HOSTS = ("localhost", "127.0.0.1")
INVOICE_DOCTYPES = ("Sales Invoice", "POS Invoice")


def validate_settings(doc) -> None:
	"""
	Fill the environment's base URL and validate store mapping and patterns.

	Parameters:
	        doc (Document, required): Zithara Settings.

	Returns:
	        None
	"""
	__set_base_url(doc)
	__validate_store_mapping(doc)
	__validate_patterns(doc)


def __set_base_url(doc) -> None:
	"""
	Switch the base URL with the environment unless a custom URL was entered.

	Parameters:
	        doc (Document, required): Zithara Settings.

	Returns:
	        None
	"""
	if not doc.base_url or doc.base_url.rstrip("/") in BASE_URLS.values():
		doc.base_url = BASE_URLS.get(doc.environment, BASE_URLS["Sandbox"])
	doc.base_url = doc.base_url.rstrip("/")
	if doc.base_url.startswith("https://") or doc.test_mode or __is_local_mock(doc.base_url):
		return
	frappe.throw(_("Base URL must start with https://"))


def __is_local_mock(base_url: str) -> bool:
	"""
	Allow a plain-http local mock Zithara (scripts/mock_zithara) in developer mode only.

	Parameters:
	        base_url (str, required): Base URL entered in the settings.

	Returns:
	        bool: True for http://localhost or http://127.0.0.1 on a developer-mode site.
	"""
	host = urlparse(base_url).hostname
	return bool(frappe.conf.developer_mode) and base_url.startswith("http://") and host in LOCAL_HOSTS


def __validate_store_mapping(doc) -> None:
	"""
	The invoice store field must exist on the synced invoice types and point
	at the Store DocType.

	Parameters:
	        doc (Document, required): Zithara Settings.

	Returns:
	        None
	"""
	for invoice_doctype in INVOICE_DOCTYPES:
		field = frappe.get_meta(invoice_doctype).get_field(doc.invoice_store_field)
		if not field:
			frappe.throw(
				_("Field {0} does not exist on {1}").format(
					frappe.bold(doc.invoice_store_field), invoice_doctype
				)
			)
		if field.fieldtype == "Link" and field.options != doc.store_doctype:
			frappe.throw(
				_("Field {0} on {1} links to {2}, not {3}").format(
					frappe.bold(doc.invoice_store_field), invoice_doctype, field.options, doc.store_doctype
				)
			)


def __validate_patterns(doc) -> None:
	"""
	Every pattern must be a valid regular expression; value patterns need a
	capture group.

	Parameters:
	        doc (Document, required): Zithara Settings.

	Returns:
	        None
	"""
	for fieldname in PATTERN_FIELDS:
		pattern = doc.get(fieldname)
		if not pattern:
			continue
		label = _(doc.meta.get_label(fieldname))
		try:
			compiled = re.compile(pattern)
		except re.error as error:
			frappe.throw(_("{0} is not a valid regular expression: {1}").format(label, error))
		if fieldname in CAPTURE_FIELDS and compiled.groups < 1:
			frappe.throw(_("{0} needs a capture group ( ... ) around the value").format(label))
