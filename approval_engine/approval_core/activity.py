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
    ADDITIONAL_APPROVAL_STATE,
    ADDITIONAL_HOLD_STATE,
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

# to_state -> the tier whose approval lands there (an escalation credits that tier)
_APPROVED_STATE_TIER = {"Approved 1": 1, "Approved 2": 2, "Approved 3": 3}
_HOLD_PREFIX = "On Hold by Approver "

# reviewer sidebar status -> the state their own action moved the document to
_REVIEWER_OUTCOME_STATE = {
    "approved": ADDITIONAL_APPROVAL_STATE,
    "on_hold": ADDITIONAL_HOLD_STATE,
    "rejected": "Rejected",
}


def _logged_tier(from_state, to_state):
    """
    The configured approver tier a logged transition belongs to, or None.

    Attributes by DESTINATION where it is unambiguous — an escalation into `Approved N`
    or a tier hold `On Hold by Approver N` credits tier N, which also correctly credits a
    tier that resumed after an ad-hoc review (its `from_state` is `Additionally Approved`).
    A move INTO an additional-approver state is the reviewer's own action, not a tier's.
    Finalize (`Approved`) and `Rejected` name no tier in the destination, so the acting
    tier is read from `from_state`.

    Parameters:
        from_state (str, optional): State the transition acted from.
        to_state (str, optional): State the transition moved to.

    Returns:
        int | None: The configured tier, or None when the move is not a tier action.
    """
    if to_state in (ADDITIONAL_APPROVAL_STATE, ADDITIONAL_HOLD_STATE):
        return None
    if to_state in _APPROVED_STATE_TIER:
        return _APPROVED_STATE_TIER[to_state]
    if to_state and to_state.startswith(_HOLD_PREFIX):
        suffix = to_state[len(_HOLD_PREFIX):]
        return int(suffix) if suffix.isdigit() else None
    return acting_tier(from_state)


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


def _active_reviewer(doctype, name):
    """
    The document's live ad-hoc reviewer record (pending or just-completed), if any.

    Parameters:
        doctype (str, required): Target document's DocType.
        name (str, required): Target document's name.

    Returns:
        dict | None: {approver, insert_state, completed, acted_on}, or None.
    """
    return frappe.db.get_value(
        "Additional Approver",
        {"reference_doctype": doctype, "reference_name": name, "active": 1},
        ["approver", "insert_state", "completed", "acted_on"],
        as_dict=True,
    )


def _all_reviewers(doctype, name):
    """
    Every ad-hoc reviewer ever added to a document, oldest first, for the sidebar.

    Parameters:
        doctype (str, required): Target document's DocType.
        name (str, required): Target document's name.

    Returns:
        list[dict]: Reviewer records with
            {approver, insert_state, completed, active, acted_on, creation}.
    """
    return frappe.get_all(
        "Additional Approver",
        filters={"reference_doctype": doctype, "reference_name": name},
        fields=["approver", "insert_state", "completed", "active", "acted_on", "creation"],
        order_by="creation asc",
    )


def _reviewer_status(reviewer, current):
    """
    Sidebar status for one ad-hoc reviewer.

    Approved once they have approved (`completed`); on_hold while the document sits in
    the reviewer's hold state; pending while it is still their turn (`active`, not
    completed); rejected once retired without completing.

    Parameters:
        reviewer (dict, required): An `Additional Approver` record's fields.
        current (str, required): The document's current workflow state.

    Returns:
        str: "approved", "on_hold", "pending" or "rejected".
    """
    if reviewer.completed:
        return "approved"
    if reviewer.active and current == ADDITIONAL_HOLD_STATE:
        return "on_hold"
    if reviewer.active:
        return "pending"
    return "rejected"


