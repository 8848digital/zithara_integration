# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

from frappe.model.document import Document

from zithara_integration.zithara_core.doctype.zithara_store.zithara_store_utils import (
	after_store_update,
	validate_store,
)


class ZitharaStore(Document):
	"""A store as a Zithara merchant: its ERPNext store, credentials and status."""

	def validate(self):
		"""
		Validate the store link and derive the status from the credentials.

		Returns:
		        None
		"""
		validate_store(self)

	def on_update(self):
		"""
		Forget cached Zithara tokens when the credentials change.

		Returns:
		        None
		"""
		after_store_update(self)
