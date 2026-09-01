"""Install hooks.

Seed the master data the generated Workflows depend on, so a freshly installed
site is ready *before* the first Approval Matrix is submitted. Everything here is
idempotent — the generator also ensures these on every matrix submit, so running
this again (e.g. on reinstall) is safe.
"""

import frappe

from approval_engine import generator


def after_install():
    generator.ensure_workflow_states()
    generator.ensure_actions()
    frappe.db.commit()
