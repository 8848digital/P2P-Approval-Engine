# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from approval_engine.approval_settlement.doctype.faq_master.faq_master_utils import (
	FIELDNAME_RE,
	_parse_options,
)

EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = []


class TestFAQMasterHelpers(UnitTestCase):
	"""Pure-logic helpers from faq_master_utils.py -- no DB needed."""

	def test_parse_options_splits_and_drops_blanks(self):
		self.assertEqual(_parse_options("Yes\nNo\n\n"), ["Yes", "No"])

	def test_parse_options_empty_input(self):
		self.assertEqual(_parse_options(""), [])
		self.assertEqual(_parse_options(None), [])

	def test_fieldname_re_accepts_valid_question_code(self):
		self.assertTrue(FIELDNAME_RE.match("sustainable_goods_percentage"))
		self.assertTrue(FIELDNAME_RE.match("msa_agreement_2"))

	def test_fieldname_re_rejects_invalid_question_code(self):
		self.assertFalse(FIELDNAME_RE.match("Msa_Agreement"))  # uppercase
		self.assertFalse(FIELDNAME_RE.match("2nd_question"))  # leading digit
		self.assertFalse(FIELDNAME_RE.match("has space"))


class IntegrationTestFAQMaster(IntegrationTestCase):
	"""
	Integration tests for FAQMaster's validate() doc_event. Each case here
	fails during validate(), before before_insert/after_insert run, so
	none of these touch Supplier's custom fields or the onboarding web
	form -- safe to run without those side effects landing.
	"""

	def test_invalid_question_code_rejected(self):
		doc = frappe.get_doc(
			doctype="FAQ Master",
			question_code="Not Valid",
			question_label="Test Question",
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_select_field_requires_options(self):
		doc = frappe.get_doc(
			doctype="FAQ Master",
			question_code="test_select_no_options",
			question_label="Test Question",
			field_type="Select",
			options="",
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_expected_answer_must_be_one_of_options(self):
		doc = frappe.get_doc(
			doctype="FAQ Master",
			question_code="test_bad_expected_answer",
			question_label="Test Question",
			field_type="Select",
			options="Yes\nNo",
			expected_answer="Maybe",
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_depends_on_question_cannot_reference_itself(self):
		doc = frappe.get_doc(
			doctype="FAQ Master",
			question_code="test_self_reference",
			question_label="Test Question",
			depends_on_question="test_self_reference",
		)
		self.assertRaises(frappe.ValidationError, doc.insert)
