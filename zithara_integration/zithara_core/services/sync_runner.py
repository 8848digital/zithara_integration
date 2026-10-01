# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Send one queued Zithara Sync Log and record Zithara's answer."""

import frappe
from frappe import _

from zithara_integration.zithara_core.services.client import ZitharaClient
from zithara_integration.zithara_core.services.client_response import ZitharaError
from zithara_integration.zithara_core.services.order_payload import OrderPayload

# Network failures, rate limits and Zithara server errors are worth retrying;
# other 4xx answers need someone to fix data or credentials first.
RETRYABLE_STATUSES = (0, 429, 500, 502, 503, 504)
DUPLICATE_STATUS = 409


class SyncRunner:
	"""Executes a Zithara Sync Log against Zithara."""

	def __init__(self, log_name: str):
		"""
		Load the log to send.

		Parameters:
		        log_name (str, required): Zithara Sync Log name.

		Returns:
		        None
		"""
		self.log = frappe.get_doc("Zithara Sync Log", log_name)

	def run(self) -> None:
		"""
		Send the log once and store the outcome. Create Order bodies are built
		now, so payments added after queueing are included.

		Returns:
		        None
		"""
		log = self.log
		if log.status in ("Success", "Duplicate") or not log.store:
			return

		if self.__sale_cancelled():
			log.update({"status": "Skipped", "error": _("The invoice was cancelled before it was sent")})
			log.save(ignore_permissions=True)
			return

		log.attempts = (log.attempts or 0) + 1
		try:
			payload = self.__payload()
			log.request_payload = frappe.as_json(payload)
			client = ZitharaClient.for_store(log.store)
			if log.action == "Create Order":
				response = client.create_order(payload)
			else:
				response = client.cancel_order(payload)
			self.__succeeded(response)
		except ZitharaError as error:
			self.__failed(error.status_code, str(error), error.payload)
		except Exception as error:
			# Data problems (deleted invoice, bad store setup): logged, not retried.
			self.__failed(-1, str(error), None)
			frappe.log_error(title=_("Zithara sync failed: {0}").format(log.name))
		log.save(ignore_permissions=True)

	def __sale_cancelled(self) -> bool:
		"""
		True when a Create Order is still pending but its invoice is no longer submitted.

		Returns:
		        bool: Whether the order should not be sent.
		"""
		if self.log.action != "Create Order":
			return False
		return frappe.db.get_value(self.log.reference_doctype, self.log.reference_name, "docstatus") != 1

	def __payload(self) -> dict:
		"""
		The body to send: stored for cancels, rebuilt from the invoice for creates.

		Returns:
		        dict: Request body.
		"""
		if self.log.action == "Create Order":
			invoice = frappe.get_doc(self.log.reference_doctype, self.log.reference_name)
			return OrderPayload(invoice).build()
		return frappe.parse_json(self.log.request_payload)

	def __succeeded(self, response) -> None:
		"""
		Mark the log successful and keep Zithara's order id.

		Parameters:
		        response (dict | list, required): Zithara reply.

		Returns:
		        None
		"""
		self.log.update(
			{
				"status": "Success",
				"http_status": response.get("status") if isinstance(response, dict) else 200,
				"zithara_order_id": response.get("orderId") if isinstance(response, dict) else None,
				"response_payload": frappe.as_json(response),
				"error": None,
				"retryable": 0,
			}
		)

	def __failed(self, status_code: int, message: str, payload) -> None:
		"""
		Record a failure. A 409 on create means Zithara already has the order
		(e.g. sent twice), which counts as done.

		Parameters:
		        status_code (int, required): HTTP status (0 = unreachable, -1 = local error).
		        message (str, required): Error text.
		        payload (dict | list, optional): Zithara reply.

		Returns:
		        None
		"""
		duplicate = status_code == DUPLICATE_STATUS and self.log.action == "Create Order"
		self.log.update(
			{
				"status": "Duplicate" if duplicate else "Failed",
				"http_status": status_code if status_code > 0 else None,
				"response_payload": frappe.as_json(payload) if payload else None,
				"error": message,
				"retryable": int(status_code in RETRYABLE_STATUSES),
			}
		)
