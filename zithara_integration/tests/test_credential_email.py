# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Zithara's credential emails are read, checked, stored securely and redacted."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from zithara_integration.tests.zithara_fixtures import (
	CLIENT,
	fresh_store,
	run_jobs_inline,
	setup_zithara,
	token_reply,
	zithara_reply,
)
from zithara_integration.zithara_core.services.store_credentials import StoreCredentials

NOTIFY = "zithara_integration.zithara_core.services.credential_email.notify"
BODY = (
	"Hello,<br>Store Code: {store}<br>Client ID: new-client-id<br>Client Secret: n3w-s3cret<br>Thanks"
)


class TestCredentialEmail(IntegrationTestCase):
	"""Incoming Communication -> Zithara Store credentials."""

	def setUp(self):
		"""
		Enable email import for @zithara.com, run jobs inline, accept tokens.

		Returns:
		        None
		"""
		setup_zithara(
			import_credentials_from_email=1, allowed_senders="@zithara.com", require_approval=1
		)
		self.jobs = run_jobs_inline()
		self.token = patch(f"{CLIENT}.get", return_value=token_reply()).start()
		self.notify = patch(NOTIFY).start()
		self.store = fresh_store("ZT-MALL")
		if frappe.db.exists("Zithara Store", "ZT-AIRPORT"):
			frappe.delete_doc("Zithara Store", "ZT-AIRPORT", force=True)

	def tearDown(self):
		"""
		Stop all patches.

		Returns:
		        None
		"""
		patch.stopall()

	def test_credentials_saved_checked_and_redacted(self):
		"""Emailed credentials are stored, checked, held for approval and removed from the email."""
		email = receive(BODY.format(store="ZT-MALL"))
		self.store.reload()

		self.assertEqual(self.store.status, "Pending Approval")
		self.assertEqual(
			(self.store.client_id, self.store.credentials_source), ("new-client-id", "Email")
		)
		self.assertEqual(self.store.get_password("client_secret"), "n3w-s3cret")
		self.assertEqual(self.store.source_email, email.name)
		self.assertNotIn("n3w-s3cret", frappe.db.get_value("Communication", email.name, "content"))
		self.assertEqual(self.token.call_args.kwargs["headers"]["client_id"], "new-client-id")

		StoreCredentials(self.store.name).approve()
		self.store.reload()
		self.assertEqual((self.store.status, self.store.approved_by), ("Active", "Administrator"))

	def test_no_approval_needed(self):
		"""With approval off, checked credentials go live straight away."""
		setup_zithara(
			import_credentials_from_email=1, allowed_senders="@zithara.com", require_approval=0
		)
		receive(BODY.format(store="ZT-MALL"))
		self.assertEqual(frappe.db.get_value("Zithara Store", self.store.name, "status"), "Active")

	def test_unknown_sender_is_ignored(self):
		"""Emails from other senders are never read."""
		receive(BODY.format(store="ZT-MALL"), sender="attacker@example.com")
		self.store.reload()
		self.assertEqual((self.store.status, self.store.client_id), ("Awaiting Credentials", None))
		self.token.assert_not_called()

	def test_reply_to_request_matches_its_store(self):
		"""A reply to our request needs no store line: the thread identifies the store."""
		body = "Client ID: reply-id<br>Client Secret: reply-secret"
		receive(body, reference_doctype="Zithara Store", reference_name=self.store.name)
		self.assertEqual(frappe.db.get_value("Zithara Store", self.store.name, "client_id"), "reply-id")

	def test_unknown_store_creates_one(self):
		"""Credentials for a store we do not know create it, pending approval."""
		receive(BODY.format(store="ZT-AIRPORT"))
		store = frappe.get_doc("Zithara Store", "ZT-AIRPORT")
		self.assertEqual((store.status, store.client_id), ("Pending Approval", "new-client-id"))

	def test_unreadable_email_is_reported(self):
		"""An allowed email without a secret changes nothing and alerts the admins."""
		receive("Store Code: ZT-MALL<br>Client ID: only-id")
		self.store.reload()
		self.assertIsNone(self.store.client_id)
		self.assertIn("Could not read", self.notify.call_args.args[0])

	def test_rejected_emailed_credentials(self):
		"""Emailed credentials that Zithara rejects never go live."""
		self.token.return_value = zithara_reply(401, {"message": "unknown client"})
		receive(BODY.format(store="ZT-MALL"))
		self.assertEqual(
			frappe.db.get_value("Zithara Store", self.store.name, "status"), "Invalid Credentials"
		)


def receive(content: str, sender: str = "onboarding@zithara.com", **values):
	"""
	Insert an incoming email as Frappe's email pull would.

	Parameters:
	        content (str, required): Email HTML.
	        sender (str, optional): Sender address.
	        **values: Other Communication fields.

	Returns:
	        Document: The Communication.
	"""
	return frappe.get_doc(
		{
			"doctype": "Communication",
			"communication_type": "Communication",
			"communication_medium": "Email",
			"sent_or_received": "Received",
			"sender": sender,
			"subject": "Zithara POS credentials",
			"content": content,
			**values,
		}
	).insert(ignore_permissions=True)
