# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

# Copyright (c) 2026, Satya and Contributors
# See license.txt
"""Coverage for KYCValidationRun.recompute_summary() -- part of issue
#10's "KYC validation run ... lifecycle" test-coverage ask.

Called against a lightweight frappe._dict standing in for `self` (only
`logs` is read), rather than inserting a real KYC Validation Run --
avoids needing a live Supplier/vendor fixture chain this environment has
no site to verify against.
"""

import frappe
from frappe.tests import UnitTestCase

from approval_engine.settlement.doctype.kyc_validation_run.kyc_validation_run import (
	KYCValidationRun,
)

EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = []


def _run(statuses):
	logs = [frappe._dict(status=s) for s in statuses]
	return frappe._dict(logs=logs)


class TestRecomputeSummary(UnitTestCase):
	def test_no_logs_is_failed(self):
		run = _run([])
		KYCValidationRun.recompute_summary(run)
		self.assertEqual((run.total_checks, run.success_count, run.failed_count), (0, 0, 0))
		self.assertEqual(run.overall_status, "Failed")

	def test_all_success_is_success(self):
		run = _run(["Success", "Success"])
		KYCValidationRun.recompute_summary(run)
		self.assertEqual((run.total_checks, run.success_count, run.failed_count), (2, 2, 0))
		self.assertEqual(run.overall_status, "Success")

	def test_all_failed_is_failed(self):
		run = _run(["Failed", "Error"])
		KYCValidationRun.recompute_summary(run)
		self.assertEqual((run.total_checks, run.success_count, run.failed_count), (2, 0, 2))
		self.assertEqual(run.overall_status, "Failed")

	def test_mixed_is_partial(self):
		run = _run(["Success", "Failed", "Skipped"])
		KYCValidationRun.recompute_summary(run)
		self.assertEqual((run.total_checks, run.success_count, run.failed_count), (3, 1, 1))
		self.assertEqual(run.overall_status, "Partial")

	def test_skipped_counts_toward_total_but_not_success_or_failed(self):
		run = _run(["Success", "Skipped"])
		KYCValidationRun.recompute_summary(run)
		self.assertEqual((run.total_checks, run.success_count, run.failed_count), (2, 1, 0))
		# 1 success out of 2 total -> Partial, even though the non-success
		# row is "Skipped" rather than an actual failure.
		self.assertEqual(run.overall_status, "Partial")
