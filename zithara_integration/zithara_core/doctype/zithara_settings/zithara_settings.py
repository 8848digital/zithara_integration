# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

from frappe.model.document import Document

from zithara_integration.zithara_core.doctype.zithara_settings.zithara_settings_utils import (
	validate_settings,
)


class ZitharaSettings(Document):
	"""Zithara connection, store mapping, sync options and credential-email rules."""

	def validate(self):
		"""
		Validate the connection, store mapping and email patterns.

		Returns:
		        None
		"""
		validate_settings(self)
