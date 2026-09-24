# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Pure-logic tests for the ad-hoc Additional Approver feature.

Covers the parts where subtle bugs hide and that need no database: the reviewer
condition fragments baked into workflow transitions, the generic reviewer
transitions (`_reviewer_intercepts`), the sidebar tier-attribution rule
(`activity._logged_tier`), `resuming_tier`, eligibility, and the record
invariants. The full multi-user runtime flow (approve/reject/hold, role
grant/revoke, dashboard) is exercised end-to-end separately.
"""

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from approval_engine.approval_core import activity
from approval_engine.approval_core.generator import (
    ADDITIONAL_APPROVAL_STATE,
    ADDITIONAL_HOLD_STATE,
    STATE_FOR_TIER,
    additional_role_name,
    resuming_tier,
    _pending_reviewer_cond,
    _reviewer_can_act_cond,
    _reviewer_done_cond,
    _reviewer_intercepts,
)
from approval_engine.approval_core.doctype.additional_approver import (
    additional_approver_utils as U,
)


class UnitTestAdditionalApprover(UnitTestCase):
    """No-database tests for the Additional Approver logic."""

    # ---------------- naming / states ----------------

    def test_additional_role_name(self):
        """The coarse reviewer role is namespaced to the DocType."""
        self.assertEqual(additional_role_name("Purchase Order"),
                         "Purchase Order - Additional Approver")

    def test_state_rename_is_past_tense(self):
        """The post-review resting state reads as completed, not pending."""
        self.assertEqual(ADDITIONAL_APPROVAL_STATE, "Additionally Approved")

    def test_insertable_states_are_the_waiting_tiers(self):
        """A reviewer may only be inserted at a tier's waiting state, never mid-review."""
        self.assertEqual(U.INSERTABLE_STATES, set(STATE_FOR_TIER.values()))
        self.assertNotIn(ADDITIONAL_APPROVAL_STATE, U.INSERTABLE_STATES)
        self.assertNotIn(ADDITIONAL_HOLD_STATE, U.INSERTABLE_STATES)

    # ---------------- condition fragments (baked into transitions) ----------------

    def test_pending_cond_pins_state_and_open_record(self):
        """A pending-reviewer check targets an active, not-yet-acted record at that state."""
        cond = _pending_reviewer_cond("Approved 1")
        self.assertIn("'insert_state': 'Approved 1'", cond)
        self.assertIn("'active': 1", cond)
        self.assertIn("'completed': 0", cond)
        self.assertIn("doc.doctype", cond)
        self.assertIn("doc.name", cond)

    def test_can_act_cond_pins_session_user(self):
        """The reviewer's own action is pinned to the session user."""
        cond = _reviewer_can_act_cond("Pending")
        self.assertIn("'approver': frappe.session.user", cond)
        self.assertIn("'completed': 0", cond)

    def test_can_act_cond_honours_flag(self):
        """Reject/Hold intercepts additionally require the per-record flag."""
        self.assertIn("'can_reject': 1", _reviewer_can_act_cond("Pending", "can_reject"))
        self.assertIn("'can_hold': 1", _reviewer_can_act_cond("Approved 2", "can_hold"))
        self.assertNotIn("can_reject", _reviewer_can_act_cond("Pending"))

    def test_done_cond_requires_completed(self):
        """The resume check requires the reviewer to have completed."""
        cond = _reviewer_done_cond("Approved 2")
        self.assertIn("'insert_state': 'Approved 2'", cond)
        self.assertIn("'completed': 1", cond)

    # ---------------- generic reviewer transitions ----------------

    def test_reviewer_intercepts_cover_every_waiting_state(self):
        """One Approve/Reject/Hold from each waiting state, plus Approve/Reject from the
        reviewer's own hold — all under the coarse additional-approver role."""
        trs = _reviewer_intercepts("Purchase Order")
        role = additional_role_name("Purchase Order")
        self.assertTrue(all(t["allowed"] == role for t in trs))
        # 5 transitions per waiting state (3 from src + 2 from the reviewer hold)
        self.assertEqual(len(trs), 5 * len(STATE_FOR_TIER))

        for src in STATE_FOR_TIER.values():
            self._assert_transition(trs, src, "Approve", ADDITIONAL_APPROVAL_STATE)
            self._assert_transition(trs, src, "Reject", "Rejected")
            self._assert_transition(trs, src, "Hold", ADDITIONAL_HOLD_STATE)
            self._assert_transition(trs, ADDITIONAL_HOLD_STATE, "Approve", ADDITIONAL_APPROVAL_STATE)
            self._assert_transition(trs, ADDITIONAL_HOLD_STATE, "Reject", "Rejected")

    def _assert_transition(self, trs, state, action, next_state):
        """Fail unless a transition state --action--> next_state exists in `trs`."""
        match = any(
            t["state"] == state and t["action"] == action and t["next_state"] == next_state
            for t in trs
        )
        self.assertTrue(match, f"missing transition {state} --{action}--> {next_state}")

    # ---------------- resuming tier (mocked db) ----------------

    def test_resuming_tier_from_reviewer_insert_state(self):
        """The tier that resumes is derived from the reviewer's captured insert_state."""
        doc = SimpleNamespace(doctype="Purchase Order", name="PO-1")
        with patch.object(frappe.db, "get_value", return_value="Approved 1"):
            self.assertEqual(resuming_tier(doc), 2)  # tier acting from "Approved 1"

    def test_resuming_tier_none_when_no_reviewer(self):
        """No completed reviewer -> no resuming tier."""
        doc = SimpleNamespace(doctype="Purchase Order", name="PO-1")
        with patch.object(frappe.db, "get_value", return_value=None):
            self.assertIsNone(resuming_tier(doc))

    # ---------------- sidebar tier attribution (activity._logged_tier) ----------------

    def test_logged_tier_reviewer_move_credits_no_tier(self):
        """A move INTO a reviewer state is the reviewer's own action, not a tier's."""
        self.assertIsNone(activity._logged_tier("Pending", ADDITIONAL_APPROVAL_STATE))
        self.assertIsNone(activity._logged_tier("Approved 1", ADDITIONAL_HOLD_STATE))

    def test_logged_tier_escalation_credited_by_destination(self):
        """Escalations credit the tier by destination — including a tier resuming from review."""
        self.assertEqual(activity._logged_tier("Approved 1", "Approved 2"), 2)
        # tier 1 resuming after a review (from_state is the review state) still credits tier 1
        self.assertEqual(activity._logged_tier(ADDITIONAL_APPROVAL_STATE, "Approved 1"), 1)

    def test_logged_tier_hold_credited_by_destination(self):
        """A tier hold credits that tier."""
        self.assertEqual(activity._logged_tier("Approved 2", "On Hold by Approver 3"), 3)

    def test_logged_tier_finalize_and_reject_use_from_state(self):
        """Finalize/Reject name no tier in the destination, so the acting tier comes from
        the from-state."""
        self.assertEqual(activity._logged_tier("Approved 1", "Approved"), 2)
        self.assertEqual(activity._logged_tier("Pending", "Rejected"), 1)

    # ---------------- eligibility (mocked) ----------------

    def test_manager_role_is_eligible(self):
        """A manager role may inject a reviewer without being a configured approver."""
        with patch.object(frappe, "get_roles", return_value=["Approval Manager"]):
            self.assertTrue(U.is_eligible_approver("Purchase Order", "PO-1", "mgr@example.com"))

    def test_pool_member_is_eligible(self):
        """A configured approver of the document is eligible."""
        row = SimpleNamespace()
        with patch.object(frappe, "get_roles", return_value=["Employee"]), \
             patch.object(frappe, "get_doc", return_value=SimpleNamespace(
                 get=lambda f: "8848Digital" if f == "company" else "Purchase - 8")), \
             patch.object(U, "amount_field_for", return_value="grand_total"), \
             patch.object(U, "find_band_row", return_value=row), \
             patch.object(U, "configured_levels", return_value=[1, 2]), \
             patch.object(U, "pool", side_effect=lambda r, lvl: {1: ["a@x.com"], 2: ["b@x.com"]}[lvl]):
            self.assertTrue(U.is_eligible_approver("Purchase Order", "PO-1", "b@x.com"))
            self.assertFalse(U.is_eligible_approver("Purchase Order", "PO-1", "stranger@x.com"))
