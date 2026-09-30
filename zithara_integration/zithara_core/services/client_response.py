# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Zithara replies: errors and success bodies."""

import frappe
from frappe import _

FRIENDLY_ERRORS = {
	400: "Zithara rejected the request",
	401: "Zithara credentials are invalid or expired",
	403: "Zithara refused access for this store",
	404: "Not found on Zithara",
	409: "Already exists on Zithara",
}


class ZitharaError(Exception):
	"""Raised when Zithara returns an error or cannot be reached."""

	def __init__(self, status_code: int, message: str, payload: dict | list | None = None):
		"""
		Build the error with the HTTP status, a readable message and Zithara's reply.

		Parameters:
		        status_code (int, required): HTTP status (0 when Zithara was unreachable).
		        message (str, required): Error message.
		        payload (dict | list, optional): Zithara's JSON reply, kept for the sync log.

		Returns:
		        None
		"""
		super().__init__(message)
		self.status_code = status_code
		self.payload = payload


def parse_response(response) -> dict | list:
	"""
	Turn an HTTP response into a success body or a ZitharaError. Zithara also
	reports failures as HTTP 200 with "success": false.

	Parameters:
	        response (Response, required): Zithara HTTP response.

	Returns:
	        dict | list: Success body.
	"""
	try:
		body = response.json()
	except ValueError:
		body = {}

	if response.status_code >= 400:
		detail = error_detail(body) or response.text[:300]
		base = FRIENDLY_ERRORS.get(response.status_code, "Zithara request failed")
		raise ZitharaError(response.status_code, f"{_(base)} ({response.status_code}): {detail}", body)
	if isinstance(body, dict) and body.get("success") is False:
		message = error_detail(body) or _("Zithara request failed")
		raise ZitharaError(body.get("status_code") or 502, message, body)
	return body


def error_detail(body) -> str:
	"""
	Pick Zithara's own error text from a reply ("error" first, then "message").

	Parameters:
	        body (dict | list, required): Parsed reply.

	Returns:
	        str: Error text, or "" when there is none.
	"""
	if not isinstance(body, dict):
		return ""
	detail = body.get("error") or body.get("message") or ""
	return detail if isinstance(detail, str) else frappe.as_json(detail)
