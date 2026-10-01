# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""
Payload checks the mock applies to Create / Cancel Order bodies. Rules come from
Zithara's POS doc and the previous backend's live dev tests; where Zithara's exact
rule is unknown the check is a warning (reported, not rejected).
"""

import re

PHONE_PATTERN = re.compile(r"^91\d{10}$")
CREATED_AT_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
CANCEL_TYPES = ("complete", "partial")


def check_order(body: dict, used_line_ids: set) -> tuple[list, list]:
	"""
	Check a Create Order body.

	Parameters:
	        body (dict, required): Create Order body.
	        used_line_ids (set, required): Line ids already taken by earlier orders.

	Returns:
	        tuple[list, list]: (errors that reject the order, warnings).
	"""
	errors, warnings = [], []
	customer = body.get("customer") or {}
	order = body.get("order") or {}
	lines = body.get("order_line_item") or []

	if not customer.get("platform_customer_id"):
		errors.append("customer.platform_customer_id is required")
	phone = str(customer.get("phone_number") or "")
	if not PHONE_PATTERN.match(phone):
		errors.append(f"customer.phone_number must be 91 + 10 digits, got {phone!r}")
	if not order.get("platform_order_id"):
		errors.append("order.platform_order_id is required")
	if not CREATED_AT_PATTERN.match(str(order.get("created_at") or "")):
		errors.append("order.created_at must be 'YYYY-MM-DD HH:MM:SS' (naive, local time)")
	if not body.get("timezone"):
		warnings.append("timezone is missing (Zithara reads created_at in this zone)")
	if not lines:
		errors.append("order_line_item must have at least one line")

	errors += __check_lines(lines, used_line_ids)
	warnings += __check_totals(order, body.get("transactions") or [])
	if not body.get("transactions"):
		warnings.append("no transactions: real Zithara accepts but silently DROPS such orders")
	return errors, warnings


def check_cancel(body: dict, order: dict | None) -> list:
	"""
	Check a Cancel Order body against the stored order.

	Parameters:
	        body (dict, required): Cancel body.
	        order (dict, optional): The stored order, None when unknown.

	Returns:
	        list: Errors (empty when the cancel is valid).
	"""
	if order is None:
		return [f"order {body.get('platform_order_id')!r} not found"]
	if body.get("type") not in CANCEL_TYPES:
		return [f"type must be one of {CANCEL_TYPES}"]
	if body["type"] == "complete":
		return []
	ids = body.get("platform_line_item_ids") or []
	if not ids:
		return ["partial cancel needs platform_line_item_ids"]
	unknown = sorted(set(ids) - set(order["line_ids"]))
	return [f"line ids not on this order: {unknown}"] if unknown else []


def __check_lines(lines: list, used_line_ids: set) -> list:
	"""
	Each line needs a globally unique string id, an int product_id and qty > 0.

	Parameters:
	        lines (list, required): order_line_item rows.
	        used_line_ids (set, required): Line ids already taken.

	Returns:
	        list: Errors.
	"""
	errors, seen = [], set()
	for index, line in enumerate(lines, start=1):
		line_id = line.get("platform_line_item_id")
		if not isinstance(line_id, str) or not line_id:
			errors.append(f"line {index}: platform_line_item_id must be a non-empty string")
		elif line_id in used_line_ids or line_id in seen:
			errors.append(
				f"line {index}: platform_line_item_id {line_id!r} already used (must be globally unique)"
			)
		seen.add(line_id)
		if not isinstance(line.get("product_id"), int) or isinstance(line.get("product_id"), bool):
			errors.append(f"line {index}: product_id must be an integer")
		if not (line.get("quantity") or 0) > 0:
			errors.append(f"line {index}: quantity must be > 0")
	return errors


def __check_totals(order: dict, transactions: list) -> list:
	"""
	Soft total checks: subtotal + tax = total, payments = total.

	Parameters:
	        order (dict, required): The order block.
	        transactions (list, required): Payment rows.

	Returns:
	        list: Warnings.
	"""
	warnings = []
	total = float(order.get("current_total_price") or 0)
	subtotal = float(order.get("current_subtotal_price") or 0)
	tax = float(order.get("current_total_tax") or 0)
	if abs(subtotal + tax - total) > 0.01:
		warnings.append(f"subtotal {subtotal} + tax {tax} != total {total}")
	paid = sum(float(row.get("transaction_final_amount") or 0) for row in transactions)
	if transactions and abs(paid - total) > 0.01:
		warnings.append(f"transactions add up to {paid}, order total is {total}")
	return warnings
