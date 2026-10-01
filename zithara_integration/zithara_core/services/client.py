# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""HTTP client for the Zithara POS API: per-store access token + retrying requests."""

import time
from urllib.parse import quote

import requests

import frappe
from frappe import _

from zithara_integration.zithara_core.services import test_mode
from zithara_integration.zithara_core.services.client_response import ZitharaError, parse_response

TOKEN_PATH = "/v1/generate-access-token"
CREATE_ORDER_PATH = "/v1/order"
CANCEL_ORDER_PATH = "/v1/order/cancel"
GET_ORDER_PATH = "/v1/order/{platform_order_id}"
TOKEN_CACHE_PREFIX = "zithara_integration:token:"
# Refresh a little before Zithara's expiry so no call goes out on a dying token.
TOKEN_BUFFER_SECONDS = 300
DEFAULT_TOKEN_LIFETIME = 3600
# 4xx never self-heals, so only transient server errors are retried.
RETRY_STATUSES = (500, 502, 503, 504)
RETRY_DELAY_SECONDS = 2


class ZitharaClient:
	"""
	Zithara POS API wrapper for one store. Each store is its own Zithara merchant
	with its own client id/secret, so tokens are cached per client id.
	"""

	def __init__(self, client_id: str, client_secret: str):
		"""
		Load connection settings and keep the store's credentials.

		Parameters:
		        client_id (str, required): The store's Zithara client id.
		        client_secret (str, required): The store's Zithara client secret.

		Returns:
		        None
		"""
		settings = frappe.get_cached_doc("Zithara Settings")
		self.base_url = (settings.base_url or "").rstrip("/")
		self.timeout = settings.timeout_seconds or 30
		self.max_retries = settings.max_retries if settings.max_retries is not None else 2
		self.test_mode = bool(settings.test_mode)
		self.client_id = (client_id or "").strip()
		self.client_secret = (client_secret or "").strip()

		if not (self.client_id and self.client_secret):
			frappe.throw(_("Zithara client id and secret are required"))
		if not (self.base_url or self.test_mode):
			frappe.throw(_("Set the Base URL in Zithara Settings"))

	@classmethod
	def for_store(cls, store: str) -> "ZitharaClient":
		"""
		Build a client from a Zithara Store's saved credentials.

		Parameters:
		        store (str, required): Zithara Store name.

		Returns:
		        ZitharaClient: Client authenticated as that store.
		"""
		store_doc = frappe.get_doc("Zithara Store", store)
		return cls(store_doc.client_id, store_doc.get_password("client_secret", raise_exception=False))

	def test_connection(self) -> str:
		"""
		Ask Zithara for a fresh access token to prove the credentials work.

		Returns:
		        str: The access token.
		"""
		return self.__token(force=True)

	def create_order(self, payload: dict) -> dict:
		"""
		Send an order (customer, lines, payments) to Zithara.

		Parameters:
		        payload (dict, required): Create Order body.

		Returns:
		        dict: Zithara reply, e.g. {"status": 201, "orderId": "702355"}.
		"""
		return self.__request("POST", CREATE_ORDER_PATH, payload)

	def cancel_order(self, payload: dict) -> dict:
		"""
		Cancel a whole order or some of its lines on Zithara.

		Parameters:
		        payload (dict, required): {"platform_order_id", "type": "complete" | "partial",
		                "platform_line_item_ids": [...] (partial only)}.

		Returns:
		        dict: Zithara reply.
		"""
		return self.__request("POST", CANCEL_ORDER_PATH, payload)

	def get_order(self, platform_order_id: str) -> dict | list:
		"""
		Read an order back from Zithara (no side effects).

		Parameters:
		        platform_order_id (str, required): Our order id, i.e. the invoice name.

		Returns:
		        dict | list: Zithara reply (an array holding one order).
		"""
		path = GET_ORDER_PATH.format(platform_order_id=quote(platform_order_id, safe=""))
		return self.__request("GET", path)

	def call(
		self, method: str, path: str, payload: dict | None = None, retry: bool = True
	) -> dict | list:
		"""
		Call any Zithara endpoint as this store (used by the loyalty calls).

		Parameters:
		        method (str, required): "GET" or "POST".
		        path (str, required): Endpoint path, with its query string.
		        payload (dict, optional): JSON body for POST.
		        retry (bool, optional): Retry 5xx. False for calls that must never
		                repeat, e.g. initiate-redemption (each call sends an SMS).

		Returns:
		        dict | list: Parsed success body.
		"""
		return self.__request(method, path, payload, retry)

	def __request(
		self, method: str, path: str, payload: dict | None = None, retry: bool = True
	) -> dict | list:
		"""
		Call Zithara with the store's token. 5xx is retried; a 401 refreshes the
		token once (it can expire before our cached expiry).

		Parameters:
		        method (str, required): "GET" or "POST".
		        path (str, required): Endpoint path.
		        payload (dict, optional): JSON body for POST.
		        retry (bool, optional): Retry 5xx responses.

		Returns:
		        dict | list: Parsed success body.

		Raises:
		        ZitharaError: On any failure after retries.
		"""
		if self.test_mode:
			return test_mode.reply(method, path, payload)

		token_refreshed = False
		attempt = 0
		while True:
			attempt += 1
			response = self.__send(method, path, payload, self.__token(force=token_refreshed))
			if response.status_code == 401 and not token_refreshed:
				token_refreshed = True
				continue
			if retry and response.status_code in RETRY_STATUSES and attempt <= self.max_retries:
				time.sleep(RETRY_DELAY_SECONDS)
				continue
			return parse_response(response)

	def __token(self, force: bool = False) -> str:
		"""
		Return a cached access token, or fetch one. Zithara's quirk: a GET with
		client_id / client_secret as headers (no body, no Basic auth).

		Parameters:
		        force (bool, optional): Ignore the cache and fetch a new token.

		Returns:
		        str: Access token.
		"""
		if self.test_mode:
			return test_mode.TOKEN

		cache_key = f"{TOKEN_CACHE_PREFIX}{self.client_id}"
		cached = None if force else frappe.cache.get_value(cache_key)
		if cached:
			return cached

		try:
			response = requests.get(
				f"{self.base_url}{TOKEN_PATH}",
				headers={"client_id": self.client_id, "client_secret": self.client_secret},
				timeout=self.timeout,
			)
		except requests.RequestException as error:
			raise ZitharaError(0, _("Could not reach Zithara: {0}").format(str(error))) from error

		body = parse_response(response)
		token = body.get("access_token") if isinstance(body, dict) else None
		if not token:
			raise ZitharaError(response.status_code, _("Zithara did not return an access token"), body)

		lifetime = int(body.get("expires_in") or DEFAULT_TOKEN_LIFETIME)
		frappe.cache.set_value(cache_key, token, expires_in_sec=max(lifetime - TOKEN_BUFFER_SECONDS, 60))
		return token

	def __send(self, method: str, path: str, payload: dict | None, token: str):
		"""
		Send one HTTP request. Zithara wants the raw token, not "Bearer <token>".

		Parameters:
		        method (str, required): "GET" or "POST".
		        path (str, required): Endpoint path.
		        payload (dict, optional): JSON body.
		        token (str, required): Access token.

		Returns:
		        Response: The raw HTTP response.
		"""
		try:
			return requests.request(
				method,
				f"{self.base_url}{path}",
				headers={"Authorization": token, "Accept": "application/json"},
				json=payload if method != "GET" else None,
				timeout=self.timeout,
			)
		except requests.RequestException as error:
			raise ZitharaError(0, _("Could not reach Zithara: {0}").format(str(error))) from error


def clear_cached_token(client_id: str) -> None:
	"""
	Forget a store's cached token (after its credentials change).

	Parameters:
	        client_id (str, required): The store's Zithara client id.

	Returns:
	        None
	"""
	if client_id:
		frappe.cache.delete_value(f"{TOKEN_CACHE_PREFIX}{client_id.strip()}")
