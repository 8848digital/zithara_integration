# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Store statuses, credential checks, approval, credential requests and settings rules."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from zithara_integration.tests.zithara_fixtures import (
	CLIENT,
	STORE,
	fresh_store,
	run_jobs_inline,
	setup_zithara,
	token_reply,
	zithara_reply,
)
from zithara_integration.zithara_core.services.store_credentials import (
	StoreCredentials,
	request_credentials,
)

SENDMAIL = "zithara_integration.zithara_core.services.store_credentials.frappe.sendmail"


def new_store(code: str = "ZT-NEW", **values):
	"""
	Insert a Zithara Store.

	Parameters:
	        code (str, optional): Store code.
	        **values: Other fields.

	Returns:
	        Document: The store.
	"""
	return fresh_store(code, **values)


class TestStoreCredentials(IntegrationTestCase):
	"""Credential lifecycle of a Zithara Store."""

	def setUp(self):
		"""
		Enable Zithara.

		Returns:
		        None
		"""
		setup_zithara(zithara_contact_email="pos@zithara.example")

	def tearDown(self):
		"""
		Stop all patches.

		Returns:
		        None
		"""
		patch.stopall()

	def test_status_follows_credentials(self):
		"""No credentials -> Awaiting; credentials typed in -> Not Verified."""
		store = new_store()
		self.assertEqual(store.status, "Awaiting Credentials")

		store.update({"client_id": "id-1", "client_secret": "secret-1"})
		store.save()
		self.assertEqual((store.status, store.credentials_source), ("Not Verified", "Manual"))

	def test_check_puts_manual_store_live(self):
		"""Credentials typed in by an admin go live once Zithara accepts them."""
		patch(f"{CLIENT}.get", return_value=token_reply()).start()
		store = new_store(client_id="id-1", client_secret="secret-1")

		self.assertTrue(StoreCredentials(store.name).verify())
		store.reload()
		self.assertEqual(store.status, "Active")
		self.assertTrue(store.last_verified_on)

	def test_rejected_credentials(self):
		"""Credentials Zithara rejects mark the store invalid with the reason."""
		patch(f"{CLIENT}.get", return_value=zithara_reply(401, {"message": "unknown client"})).start()
		store = new_store(client_id="id-1", client_secret="wrong")

		self.assertFalse(StoreCredentials(store.name).verify())
		store.reload()
		self.assertEqual(store.status, "Invalid Credentials")
		self.assertIn("unknown client", store.last_error)

	def test_status_cannot_be_forged(self):
		"""Status and other system fields ignore edits from the form or API."""
		store = new_store()
		store.update({"status": "Active", "approved_by": "Administrator"})
		store.save()
		self.assertEqual((store.status, store.approved_by), ("Awaiting Credentials", None))

	def test_changed_credentials_need_a_new_check(self):
		"""Changing the secret of a live store takes it back to Not Verified."""
		store = frappe.get_doc("Zithara Store", STORE)
		self.assertEqual(store.status, "Active")
		store.client_secret = "rotated-secret"
		store.save()
		self.assertEqual(store.status, "Not Verified")

	def test_disable_and_enable(self):
		"""Disabling stops a store; enabling needs a new check."""
		store = frappe.get_doc("Zithara Store", STORE)
		store.disabled = 1
		store.save()
		self.assertEqual(store.status, "Disabled")
		store.disabled = 0
		store.save()
		self.assertEqual(store.status, "Not Verified")

	def test_one_zithara_store_per_erpnext_store(self):
		"""The same ERPNext store cannot be linked twice."""
		company = frappe.defaults.get_global_default("company")
		new_store("ZT-A", reference_doctype="Company", reference_name=company)
		with self.assertRaises(frappe.ValidationError):
			new_store("ZT-B", reference_doctype="Company", reference_name=company)

	def test_approval_only_for_pending_stores(self):
		"""Approve works only on stores pending approval."""
		with self.assertRaises(frappe.ValidationError):
			StoreCredentials(STORE).approve()

	def test_request_credentials_email(self):
		"""The request goes to Zithara's contact, linked to the store for reply matching."""
		sendmail = patch(SENDMAIL).start()
		store = new_store(store_name="Mall Road")
		request_credentials(store.name)

		kwargs = sendmail.call_args.kwargs
		self.assertEqual(kwargs["recipients"], ["pos@zithara.example"])
		self.assertEqual(
			(kwargs["reference_doctype"], kwargs["reference_name"]), ("Zithara Store", store.name)
		)
		self.assertIn("ZT-NEW", kwargs["subject"])
		self.assertTrue(frappe.db.get_value("Zithara Store", store.name, "credentials_requested_on"))

	def test_request_needs_contact_email(self):
		"""Without a Zithara contact email the request is refused."""
		setup_zithara(zithara_contact_email=None)
		with self.assertRaises(frappe.ValidationError):
			request_credentials(new_store().name)

	def test_new_erpnext_store_is_onboarded(self):
		"""A new record of the Store DocType gets a Zithara Store and a request email."""
		setup_zithara(
			store_doctype="Warehouse",
			invoice_store_field="set_warehouse",
			request_credentials_automatically=1,
			zithara_contact_email="pos@zithara.example",
		)
		jobs = run_jobs_inline()
		sendmail = patch(SENDMAIL).start()
		company = frappe.defaults.get_global_default("company")
		warehouse = frappe.get_doc(
			{"doctype": "Warehouse", "warehouse_name": "_ZT New Store", "company": company}
		).insert()
		jobs.stop()

		store = frappe.get_doc("Zithara Store", {"reference_name": warehouse.name})
		self.assertEqual((store.reference_doctype, store.status), ("Warehouse", "Awaiting Credentials"))
		sendmail.assert_called_once()

	def test_settings_validation(self):
		"""Store field must exist on invoices; patterns must be valid with a capture group."""
		with self.assertRaises(frappe.ValidationError):
			setup_zithara(invoice_store_field="no_such_field")
		with self.assertRaises(frappe.ValidationError):
			setup_zithara(client_id_pattern="client id: (")
		with self.assertRaises(frappe.ValidationError):
			setup_zithara(client_secret_pattern="secret: \\S+")
