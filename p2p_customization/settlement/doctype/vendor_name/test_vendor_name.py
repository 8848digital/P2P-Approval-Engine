# Copyright (c) 2026, Satya and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]


class IntegrationTestVendorName(IntegrationTestCase):
	"""
	Integration tests for VendorName.
	Use this class for testing interactions between multiple components.
	"""

	def test_create_vendor_name(self) -> None:
		"""
		Creating a Vendor Name record persists the given value and names
		the document after it (autoname: field:vendor).
		"""
		doc = frappe.get_doc(doctype="Vendor Name", vendor="Test Vendor One")
		doc.insert()

		self.assertEqual(doc.name, "Test Vendor One")
		self.assertEqual(doc.vendor, "Test Vendor One")

	def test_duplicate_vendor_not_allowed(self) -> None:
		"""
		A second Vendor Name record with the same `vendor` value is
		rejected by the field's uniqueness constraint.
		"""
		frappe.get_doc(doctype="Vendor Name", vendor="Test Vendor Two").insert()

		duplicate = frappe.get_doc(doctype="Vendor Name", vendor="Test Vendor Two")

		self.assertRaises((frappe.DuplicateEntryError, frappe.UniqueValidationError), duplicate.insert)
