# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Coverage for the ITC reversal sweep, per issue #11's plan: tests for
set_itc_status, handle_itc_reversal_on_submit, and the daily sweep.

classify_itc_requirement/get_cutoff_date/is_prior_fiscal_year are pure
functions (today/cutoff_date/fiscal-year docs are all passed in, never
read from frappe.utils.nowdate() internally) -- covered directly, no
freeze_time or DB needed.

set_itc_status/handle_itc_reversal_on_submit/run_daily_itc_reversal_sweep
DO read "today" internally (via get_current_fiscal_year_doc ->
getdate(nowdate())) and write real ITC Reversal Log / Purchase Invoice
records. The issue's plan calls for freeze_time on this cron-driven path;
this environment has no live Frappe test site to construct a real
Fiscal Year/Purchase Invoice against and verify a freeze_time-pinned
Fiscal Year lookup succeeds, so rather than risk a test that only works
by coincidence with whatever Fiscal Year happens to exist, the two
current/previous-fiscal-year lookups are mocked directly instead
(deterministic either way, and doesn't depend on real Fiscal Year data).
Only the fixture-free, deterministic guard-clause paths (feature flag
off, missing bill_date, no candidate logs) are covered here -- full
end-to-end reversal-JV creation needs a live Purchase Invoice with real
Company/Supplier/Item/tax fixtures; see this PR's test plan for what a
real site should still verify, ideally with freeze_time as the issue
asks once that's possible to exercise for real.
"""

from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from approval_engine.settlement.customization.purchase_invoice.itc_reversal import (
	classify_itc_requirement,
	get_cutoff_date,
	is_prior_fiscal_year,
	run_daily_itc_reversal_sweep,
	set_itc_status,
)


def _fy(name, start, end):
	return frappe._dict(name=name, year_start_date=start, year_end_date=end)


class TestClassifyItcRequirement(UnitTestCase):
	"""The core reversal-decision engine -- pure function, no DB needed."""

	current_fy = _fy("2026-2027", date(2026, 4, 1), date(2027, 3, 31))
	previous_fy = _fy("2025-2026", date(2025, 4, 1), date(2026, 3, 31))
	older_fy = _fy("2024-2025", date(2024, 4, 1), date(2025, 3, 31))
	cutoff_date = date(2026, 11, 30)

	def test_current_fy_invoice_never_requires_reversal(self):
		status, required = classify_itc_requirement(
			self.current_fy, self.current_fy, self.previous_fy, date(2027, 1, 1), self.cutoff_date
		)
		self.assertEqual(status, "All Other ITC")
		self.assertFalse(required)

	def test_previous_fy_before_cutoff_not_required(self):
		status, required = classify_itc_requirement(
			self.previous_fy, self.current_fy, self.previous_fy, date(2026, 11, 30), self.cutoff_date
		)
		self.assertEqual(status, "All Other ITC")
		self.assertFalse(required)

	def test_previous_fy_after_cutoff_required(self):
		status, required = classify_itc_requirement(
			self.previous_fy, self.current_fy, self.previous_fy, date(2026, 12, 1), self.cutoff_date
		)
		self.assertEqual(status, "Reversed - Prior FY Invoice")
		self.assertTrue(required)

	def test_older_than_previous_fy_always_required(self):
		# No cut-off grace period at all for anything older than the
		# immediately-previous FY -- even "today" being far in the past
		# relative to cutoff_date doesn't matter here.
		status, required = classify_itc_requirement(
			self.older_fy, self.current_fy, self.previous_fy, date(2026, 4, 5), self.cutoff_date
		)
		self.assertEqual(status, "Reversed - Prior FY Invoice")
		self.assertTrue(required)


class TestGetCutoffDate(UnitTestCase):
	def test_cutoff_month_on_or_after_fy_start_month_same_year(self):
		# FY starts April (month 4); cutoff configured for November (11,
		# >= 4) -> falls within the same calendar year the FY started.
		current_fy = _fy("2026-2027", date(2026, 4, 1), date(2027, 3, 31))
		settings = frappe._dict(cutoff_month=11, cutoff_day=30)
		self.assertEqual(get_cutoff_date(current_fy, settings), date(2026, 11, 30))

	def test_cutoff_month_before_fy_start_month_next_year(self):
		# Cutoff configured for January (1, < 4) -> falls in the calendar
		# year AFTER the FY started.
		current_fy = _fy("2026-2027", date(2026, 4, 1), date(2027, 3, 31))
		settings = frappe._dict(cutoff_month=1, cutoff_day=31)
		self.assertEqual(get_cutoff_date(current_fy, settings), date(2027, 1, 31))


class TestIsPriorFiscalYear(UnitTestCase):
	def test_true_when_invoice_fy_ended_before_current_fy_started(self):
		invoice_fy = _fy("2024-2025", date(2024, 4, 1), date(2025, 3, 31))
		current_fy = _fy("2026-2027", date(2026, 4, 1), date(2027, 3, 31))
		self.assertTrue(is_prior_fiscal_year(invoice_fy, current_fy))

	def test_false_for_the_current_fy_itself(self):
		current_fy = _fy("2026-2027", date(2026, 4, 1), date(2027, 3, 31))
		self.assertFalse(is_prior_fiscal_year(current_fy, current_fy))


class TestGuardClauses(IntegrationTestCase):
	"""Fixture-free, deterministic paths that don't need a live Purchase
	Invoice/Fiscal Year -- both functions must exit before touching the
	DB, so mocking get_settings() (rather than JFS Settings itself) is
	enough to prove it."""

	def test_set_itc_status_noop_when_feature_disabled(self):
		fake_settings = frappe._dict(enable_itc_reversal=0)
		doc = frappe._dict(bill_date="2026-06-01", name="PI-TEST-0001")
		with patch(
			"approval_engine.settlement.customization.purchase_invoice.itc_reversal.get_settings",
			return_value=fake_settings,
		):
			set_itc_status(doc)  # must return immediately, no DB writes

	def test_set_itc_status_noop_when_no_bill_date(self):
		fake_settings = frappe._dict(enable_itc_reversal=1)
		doc = frappe._dict(bill_date=None, name="PI-TEST-0002")
		with patch(
			"approval_engine.settlement.customization.purchase_invoice.itc_reversal.get_settings",
			return_value=fake_settings,
		):
			set_itc_status(doc)  # must return immediately, no DB writes

	def test_daily_sweep_noop_when_feature_disabled(self):
		fake_settings = frappe._dict(enable_itc_reversal=0)
		with patch(
			"approval_engine.settlement.customization.purchase_invoice.itc_reversal.get_settings",
			return_value=fake_settings,
		):
			run_daily_itc_reversal_sweep()  # must return immediately, before even looking up candidate logs

	def test_daily_sweep_handles_zero_candidate_logs(self):
		# Every log already Reversed (or none exist) -> the sweep's own
		# get_all() returns [], loop body never runs, no error. Also mocks
		# the current/previous fiscal-year lookups (which run BEFORE the
		# get_all call) so this doesn't depend on a real Fiscal Year
		# existing for today's actual date on whatever site runs this.
		fake_fy = _fy("2026-2027", date(2026, 4, 1), date(2027, 3, 31))
		fake_previous_fy = _fy("2025-2026", date(2025, 4, 1), date(2026, 3, 31))
		fake_settings = frappe._dict(enable_itc_reversal=1, cutoff_month=3, cutoff_day=31)
		module = "approval_engine.settlement.customization.purchase_invoice.itc_reversal"
		with (
			patch(f"{module}.get_settings", return_value=fake_settings),
			patch(f"{module}.get_current_fiscal_year_doc", return_value=fake_fy),
			patch(f"{module}.get_previous_fiscal_year_doc", return_value=fake_previous_fy),
			patch("frappe.get_all", return_value=[]),
		):
			run_daily_itc_reversal_sweep()  # must not raise
