# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Zithara HTTP client: token quirks, caching, retries, errors and test mode."""

from unittest.mock import patch

from frappe.tests import IntegrationTestCase

from zithara_integration.tests.zithara_fixtures import (
	CLIENT,
	CLIENT_ID,
	CLIENT_SECRET,
	setup_zithara,
	token_reply,
	zithara_reply,
)
from zithara_integration.zithara_core.services.client import ZitharaClient
from zithara_integration.zithara_core.services.client_response import ZitharaError
from zithara_integration.zithara_core.services.value_format import normalize_phone, product_id

CREATED = {"status": 201, "orderId": "1"}


class TestZitharaClient(IntegrationTestCase):
	"""Client behaviour against a mocked Zithara."""

	def setUp(self):
		"""
		Enable Zithara in live mode with a fresh token cache.

		Returns:
		        None
		"""
		setup_zithara()
		self.client = ZitharaClient(CLIENT_ID, CLIENT_SECRET)

	def tearDown(self):
		"""
		Stop all patches.

		Returns:
		        None
		"""
		patch.stopall()

	def test_token_request_and_raw_authorization(self):
		"""Token: GET with credentials as headers; calls send the raw token (no Bearer)."""
		token = patch(f"{CLIENT}.get", return_value=token_reply()).start()
		api = patch(f"{CLIENT}.request", return_value=zithara_reply(201, CREATED)).start()

		self.client.create_order({"order": {}})
		headers = token.call_args.kwargs["headers"]
		self.assertEqual(headers, {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET})
		self.assertTrue(token.call_args.args[0].endswith("/v1/generate-access-token"))
		self.assertEqual(api.call_args.kwargs["headers"]["Authorization"], "token-123")

	def test_token_is_cached_per_store(self):
		"""Two calls reuse one token."""
		token = patch(f"{CLIENT}.get", return_value=token_reply()).start()
		patch(f"{CLIENT}.request", return_value=zithara_reply(201, CREATED)).start()

		self.client.create_order({})
		self.client.create_order({})
		self.assertEqual(token.call_count, 1)

	def test_expired_token_is_refreshed_once(self):
		"""A 401 fetches a new token and repeats the call once."""
		token = patch(f"{CLIENT}.get", return_value=token_reply()).start()
		patch(
			f"{CLIENT}.request",
			side_effect=[zithara_reply(401, {"message": "expired"}), zithara_reply(201, CREATED)],
		).start()

		self.assertEqual(self.client.create_order({})["orderId"], "1")
		self.assertEqual(token.call_count, 2)

	def test_business_failure_in_200_raises(self):
		"""Zithara's HTTP 200 with success=false is an error."""
		patch(f"{CLIENT}.get", return_value=token_reply()).start()
		patch(
			f"{CLIENT}.request", return_value=zithara_reply(200, {"success": False, "error": "Invalid OTP"})
		).start()

		with self.assertRaises(ZitharaError) as raised:
			self.client.create_order({})
		self.assertIn("Invalid OTP", str(raised.exception))

	def test_rejected_credentials_raise(self):
		"""A token request rejected by Zithara raises with its status."""
		patch(f"{CLIENT}.get", return_value=zithara_reply(401, {"message": "bad client"})).start()
		with self.assertRaises(ZitharaError) as raised:
			self.client.test_connection()
		self.assertEqual(raised.exception.status_code, 401)

	def test_order_id_is_url_encoded(self):
		"""Order ids with slashes are encoded in the path."""
		patch(f"{CLIENT}.get", return_value=token_reply()).start()
		api = patch(f"{CLIENT}.request", return_value=zithara_reply(200, [])).start()

		self.client.get_order("102/JSA/25")
		self.assertTrue(api.call_args.args[1].endswith("/v1/order/102%2FJSA%2F25"))

	def test_test_mode_makes_no_calls(self):
		"""Test Mode answers locally: no token call, no HTTP."""
		setup_zithara(test_mode=1)
		token = patch(f"{CLIENT}.get").start()
		api = patch(f"{CLIENT}.request").start()

		reply = ZitharaClient(CLIENT_ID, CLIENT_SECRET).create_order({})
		self.assertTrue(reply["orderId"].startswith("TEST-"))
		token.assert_not_called()
		api.assert_not_called()

	def test_phone_and_product_id(self):
		"""Phones get the country code; product ids are stable integers."""
		self.assertEqual(normalize_phone("098765 43210", "91"), "919876543210")
		self.assertEqual(normalize_phone("+91 98765 43210", "91"), "919876543210")
		self.assertEqual(normalize_phone("", "91"), "")
		self.assertEqual(product_id("RING-1"), product_id("RING-1"))
		self.assertIsInstance(product_id("RING-1"), int)
