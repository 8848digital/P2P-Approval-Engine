# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

# Copyright (c) 2026, Satya and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]


class IntegrationTestNatureOfTransaction(IntegrationTestCase):
	"""
	Integration tests for NatureOfTransaction.
	Use this class for testing interactions between multiple components.
	"""

	def test_create_nature_of_transaction(self) -> None:
		"""
		Creating a Nature Of Transaction record persists the given value
		and names the document after it (autoname: field:nature_of_transition).
		"""
		doc = frappe.get_doc(doctype="Nature Of Transaction", nature_of_transition="Test Advance")
		doc.insert()

		self.assertEqual(doc.name, "Test Advance")
		self.assertEqual(doc.nature_of_transition, "Test Advance")

	def test_duplicate_nature_of_transition_not_allowed(self) -> None:
		"""
		A second Nature Of Transaction record with the same
		`nature_of_transition` value is rejected by the field's
		uniqueness constraint.
		"""
		frappe.get_doc(doctype="Nature Of Transaction", nature_of_transition="Test Settlement").insert()

		duplicate = frappe.get_doc(
			doctype="Nature Of Transaction", nature_of_transition="Test Settlement"
		)

		self.assertRaises((frappe.DuplicateEntryError, frappe.UniqueValidationError), duplicate.insert)
