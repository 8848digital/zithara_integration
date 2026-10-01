# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Zithara Cancel Order body for a return invoice."""

import frappe

# Return rows point at the original line through this field, per invoice type.
RETURN_LINK_FIELD = {"Sales Invoice": "sales_invoice_item", "POS Invoice": "pos_invoice_item"}


def cancel_payload(return_invoice) -> dict | None:
	"""
	Cancel body for a return: "complete" when every original line comes back,
	otherwise "partial" with the returned line ids.

	Parameters:
	        return_invoice (Document, required): Submitted return (is_return=1).

	Returns:
	        dict | None: Cancel body, or None when there is no original invoice.
	"""
	original = return_invoice.return_against
	if not original:
		return None

	link_field = RETURN_LINK_FIELD[return_invoice.doctype]
	returned = {row.get(link_field) for row in return_invoice.items if row.get(link_field)}
	all_lines = set(
		frappe.get_all(f"{return_invoice.doctype} Item", filters={"parent": original}, pluck="name")
	)
	if not returned or returned >= all_lines:
		return {"platform_order_id": original, "type": "complete"}
	return {
		"platform_order_id": original,
		"type": "partial",
		"platform_line_item_ids": sorted(returned),
	}
