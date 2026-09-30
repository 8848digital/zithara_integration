# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Formatting of values Zithara expects: phones, product ids, money."""

import re
import zlib

from frappe.utils import flt


def normalize_phone(raw: str | None, country_code: str | None) -> str:
	"""
	Digits only, with the country code: "098765 43210" -> "919876543210".

	Parameters:
	        raw (str, optional): Phone as stored.
	        country_code (str, optional): Code to prefix to 10-digit numbers, e.g. "91".

	Returns:
	        str: Normalized phone, or "" when empty.
	"""
	digits = re.sub(r"\D", "", raw or "").lstrip("0")
	code = re.sub(r"\D", "", country_code or "")
	if code and len(digits) == 10:
		return f"{code}{digits}"
	return digits


def product_id(item_code: str) -> int:
	"""
	Stable positive integer for an item code. Zithara wants a numeric product id,
	while ERPNext item codes are text; the code itself is sent as the SKU.

	Parameters:
	        item_code (str, required): Item code.

	Returns:
	        int: CRC32 of the item code.
	"""
	return zlib.crc32((item_code or "").encode())


def money(value) -> float:
	"""
	Round a money value to 2 decimals.

	Parameters:
	        value (float | int | str | None, required): Amount.

	Returns:
	        float: Rounded amount.
	"""
	return round(flt(value), 2)
