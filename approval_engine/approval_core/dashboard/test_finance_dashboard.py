# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Pure-logic tests for the Finance Overview dashboard's ad-hoc reviewer attribution.

An Additional Approver's actions land in their own states (`Additionally Approved`,
`On Hold by Additional Approver`), not the tier states — these tests pin that the
dashboard counts them. The SQL is captured via a mocked `frappe.db.sql`.
"""

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from approval_engine.approval_core.dashboard import finance_dashboard as fd
from approval_engine.approval_core.generator import (
    ADDITIONAL_APPROVAL_STATE,
    ADDITIONAL_HOLD_STATE,
)


class UnitTestFinanceDashboard(UnitTestCase):
    """No-database tests for the dashboard's state attribution."""

    def test_reviewer_approve_counts_as_approved(self):
        """A reviewer's Approve (-> Additionally Approved) is an approval by that user."""
        self.assertIn(ADDITIONAL_APPROVAL_STATE, fd.APPROVED_STATES)

    def test_on_hold_includes_reviewer_hold(self):
        """The on-hold query matches the reviewer's hold state, not only tier holds."""
        query, params = self._capture_sql(lambda: fd.on_hold_for_doctype("BRN", "C", "u"))
        self.assertIn("%(reviewer_hold)s", query)
        self.assertEqual(params["reviewer_hold"], ADDITIONAL_HOLD_STATE)

    def test_held_reviewer_doc_is_not_pending(self):
        """A doc the reviewer has held counts under on-hold, not pending."""
        query, _params = self._capture_sql(
            lambda: fd._pending_reviewer_rows("BRN", "total_amount", {})
        )
        self.assertIn(f"!= {frappe.db.escape(ADDITIONAL_HOLD_STATE)}", query)

    def _capture_sql(self, call):
        """
        Run `call` with the amount-field lookup and `frappe.db.sql` mocked out.

        Parameters:
            call (callable, required): Zero-arg function issuing one dashboard query.

        Returns:
            tuple: (query string, bind params) passed to `frappe.db.sql`.
        """
        with patch.object(fd, "amount_field_for", return_value="total_amount"), \
             patch.object(frappe.db, "sql", return_value=[]) as sql:
            call()
        return sql.call_args.args[0], sql.call_args.args[1]
