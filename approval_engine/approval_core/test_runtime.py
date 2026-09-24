# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Pure-logic tests for the runtime workflow hooks.

Covers the reviewer re-notify-on-hold rule (`_renotify_held_reviewer`) without a
database, by mocking the reviewer lookup, the `action_via_email` read, and the
enqueue helper. The full multi-user runtime flow is exercised end-to-end separately.
"""

from types import SimpleNamespace
from unittest.mock import patch

from frappe.tests import UnitTestCase

from approval_engine.approval_core import runtime


class UnitTestRuntime(UnitTestCase):
    """No-database tests for the runtime hooks."""

    def _doc(self):
        """A minimal stand-in for a governed document in the additional-hold state."""
        return SimpleNamespace(doctype="Purchase Order", name="PUR-ORD-0001")

    def test_held_reviewer_reemailed_when_email_enabled(self):
        """A pending reviewer with action_via_email set is re-emailed on hold."""
        with patch.object(runtime, "pending_reviewer", return_value="AA-0001"), \
             patch.object(runtime.frappe.db, "get_value", return_value=1), \
             patch.object(runtime, "notify_reviewer") as notify:
            runtime._renotify_held_reviewer(self._doc())
        notify.assert_called_once_with("AA-0001")

    def test_held_reviewer_not_emailed_when_email_disabled(self):
        """A Desk-only reviewer (action_via_email unset) is never emailed on hold."""
        with patch.object(runtime, "pending_reviewer", return_value="AA-0001"), \
             patch.object(runtime.frappe.db, "get_value", return_value=0), \
             patch.object(runtime, "notify_reviewer") as notify:
            runtime._renotify_held_reviewer(self._doc())
        notify.assert_not_called()

    def test_no_reviewer_no_email(self):
        """With no pending reviewer, nothing is emailed (and the flag is never read)."""
        with patch.object(runtime, "pending_reviewer", return_value=None), \
             patch.object(runtime.frappe.db, "get_value") as get_value, \
             patch.object(runtime, "notify_reviewer") as notify:
            runtime._renotify_held_reviewer(self._doc())
        notify.assert_not_called()
        get_value.assert_not_called()

    def test_additional_hold_not_in_no_email_states(self):
        """The reviewer hold state is no longer a blanket no-email state."""
        self.assertNotIn(runtime.ADDITIONAL_HOLD_STATE, runtime.NO_EMAIL_STATES)
