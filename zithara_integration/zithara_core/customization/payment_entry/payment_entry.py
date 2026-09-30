# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""doc_events for Payment Entry: a payment can complete an invoice's payment."""

from zithara_integration.zithara_core.services.order_sync import OrderSync


def on_submit(doc, method=None):
	"""
	Send invoices this payment settles in full.

	Parameters:
	        doc (Document, required): The submitted Payment Entry.
	        method (str, optional): Hook event name passed by Frappe.

	Returns:
	        None
	"""
	OrderSync().on_payment_submit(doc)
