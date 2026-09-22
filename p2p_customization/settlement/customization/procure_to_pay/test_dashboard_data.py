# Copyright (c) 2026, p2p_customization
# See license.txt
"""Coverage for the Payments Compliance dashboard's workflow-mapping
bucketing logic (issue #9's "settings/workflow-mapping validation logic"
plan item) -- the actual validation isn't on the Workflow State Mapping
child doctype itself (a plain stub), it's how dashboard_data.py applies
those rows. All pure-logic, no DB needed.
"""

import frappe
from frappe.tests import UnitTestCase

from p2p_customization.settlement.customization.procure_to_pay.dashboard_data import (
	APPROVAL_TARGET_KEYS,
	PAYMENT_TARGET_KEYS,
	_docstatus_bucket,
	_get_state_mapping,
	_payment_order_bucket,
	_resolve_bucket,
)


def _settings_with_mapping(rows):
	"""A minimal settings-like object exposing .get("workflow_state_mapping")."""
	return frappe._dict(workflow_state_mapping=[frappe._dict(r) for r in rows])


class TestGetStateMapping(UnitTestCase):
	def test_filters_to_requested_doctype_only(self):
		settings = _settings_with_mapping(
			[
				{
					"reference_doctype": "Purchase Order",
					"workflow_state": "Approved",
					"status_bucket": "Approved",
				},
				{"reference_doctype": "BRN", "workflow_state": "Approved", "status_bucket": "Rejected"},
			]
		)
		mapping = _get_state_mapping("Purchase Order", settings)
		self.assertEqual(mapping, {"approved": "Approved"})

	def test_lowercases_workflow_state_key(self):
		settings = _settings_with_mapping(
			[{"reference_doctype": "BRN", "workflow_state": "Pending Approval", "status_bucket": "Pending"}]
		)
		mapping = _get_state_mapping("BRN", settings)
		self.assertEqual(mapping, {"pending approval": "Pending"})

	def test_skips_rows_missing_state_or_bucket(self):
		settings = _settings_with_mapping(
			[
				{"reference_doctype": "BRN", "workflow_state": "", "status_bucket": "Approved"},
				{"reference_doctype": "BRN", "workflow_state": "Approved", "status_bucket": ""},
			]
		)
		self.assertEqual(_get_state_mapping("BRN", settings), {})

	def test_no_rows_for_doctype_returns_empty(self):
		settings = _settings_with_mapping([])
		self.assertEqual(_get_state_mapping("BRN", settings), {})


class TestDocstatusBucket(UnitTestCase):
	def test_draft_is_pending(self):
		self.assertEqual(_docstatus_bucket(0, APPROVAL_TARGET_KEYS), "Pending")

	def test_submitted_is_final(self):
		self.assertEqual(_docstatus_bucket(1, APPROVAL_TARGET_KEYS), "Approved")

	def test_cancelled_is_reject(self):
		self.assertEqual(_docstatus_bucket(2, APPROVAL_TARGET_KEYS), "Rejected")


class TestPaymentOrderBucket(UnitTestCase):
	def test_cancelled_always_failed_regardless_of_status(self):
		# Cancellation overrides even a status string that would otherwise
		# map to Processed -- see the function's own docstring.
		self.assertEqual(_payment_order_bucket("Approved", docstatus=2), "Failed")

	def test_known_status_maps_case_insensitively(self):
		self.assertEqual(_payment_order_bucket("Approved", docstatus=1), "Processed")
		self.assertEqual(_payment_order_bucket("PENDING APPROVAL", docstatus=1), "Pending")

	def test_unrecognised_status_returns_none(self):
		self.assertIsNone(_payment_order_bucket("Some New Status", docstatus=1))

	def test_blank_status_returns_none(self):
		self.assertIsNone(_payment_order_bucket("", docstatus=0))
		self.assertIsNone(_payment_order_bucket(None, docstatus=0))


class TestResolveBucket(UnitTestCase):
	"""_resolve_bucket is the single dispatcher every dashboard count and
	click-through filter goes through -- see its own docstring for the
	full precedence table this exercises."""

	def test_mapping_match_wins(self):
		mapping = {"approved": "Approved"}
		bucket, source = _resolve_bucket(
			"Purchase Order",
			"Approved",
			docstatus=1,
			target_keys=APPROVAL_TARGET_KEYS,
			mapping=mapping,
			use_mapping=True,
		)
		self.assertEqual((bucket, source), ("Approved", "mapping"))

	def test_mapping_active_but_cancelled_overrides_match(self):
		# Real scenario from the module docstring: a state string mapped to
		# "Approved" still sitting on a docstatus=2 row must not count as
		# Approved.
		mapping = {"approved": "Approved"}
		bucket, source = _resolve_bucket(
			"Purchase Order",
			"Approved",
			docstatus=2,
			target_keys=APPROVAL_TARGET_KEYS,
			mapping=mapping,
			use_mapping=True,
		)
		self.assertEqual((bucket, source), ("Rejected", "cancelled_override"))

	def test_mapping_active_but_state_unmapped_falls_back_to_docstatus(self):
		mapping = {"approved": "Approved"}
		bucket, source = _resolve_bucket(
			"Purchase Order",
			"Some Unmapped State",
			docstatus=1,
			target_keys=APPROVAL_TARGET_KEYS,
			mapping=mapping,
			use_mapping=True,
		)
		self.assertEqual((bucket, source), ("Approved", "unmapped_fallback_to_docstatus"))

	def test_payment_order_uses_status_field_when_no_mapping(self):
		bucket, source = _resolve_bucket(
			"Payment Order",
			"Initiated",
			docstatus=1,
			target_keys=PAYMENT_TARGET_KEYS,
			mapping={},
			use_mapping=False,
		)
		self.assertEqual((bucket, source), ("Processed", "status_field"))

	def test_payment_order_cancelled_status_overrides(self):
		bucket, source = _resolve_bucket(
			"Payment Order",
			"Initiated",
			docstatus=2,
			target_keys=PAYMENT_TARGET_KEYS,
			mapping={},
			use_mapping=False,
		)
		self.assertEqual((bucket, source), ("Failed", "cancelled_override"))

	def test_payment_order_unrecognised_status_falls_back_to_docstatus(self):
		bucket, source = _resolve_bucket(
			"Payment Order",
			"Some New Status",
			docstatus=1,
			target_keys=PAYMENT_TARGET_KEYS,
			mapping={},
			use_mapping=False,
		)
		self.assertEqual((bucket, source), ("Processed", "unrecognised_status_fallback_to_docstatus"))

	def test_plain_doctype_no_mapping_uses_docstatus_only(self):
		bucket, source = _resolve_bucket(
			"Purchase Invoice",
			None,
			docstatus=0,
			target_keys=APPROVAL_TARGET_KEYS,
			mapping={},
			use_mapping=False,
		)
		self.assertEqual((bucket, source), ("Pending", "docstatus_only"))