def _reviewer_log(reviewer, status, logs):
    """
    The `Document Workflow Log` row recording this reviewer's action, if any.

    The record itself carries no remarks, and `acted_on` is stamped only on approve, so
    actor/time/remarks for every acted status come from the log. A hold can repeat
    (hold -> resume -> hold), so the latest one is live; approve/reject happen once, so
    the first after the reviewer was added is theirs (a later reviewer has its own).

    Parameters:
        reviewer (dict, required): An `Additional Approver` record's fields.
        status (str, required): The reviewer's sidebar status (see `_reviewer_status`).
        logs (list[dict], required): The document's log rows, oldest first.

    Returns:
        dict | None: The matching log row, or None when not acted / not logged.
    """
    target = _REVIEWER_OUTCOME_STATE.get(status)
    if not target:
        return None

    matches = [
        log for log in logs
        if log.workflow_state == target and log.creation >= reviewer.creation
    ]
    if not matches:
        return None
    return matches[-1] if status == "on_hold" else matches[0]


def _reviewer_step(reviewer, status, action_log=None):
    """
    Render one ad-hoc reviewer as a sidebar step, mirroring a tier step's shape.

    Actor/time/remarks come from the reviewer's own log row (`action_log`), so an ad-hoc
    approve/hold/reject renders exactly like a tier's. Without a log row (history that
    predates logging) an approved/rejected reviewer falls back to the record itself.

    Parameters:
        reviewer (dict, required): An `Additional Approver` record's fields.
        status (str, required): The reviewer's sidebar status (see `_reviewer_status`).
        action_log (dict, optional): The log row for the reviewer's action
            (see `_reviewer_log`).

    Returns:
        dict: A step dict flagged `additional` for the sidebar renderer.
    """
    if action_log:
        acted_by, time, remarks, via_email = (
            _owner(action_log.user or reviewer.approver), str(action_log.creation),
            action_log.remarks, bool(action_log.via_email_link),
        )
    elif status in ("approved", "rejected"):
        acted_by, time, remarks, via_email = (
            _owner(reviewer.approver),
            str(reviewer.acted_on) if reviewer.acted_on else None, None, False,
        )
    else:
        acted_by, time, remarks, via_email = None, None, None, False

    return {
        "level": None,
        "additional": True,
        "owner": [_owner(reviewer.approver)],
        "acted_by": acted_by,
        "status": status,
        "time": time,
        "remarks": remarks,
        "via_email_link": via_email,
    }


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

    # Final action per tier from the log (later entries win, so a hold that was later
    # approved correctly ends up "approved"; an unresolved hold stays "on_hold"). Tier is
    # read from the DESTINATION where unambiguous, so an ad-hoc reviewer's move into the
    # review state is never miscredited to the tier it precedes, and a tier that resumes
    # after a review (acting from Additionally Approved) is still credited correctly.
    tier_action = {}
    for log in logs:
        tier = _logged_tier(log.from_state, log.workflow_state)
        if not tier:
            continue
        # Finalize/Reject name no tier in the destination, so a reviewer acting from a
        # tier state could masquerade as that tier — keep only its real pool members.
        if log.workflow_state in ("Approved", "Rejected") and log.user not in pool(row, tier):
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

    # An ad-hoc reviewer shifts "who acts now": while they are pending the tier they
    # precede is blocked, and while the document sits in Additionally Approved that tier
    # is the one now resuming.
    active_reviewer = _active_reviewer(doctype, name)
    if active_reviewer:
        tier_before = acting_tier(active_reviewer.insert_state)
        if current == ADDITIONAL_APPROVAL_STATE:
            current_tier = tier_before
        elif not active_reviewer.completed and current == active_reviewer.insert_state:
            current_tier = None

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

    # Every reviewer (past and present) shows as a step just before the tier it precedes,
    # in the order they were added, so an approved reviewer stays visible after the chain
    # resumes past them.
    for reviewer in _all_reviewers(doctype, name):
        status = _reviewer_status(reviewer, current)
        action_log = _reviewer_log(reviewer, status, logs)
        tier_before = acting_tier(reviewer.insert_state)
        insert_at = next((i for i, s in enumerate(steps) if s["level"] == tier_before), len(steps))
        steps.insert(insert_at, _reviewer_step(reviewer, status, action_log))

    return {"managed": True, "current_state": current, "steps": steps}
