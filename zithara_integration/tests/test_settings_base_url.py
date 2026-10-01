# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Zithara Settings: Base URL rules (https, or a local mock in developer mode)."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from zithara_integration.tests.zithara_fixtures import setup_zithara

LOCAL_MOCK = "http://127.0.0.1:9099"


class TestZitharaSettings(IntegrationTestCase):
	"""Base URL validation."""

	def setUp(self):
		"""Start from enabled, live-mode settings."""
		setup_zithara()

	def tearDown(self):
		"""Undo settings changes."""
		frappe.db.rollback()

	def test_local_mock_allowed_in_developer_mode(self):
		"""http://127.0.0.1 / localhost is accepted for the local mock on a developer-mode site."""
		with patch.dict(frappe.conf, {"developer_mode": 1}):
			for url in (LOCAL_MOCK, "http://localhost:9099/"):
				settings = self.__save_base_url(url)
				self.assertEqual(settings.base_url, url.rstrip("/"))

	def test_local_mock_rejected_without_developer_mode(self):
		"""Plain http is never accepted on a production-style site."""
		with patch.dict(frappe.conf, {"developer_mode": 0}):
			with self.assertRaises(frappe.ValidationError):
				self.__save_base_url(LOCAL_MOCK)

	def test_remote_http_rejected(self):
		"""Plain http to any other host is rejected even in developer mode."""
		with patch.dict(frappe.conf, {"developer_mode": 1}):
			with self.assertRaises(frappe.ValidationError):
				self.__save_base_url("http://pos-api.zithara.com")

	def __save_base_url(self, url: str):
		"""
		Save the settings with a Base URL.

		Parameters:
		        url (str, required): Base URL to save.

		Returns:
		        Document: The saved Zithara Settings.
		"""
		settings = frappe.get_single("Zithara Settings")
		settings.base_url = url
		settings.test_mode = 0
		settings.save()
		return settings
