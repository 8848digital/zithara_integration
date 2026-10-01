# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""In-memory state of the mock Zithara: stores, tokens, orders and injected faults."""

import secrets
import threading
import time

from checks import check_cancel, check_order


class MockState:
	"""Everything the mock remembers between requests (lost on restart)."""

	def __init__(self, credentials: dict, token_ttl: int):
		"""
		Keep the valid store credentials and start empty.

		Parameters:
		        credentials (dict, required): {client_id: client_secret} of valid stores.
		        token_ttl (int, required): Token lifetime in seconds (sent as expires_in).

		Returns:
		        None
		"""
		self.lock = threading.Lock()
		self.credentials = credentials
		self.token_ttl = token_ttl
		self.reset()

	def reset(self) -> None:
		"""
		Forget tokens, orders, faults and the request log.

		Returns:
		        None
		"""
		with self.lock:
			self.tokens = {}  # token -> (client_id, expires_at)
			self.orders = {}  # (client_id, platform_order_id) -> order
			self.line_ids = set()
			self.faults = []  # [status, remaining count]
			self.log = []
			self.next_order_id = 700001

	def issue_token(self, client_id: str, client_secret: str) -> tuple[int, dict]:
		"""
		Generate Access Token: header credentials in, token out.

		Parameters:
		        client_id (str, required): client_id header.
		        client_secret (str, required): client_secret header.

		Returns:
		        tuple[int, dict]: HTTP status and reply.
		"""
		if not client_id or self.credentials.get(client_id) != client_secret:
			return 401, {"success": False, "message": "Invalid client_id or client_secret"}
		token = secrets.token_hex(16)
		with self.lock:
			self.tokens[token] = (client_id, time.time() + self.token_ttl)
		return 200, {"access_token": token, "expires_in": self.token_ttl}

	def client_for(self, authorization: str) -> str | None:
		"""
		Store the raw token belongs to.

		Parameters:
		        authorization (str, required): Authorization header (raw token, no "Bearer").

		Returns:
		        str | None: client_id, or None when missing, expired or unknown.
		"""
		entry = self.tokens.get(authorization or "")
		if not entry or entry[1] < time.time():
			return None
		return entry[0]

	def expire_tokens(self) -> None:
		"""
		Invalidate every token (tests the client's 401 -> refresh path).

		Returns:
		        None
		"""
		with self.lock:
			self.tokens.clear()

	def add_fault(self, status: int, count: int) -> None:
		"""
		Make the next `count` API calls fail with `status`.

		Parameters:
		        status (int, required): HTTP status to return.
		        count (int, required): Number of calls to fail.

		Returns:
		        None
		"""
		with self.lock:
			self.faults.append([status, count])

	def take_fault(self) -> int | None:
		"""
		Consume one injected fault, if any is pending.

		Returns:
		        int | None: HTTP status to fail with, or None.
		"""
		with self.lock:
			if not self.faults:
				return None
			fault = self.faults[0]
			fault[1] -= 1
			if fault[1] <= 0:
				self.faults.pop(0)
			return fault[0]

	def create_order(self, client_id: str, body: dict) -> tuple[int, dict, list]:
		"""
		Create Order: 201 on success, 409 duplicate, 200 success:false on bad data.

		Parameters:
		        client_id (str, required): Calling store.
		        body (dict, required): Create Order body.

		Returns:
		        tuple[int, dict, list]: HTTP status, reply, payload warnings.
		"""
		order_id = (body.get("order") or {}).get("platform_order_id")
		with self.lock:
			if (client_id, order_id) in self.orders:
				return 409, {"success": False, "message": f"Order {order_id} already exists"}, []
			errors, warnings = check_order(body, self.line_ids)
			if errors:
				return 200, {"success": False, "status_code": 400, "message": "; ".join(errors)}, warnings
			line_ids = [line["platform_line_item_id"] for line in body["order_line_item"]]
			zithara_id = str(self.next_order_id)
			self.next_order_id += 1
			self.line_ids.update(line_ids)
			self.orders[(client_id, order_id)] = {
				"id": zithara_id,
				"platform_order_id": order_id,
				"line_ids": line_ids,
				"cancelled_line_ids": [],
				"status": "dropped" if not body.get("transactions") else "paid",
				"body": body,
			}
		return 201, {"status": 201, "message": "order created", "orderId": zithara_id}, warnings

	def cancel_order(self, client_id: str, body: dict) -> tuple[int, dict]:
		"""
		Cancel Order: complete, or partial by line ids (reply shape verified live).

		Parameters:
		        client_id (str, required): Calling store.
		        body (dict, required): Cancel body.

		Returns:
		        tuple[int, dict]: HTTP status and reply.
		"""
		with self.lock:
			order = self.orders.get((client_id, body.get("platform_order_id")))
			errors = check_cancel(body, order)
			if errors:
				return 200, {"success": False, "status_code": 400, "message": "; ".join(errors)}
			if body["type"] == "complete":
				order["status"] = "cancelled"
				order["cancelled_line_ids"] = list(order["line_ids"])
			else:
				order["cancelled_line_ids"] += body["platform_line_item_ids"]
				order["status"] = "partially_cancelled"
		return 200, {
			"success": True,
			"message": "order cancelled",
			"addedResult": {"success": True},
			"deductedResult": {"success": True, "data": {"amount": 0}, "remainingPoints": 0},
			"points_deducted": 0,
		}

	def get_order(self, client_id: str, platform_order_id: str) -> tuple[int, list | dict]:
		"""
		Get Order: an ARRAY with the order, like the real API.

		Parameters:
		        client_id (str, required): Calling store.
		        platform_order_id (str, required): Our order id (invoice name).

		Returns:
		        tuple[int, list | dict]: HTTP status and reply.
		"""
		order = self.orders.get((client_id, platform_order_id))
		if not order:
			return 404, {"success": False, "message": f"Order {platform_order_id} not found"}
		body = order["body"]
		return 200, [
			{
				"id": order["id"],
				"platform_order_id": platform_order_id,
				"status": order["status"],
				"cancelled_line_ids": order["cancelled_line_ids"],
				"points_credited": 0,
				**{key: body["order"].get(key) for key in ("currency", "current_total_price", "created_at")},
				"order_line_items": body.get("order_line_item"),
				"transactions": body.get("transactions"),
				"customer": body.get("customer"),
			}
		]

	def snapshot(self) -> dict:
		"""
		Everything received so far, for /__mock/state.

		Returns:
		        dict: Orders, pending faults and the last 50 requests.
		"""
		return {
			"orders": [{"client_id": key[0], **order} for key, order in self.orders.items()],
			"pending_faults": self.faults,
			"requests": self.log[-50:],
		}
