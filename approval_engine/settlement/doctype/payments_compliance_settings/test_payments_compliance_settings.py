# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import frappe
from frappe.tests import IntegrationTestCase

EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = []


class IntegrationTestPaymentsComplianceSettings(IntegrationTestCase):
	"""
	Integration tests for PaymentsComplianceSettings.validate()'s MSME
	ageing-bucket ordering check. Each test builds the Single in memory via
	frappe.get_single() and calls .validate() directly WITHOUT .save() --
	so nothing is ever written back to the real site-wide Single record,
	and no transaction-rollback/fixture cleanup is needed either way.
	"""

	def test_default_buckets_are_valid(self):
		# Class defaults (5, 14, 30, 45) must satisfy the app's own
		# ordering rule, or every site using the untouched defaults would
		# be broken.
		doc = frappe.get_single("Payments Compliance Settings")
		doc.immediate_due_days = None
		doc.bucket_2_end_days = None
		doc.bucket_3_end_days = None
		doc.bucket_4_end_days = None
		doc.validate()  # must not raise

	def test_strictly_increasing_buckets_pass(self):
		doc = frappe.get_single("Payments Compliance Settings")
		doc.immediate_due_days = 5
		doc.bucket_2_end_days = 14
		doc.bucket_3_end_days = 30
		doc.bucket_4_end_days = 45
		doc.validate()  # must not raise

	def test_non_increasing_buckets_rejected(self):
		doc = frappe.get_single("Payments Compliance Settings")
		doc.immediate_due_days = 10
		doc.bucket_2_end_days = 10  # not strictly greater than bucket 1
		doc.bucket_3_end_days = 30
		doc.bucket_4_end_days = 45
		self.assertRaises(frappe.ValidationError, doc.validate)

	def test_out_of_order_buckets_rejected(self):
		doc = frappe.get_single("Payments Compliance Settings")
		doc.immediate_due_days = 30
		doc.bucket_2_end_days = 14  # earlier than bucket 1
		doc.bucket_3_end_days = 45
		doc.bucket_4_end_days = 60
		self.assertRaises(frappe.ValidationError, doc.validate)
