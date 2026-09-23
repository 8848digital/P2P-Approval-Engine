# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]


class IntegrationTestPortalSectionConfig(IntegrationTestCase):
	"""
	Integration tests for PortalSectionConfig. Portal Section Config is a
	child-table-only doctype (`istable`: 1) with no parent of its own
	other than Vendor Portal Settings' `doctypes` field, so every test
	here exercises it through that Single, restoring the Single's rows
	afterwards.
	"""

	def setUp(self) -> None:
		"""Snapshot Vendor Portal Settings' current `doctypes` rows so
		each test can restore them afterwards."""
		settings = frappe.get_single("Vendor Portal Settings")
		self._original_doctypes = [row.as_dict() for row in settings.doctypes]

	def tearDown(self) -> None:
		"""Restore Vendor Portal Settings' `doctypes` rows to what they
		were before the test."""
		settings = frappe.get_single("Vendor Portal Settings")
		settings.set("doctypes", self._original_doctypes)
		with patch("frappe.db.commit"):
			settings.save(ignore_permissions=True)

	def test_document_type_and_route_are_mandatory(self) -> None:
		"""
		A row with no `document_type`/`route` is rejected -- both fields
		are `reqd: 1` on Portal Section Config with no default.
		"""
		settings = frappe.get_single("Vendor Portal Settings")
		settings.append("doctypes", {"label": "Missing required fields"})

		self.assertRaises(frappe.MandatoryError, settings.save, ignore_permissions=True)

	def test_party_fieldname_defaults_to_supplier(self) -> None:
		"""
		A row with no explicit `party_fieldname` falls back to the
		field's own default ("supplier") rather than being left blank.
		"""
		settings = frappe.get_single("Vendor Portal Settings")
		row = settings.append(
			"doctypes",
			{
				"document_type": "ToDo",
				"route": "test-party-fieldname-default",
			},
		)

		self.assertEqual(row.party_fieldname, "supplier")

	def test_route_must_be_unique(self) -> None:
		"""
		`route` is `unique: 1` on Portal Section Config -- a Table
		doctype's rows live in one flat DB table, so this uniqueness is
		enforced across every row regardless of which parent it belongs
		to, and a duplicate route is rejected on save.
		"""
		settings = frappe.get_single("Vendor Portal Settings")
		settings.append(
			"doctypes",
			{
				"document_type": "ToDo",
				"route": "test-duplicate-route",
				"party_fieldname": "owner",
			},
		)
		settings.append(
			"doctypes",
			{
				"document_type": "ToDo",
				"route": "test-duplicate-route",
				"party_fieldname": "owner",
			},
		)

		with patch("frappe.db.commit"):
			self.assertRaises(
				(frappe.UniqueValidationError, frappe.DuplicateEntryError),
				settings.save,
				ignore_permissions=True,
			)
