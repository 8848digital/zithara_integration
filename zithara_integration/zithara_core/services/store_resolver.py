# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Find the Zithara Store an invoice belongs to."""

import frappe


def resolve_store(invoice) -> str | None:
	"""
	Match the invoice's store field (e.g. pos_profile) to an active Zithara
	Store; fall back to the default store for single-store setups.

	Parameters:
	        invoice (Document, required): Sales Invoice / POS Invoice.

	Returns:
	        str | None: Zithara Store name, or None when no active store matches.
	"""
	settings = frappe.get_cached_doc("Zithara Settings")
	store_value = invoice.get(settings.invoice_store_field) if settings.invoice_store_field else None
	if store_value:
		store = frappe.db.get_value(
			"Zithara Store",
			{
				"reference_doctype": settings.store_doctype,
				"reference_name": store_value,
				"status": "Active",
			},
		)
		if store:
			return store

	default = settings.default_store
	if default and frappe.db.get_value("Zithara Store", default, "status") == "Active":
		return default
	return None
