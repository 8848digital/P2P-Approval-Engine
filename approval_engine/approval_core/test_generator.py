# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Pure-logic tests for how the generator finds the workflow it owns.

The engine must only ever create, rewrite or deactivate its own `<DocType> Approval`
workflow — never another workflow on the same DocType (e.g. a customer's "Test YEXP").
Database calls are mocked, so no workflow is actually saved.
"""

from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from approval_engine.approval_core import generator

OWN_WORKFLOW = "Purchase Order Approval"


class UnitTestGenerator(UnitTestCase):
    """No-database tests for the engine's workflow lookup."""

    def _build(self, existing):
        """
        Run `build_workflow` for Purchase Order with the DB lookup and doc loaders mocked.

        Parameters:
            existing (str | None, required): What the by-name lookup of our workflow returns.

        Returns:
            tuple: (exists mock, get_doc mock, new_doc mock, workflow doc mock).
        """
        wf = MagicMock()
        with patch.object(generator.frappe.db, "exists", return_value=existing) as exists, \
             patch.object(generator.frappe, "get_doc", return_value=wf) as get_doc, \
             patch.object(generator.frappe, "new_doc", return_value=wf) as new_doc, \
             patch.object(generator, "build_transitions", return_value=[]), \
             patch.object(generator, "_allow_edit", return_value=0):
            generator.build_workflow("Purchase Order")
        return exists, get_doc, new_doc, wf

    def test_foreign_active_workflow_excludes_own(self):
        """The foreign-workflow check skips the engine's own workflow by name."""
        with patch.object(generator.frappe.db, "get_value", return_value="Test YEXP") as get_value:
            self.assertEqual(generator.foreign_active_workflow("Purchase Order"), "Test YEXP")
        filters = get_value.call_args.args[1]
        self.assertEqual(filters["name"], ("!=", OWN_WORKFLOW))
        self.assertEqual(filters["is_active"], 1)

    def test_build_creates_own_workflow_beside_foreign_one(self):
        """With only a foreign workflow on the DocType, a new named workflow is created."""
        exists, get_doc, new_doc, wf = self._build(existing=None)
        exists.assert_called_once_with("Workflow", OWN_WORKFLOW)
        get_doc.assert_not_called()
        new_doc.assert_called_once_with("Workflow")
        self.assertEqual(wf.workflow_name, OWN_WORKFLOW)

    def test_build_rewrites_own_workflow(self):
        """An existing engine workflow is loaded by name and rewritten in place."""
        exists, get_doc, new_doc, wf = self._build(existing=OWN_WORKFLOW)
        get_doc.assert_called_once_with("Workflow", OWN_WORKFLOW)
        new_doc.assert_not_called()
        wf.save.assert_called_once()

    def test_cancel_deactivates_only_own_workflow(self):
        """Cancelling the last matrix deactivates the engine workflow, found by name."""
        with patch.object(generator, "reconcile_roles"), \
             patch.object(generator.frappe.db, "count", return_value=0), \
             patch.object(generator.frappe.db, "exists", return_value=OWN_WORKFLOW) as exists, \
             patch.object(generator.frappe.db, "set_value") as set_value, \
             patch.object(generator.frappe, "clear_cache"):
            generator.on_matrix_cancel("Purchase Order")
        exists.assert_called_once_with("Workflow", OWN_WORKFLOW)
        set_value.assert_called_once_with("Workflow", OWN_WORKFLOW, "is_active", 0)

    def test_cancel_leaves_foreign_workflow_alone(self):
        """With no engine workflow present, cancel deactivates nothing."""
        with patch.object(generator, "reconcile_roles"), \
             patch.object(generator.frappe.db, "count", return_value=0), \
             patch.object(generator.frappe.db, "exists", return_value=None), \
             patch.object(generator.frappe.db, "set_value") as set_value, \
             patch.object(generator.frappe, "clear_cache"):
            generator.on_matrix_cancel("Purchase Order")
        set_value.assert_not_called()
