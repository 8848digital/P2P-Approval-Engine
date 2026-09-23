# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from approval_engine.vendor_portal.doctype.vendor_portal_settings.vendor_portal_settings import (
	DEFAULT_DOCTYPES,
	seed_default_settings,
)

# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]


class IntegrationTestVendorPortalSettings(IntegrationTestCase):
	"""
	Integration tests for VendorPortalSettings.
	Use this class for testing interactions between multiple components.
	"""

	def setUp(self) -> None:
		"""Snapshot the Single's current `doctypes` rows so each test can
		restore them, since Vendor Portal Settings is a Single and tests
		mutate the one shared document rather than an insert/rollback of
		their own record."""
		settings = frappe.get_single("Vendor Portal Settings")
		self._original_doctypes = [row.as_dict() for row in settings.doctypes]

	def tearDown(self) -> None:
		"""Restore the Single's `doctypes` rows to what they were before
		the test, so this test doesn't leave the shared Vendor Portal
		Settings document altered for the rest of the suite/site."""
		settings = frappe.get_single("Vendor Portal Settings")
		settings.set("doctypes", self._original_doctypes)
		with patch("frappe.db.commit"):
			settings.save(ignore_permissions=True)

	def test_seed_default_settings_populates_when_empty(self) -> None:
		"""
		seed_default_settings() appends the three default rows
		(Purchase Order, Purchase Invoice, Supplier) when no Document
		Types are configured yet.
		"""
		settings = frappe.get_single("Vendor Portal Settings")
		settings.set("doctypes", [])
		with patch("frappe.db.commit"):
			settings.save(ignore_permissions=True)

		# seed_default_settings() commits internally -- patched out so the
		# test's own transaction/savepoint still controls rollback.
		with patch("frappe.db.commit"):
			seed_default_settings()

		settings.reload()
		self.assertEqual(len(settings.doctypes), len(DEFAULT_DOCTYPES))
		self.assertEqual(
			{row.document_type for row in settings.doctypes},
			{row["document_type"] for row in DEFAULT_DOCTYPES},
		)

	def test_seed_default_settings_is_idempotent(self) -> None:
		"""
		A second call to seed_default_settings() is a no-op once rows
		already exist -- it must never duplicate the default rows.
		"""
		settings = frappe.get_single("Vendor Portal Settings")
		settings.set("doctypes", [])
		with patch("frappe.db.commit"):
			settings.save(ignore_permissions=True)
			seed_default_settings()
			seed_default_settings()

		settings.reload()
		self.assertEqual(len(settings.doctypes), len(DEFAULT_DOCTYPES))

	def test_seed_default_settings_skips_when_already_configured(self) -> None:
		"""
		seed_default_settings() does nothing (no save/commit) when
		`doctypes` is already non-empty, regardless of what's configured
		there -- an admin's own configuration is never overwritten.
		"""
		settings = frappe.get_single("Vendor Portal Settings")
		settings.set("doctypes", [])
		settings.append(
			"doctypes",
			{
				"document_type": "ToDo",
				"route": "custom-route",
				"party_fieldname": "owner",
			},
		)
		with patch("frappe.db.commit"):
			settings.save(ignore_permissions=True)

		seed_default_settings()

		settings.reload()
		self.assertEqual(len(settings.doctypes), 1)
		self.assertEqual(settings.doctypes[0].document_type, "ToDo")
