# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Shared Procure-to-Pay / Payments Compliance dashboard data layer.

Used by TWO pages that render the identical dashboard but differ only in who
may access it and what extra actions they see:

  - page/procure_to_pay: open dashboard, no Payments Compliance Settings
    allowed_roles gate -- any user who can reach the page can view it.
  - page/procure_to_pay_management: the same dashboard, gated by Payments
    Compliance Settings' allowed_roles (see _check_permission), plus an
    "Update Account Closing" action gated by its own separate role list
    (see payments_compliance_period_closing_role.py / can_view_period_closing
    in that page's controller).

Everything in this module is access-control-agnostic on purpose -- each
page's own whitelisted controller decides whether to call _check_permission()
before calling into here. Do not add a permission check inside this module;
that decision belongs to the caller.

Personal by default, but not always: build_dashboard_payload's `scope_user`
picks between a personal view (documents a user created, UNIONed with
documents currently pending on them as an approval-workflow approver,
UNIONed with documents they already approved or rejected at their own
step -- see _my_scope_context) and a company-wide aggregate view with no
personal filtering at all (`scope_user=None`). The open dashboard only ever uses
the personal view, forced to frappe.session.user; the management dashboard
defaults to aggregate and can drill into any specific user's personal view
via its own "User" filter.

Bucketing rule (BRN / Payment Order / Purchase Order / Purchase Invoice all
land in one of [Approved/Processed, Rejected/Failed, Pending]), in priority
order -- see _resolve_bucket for the implementation:

  1. Workflow State Mapping wins, if configured. This site runs TWO
     different workflow engines depending on the doctype -- the custom
     user_based_workflow app's "Approval Workflow", or a standard Frappe
     "Workflow" -- both just write to the doctype's `workflow_state` field,
     so _is_workflow_active() checks for either one being active.
  2. Payment Order is the one exception that does NOT fall back to plain
     docstatus: it has its own real `status` field (Pending / Initiated /
     Failed / ...), which is the actual signal for whether a payment was
     processed -- docstatus=1 only means the record was submitted, not that
     a bank acted on it. See PAYMENT_ORDER_STATUS_BUCKET.
  3. Everything else falls back to plain docstatus: Draft=Pending,
     Submitted=Approved/Processed, Cancelled=Rejected/Failed.

Every bucket also carries an exact "which documents are in it" filter
(by document name, not an approximate docstatus/state filter) so a click
on a chart bucket always opens a list that matches the chart exactly --
see _status_counts.
"""

# Re-exported so existing imports of dashboard_data keep working after the
# split into dashboard_*.py modules.
from approval_engine.approval_settlement.customization.procure_to_pay.dashboard_buckets import (  # noqa: F401
	_docstatus_bucket,
	_get_state_mapping,
	_payment_order_bucket,
	_resolve_bucket,
)
from approval_engine.approval_settlement.customization.procure_to_pay.dashboard_config import (  # noqa: F401
	APPROVAL_TARGET_KEYS,
	PAYMENT_TARGET_KEYS,
)
from approval_engine.approval_settlement.customization.procure_to_pay.dashboard_debug import (  # noqa: F401
	build_debug_line_items,
	build_debug_raw_counts,
)
from approval_engine.approval_settlement.customization.procure_to_pay.dashboard_error_logs import (  # noqa: F401
	build_error_logs,
)
from approval_engine.approval_settlement.customization.procure_to_pay.dashboard_filters import (  # noqa: F401
	_check_permission,
	_get_settings,
)
from approval_engine.approval_settlement.customization.procure_to_pay.dashboard_payload import (  # noqa: F401
	build_dashboard_payload,
)
