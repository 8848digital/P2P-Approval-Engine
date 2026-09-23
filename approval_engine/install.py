# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Install hooks.

Seed the master data the generated Workflows depend on, so a freshly installed
site is ready *before* the first Approval Matrix is submitted. Everything here is
idempotent — the generator also ensures these on every matrix submit, so running
this again (e.g. on reinstall) is safe.
"""

import frappe

from approval_engine.approval_core import generator
from approval_engine.approval_core.email_action.action_link import DEFAULT_VALIDITY_HOURS


def after_install():
    """
    Seed workflow masters and the default Approval Settings values on a new site.

    Returns:
        None
    """
    generator.ensure_workflow_states()
    generator.ensure_actions()
    frappe.db.set_single_value(
        "Approval Settings", "email_link_validity_hours", DEFAULT_VALIDITY_HOURS)
    frappe.db.commit()
