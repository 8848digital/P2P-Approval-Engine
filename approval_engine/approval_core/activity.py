# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Workflow Activity for documents governed by an approval workflow.

Reconstructs the ordered approver chain for a single target document by overlaying
the actual transition history (`Document Workflow Log`) on top of the matched
Approval Matrix band's configured tiers. This is what powers the "Workflow Activity"
section in the target document's form sidebar.

Each step is one configured approver tier:
- acted tiers        -> the real approver + status (approved / on_hold / rejected) + timestamp
- the current tier   -> "pending", owner = the eligible approver pool
- upcoming tiers      -> blank status, owner = the eligible approver pool
"""

import frappe
from frappe.utils import flt, get_fullname

from approval_engine.approval_core.generator import (
    MAX_LEVELS,
    STATE_FOR_TIER,
    acting_tier,
    amount_field_for,
    configured_levels,
    find_band_row,
    pool,
    workflow_name,
)

# from_state -> the tier that acts FROM it (inverse of STATE_FOR_TIER)
_TIER_FROM_STATE = {state: tier for tier, state in STATE_FOR_TIER.items()}


def _managed(doctype):
    """
    Whether `doctype` currently runs on an active engine-generated workflow.

    Parameters:
        doctype (str, required): DocType to check.

    Returns:
        bool: True when its `<DocType> Approval` workflow exists and is active.
    """
    return bool(frappe.db.get_value(
        "Workflow",
        {"document_type": doctype, "is_active": 1, "name": workflow_name(doctype)},
        "name",
    ))


def _status_of(to_state):
    """
    Sidebar status for a tier, from the state its action moved the document to.

    Parameters:
        to_state (str, required): State the document moved to.

    Returns:
        str: "rejected", "on_hold" or "approved".
    """
    if to_state == "Rejected":
        return "rejected"
    if to_state and to_state.startswith("On Hold"):
        return "on_hold"
    return "approved"  # "Approved N" or "Approved"


def _owner(user):
    """
    Render one approver for the sidebar.

    Parameters:
        user (str, optional): User ID.

    Returns:
        dict | None: `{"user", "full_name"}`, or None when no user.
    """
    return {"user": user, "full_name": get_fullname(user)} if user else None


def managed_doctypes():
    """Target DocTypes that currently have an active engine-generated workflow.
    Used by the client to register the sidebar renderer only where relevant."""
    from approval_engine.approval_core.dashboard.finance_dashboard import target_doctypes
    return [dt for dt in target_doctypes() if _managed(dt)]


def workflow_activity(doctype, name):
    """Reconstruct the ordered approver chain for one target document.

    Overlays the document's transition history (`Document Workflow Log`) on the
    matched Approval Matrix band's configured tiers to produce the per-tier
    steps rendered in the form sidebar.

    Parameters:
        doctype (str, required): Target document's DocType.
        name (str, required): Target document's name.

    Returns:
        dict: {"managed": bool, "current_state": str, "steps": list}.
    """
    if not _managed(doctype):
        return {"managed": False, "steps": []}

    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")

    current = doc.get("workflow_state")
    amount = flt(doc.get(amount_field_for(doctype)))
    row = find_band_row(doctype, doc.get("company"), doc.get("department"), amount)
    if not row:
        return {"managed": True, "current_state": current, "steps": []}

    levels = configured_levels(row)

    logs = frappe.get_all(
        "Document Workflow Log",
        filters={"reference_doctype": doctype, "reference_name": name},
        fields=["from_state", "workflow_state", "user", "creation", "remarks", "via_email_link"],
        order_by="creation asc",
    )

    # Final action per tier from the log (later entries win, so a hold that was
    # later approved correctly ends up "approved"; an unresolved hold stays "on_hold").
    tier_action = {}
    for log in logs:
        tier = acting_tier(log.from_state)
        if not tier:
            continue
        tier_action[tier] = {
            "status": _status_of(log.workflow_state),
            "user": log.user,
            "time": str(log.creation),
            "remarks": log.remarks,
            "via_email_link": bool(log.via_email_link),
        }

    # The single tier currently awaiting action (only set in an approve-chain state;
    # None when Approved/Rejected, and None when On Hold since that tier is already
    # captured in tier_action).
    current_tier = _TIER_FROM_STATE.get(current)

    steps = []
    for level in levels:
        act = tier_action.get(level)
        # Owner is ALWAYS the full tier pool -- every configured approver co-owns the
        # step (any of them can Approve/Hold/Reject). Who actually performed the
        # transition is surfaced separately via `acted_by`, so the owner list stays
        # stable regardless of who acted.
        step = {
            "level": level,
            "owner": [_owner(u) for u in pool(row, level)],
            "acted_by": None,
            "time": None,
            "remarks": None,
            "via_email_link": False,
        }
        if act:
            # approved / on_hold / rejected, attributed to the approver who acted
            step["status"] = act["status"]
            step["acted_by"] = _owner(act["user"])
            step["time"] = act["time"]
            step["remarks"] = act["remarks"]
            step["via_email_link"] = act["via_email_link"]
        else:
            step["status"] = "pending" if level == current_tier else "upcoming"
        steps.append(step)

    return {"managed": True, "current_state": current, "steps": steps}
