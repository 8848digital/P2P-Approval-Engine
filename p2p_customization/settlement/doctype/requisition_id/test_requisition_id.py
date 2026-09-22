# Copyright (c) 2026, Satya and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]


class IntegrationTestRequisitionID(IntegrationTestCase):
	"""
	Integration tests for RequisitionID.
	Use this class for testing interactions between multiple components.
	"""

	def test_create_requisition_id(self) -> None:
		"""
		Creating a Requisition ID record persists the given value, names
		the document after it (autoname: field:requisition_no), and
		defaults `block_id` to unchecked.
		"""
		doc = frappe.get_doc(doctype="Requisition ID", requisition_no="REQ-TEST-0001")
		doc.insert()

		self.assertEqual(doc.name, "REQ-TEST-0001")
		self.assertEqual(doc.requisition_no, "REQ-TEST-0001")
		self.assertEqual(doc.block_id, 0)

	def test_duplicate_requisition_no_not_allowed(self) -> None:
		"""
		A second Requisition ID record with the same `requisition_no`
		value is rejected by the field's uniqueness constraint.
		"""
		frappe.get_doc(doctype="Requisition ID", requisition_no="REQ-TEST-0002").insert()

		duplicate = frappe.get_doc(doctype="Requisition ID", requisition_no="REQ-TEST-0002")

		self.assertRaises((frappe.DuplicateEntryError, frappe.UniqueValidationError), duplicate.insert)

	def test_block_id_can_be_set(self) -> None:
		"""
		`block_id` can be explicitly checked at creation time, matching
		its documented purpose of blocking the Requisition ID once the
		related BRN is submitted.
		"""
		doc = frappe.get_doc(doctype="Requisition ID", requisition_no="REQ-TEST-0003", block_id=1)
		doc.insert()

		self.assertEqual(doc.block_id, 1)
