# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Approver remarks attached to a workflow transition.

Frappe's `apply_workflow(doc, action)` has no slot for a note, so remarks travel
beside it: the caller stashes them in Redis first (keyed by user + document), and
`runtime._record_history` pops them while logging the transition. The same path is
used by the Desk dialog (`api/v1/workflow.stash_remarks`) and the email-link page
(`email_action/execute.py`), so the mandatory-reject-reason rule is enforced in one
place, whatever the channel.

Example:
    stash_remarks("Purchase Invoice", "PI-0001", "Reject", "Wrong GST rate")
    apply_workflow(doc, "Reject")   # -> Document Workflow Log.remarks = "Wrong GST rate"
"""

import frappe
from frappe import _
from frappe.utils import escape_html

REJECTED_STATE = "Rejected"

# Long enough for a slow dialog-to-apply round trip, short enough that a stale note
# can't attach itself to a later, unrelated action on the same document.
STASH_TTL_SECONDS = 5 * 60

MAX_REMARKS_LENGTH = 1000


def stash_remarks(doctype, name, action, remarks, via_email_link=False, user=None):
    """
    Hold the remarks for the next workflow action `user` takes on this document.

    Parameters:
        doctype (str, required): Target document's DocType.
        name (str, required): Target document's name.
        action (str, required): Workflow action the remarks belong to (Approve/Hold/Reject).
        remarks (str, required): Approver's note; may be empty for Approve/Hold.
        via_email_link (bool, optional): True when the action comes from the email page.
        user (str, optional): Acting user. Defaults to the session user.

    Returns:
        None
    """
    user = user or frappe.session.user
    # Also proves the document exists; a stash for a document the user can't see is refused.
    frappe.has_permission(doctype, "read", doc=name, user=user, throw=True)

    cleaned = clean_remarks(remarks)
    if action_needs_reason(action) and not cleaned:
        frappe.throw(_("Please provide a reason for rejecting this document."))

    frappe.cache.set_value(
        __stash_key(doctype, name, user),
        {"action": action, "remarks": cleaned, "via_email_link": bool(via_email_link)},
        expires_in_sec=STASH_TTL_SECONDS,
    )


def pop_transition_remarks(doc, new_state):
    """
    Take (and clear) the remarks stashed for the transition `doc` is making now.

    A stash made for a different action (e.g. a note typed for Hold, then Approve
    clicked instead) is discarded rather than attached to the wrong transition.

    Parameters:
        doc (Document, required): Target document being transitioned.
        new_state (str, required): The workflow state it is moving to.

    Returns:
        frappe._dict: `{"remarks": str, "via_email_link": bool}` (empty remarks when
        nothing matching was stashed).
    """
    key = __stash_key(doc.doctype, doc.name, frappe.session.user)
    stashed = frappe.cache.get_value(key) or {}
    frappe.cache.delete_value(key)

    if stashed.get("action") != action_for_state(new_state):
        return frappe._dict(remarks="", via_email_link=False)
    return frappe._dict(
        remarks=stashed.get("remarks") or "",
        via_email_link=bool(stashed.get("via_email_link")),
    )


def validate_reject_reason(new_state, remarks):
    """
    Refuse a move to Rejected that carries no reason.

    Parameters:
        new_state (str, required): The workflow state the document is moving to.
        remarks (str, required): Remarks attached to the transition (may be empty).

    Returns:
        None
    """
    if new_state == REJECTED_STATE and not remarks:
        frappe.throw(
            _("A reason is mandatory when rejecting. Use the Reject action again and enter one."),
            title=_("Reason Required"),
        )


def add_timeline_comment(doc, new_state, remarks):
    """
    Mirror the remarks onto the document's timeline, authored by the acting approver.

    Parameters:
        doc (Document, required): Target document being transitioned.
        new_state (str, required): The workflow state it moved to.
        remarks (str, required): The (already cleaned) remarks text.

    Returns:
        None
    """
    doc.add_comment("Comment", f"<b>{escape_html(_(new_state))}</b>: {escape_html(remarks)}")


def action_for_state(state):
    """
    Workflow action that leads into `state`, from the engine's fixed state names.

    Parameters:
        state (str, required): Target workflow state.

    Returns:
        str: "Reject", "Hold" or "Approve".
    """
    if state == REJECTED_STATE:
        return "Reject"
    if state and state.startswith("On Hold"):
        return "Hold"
    return "Approve"


def action_needs_reason(action):
    """
    Whether this workflow action must carry remarks.

    Parameters:
        action (str, required): Workflow action name.

    Returns:
        bool: True only for Reject.
    """
    return action == "Reject"


def clean_remarks(remarks):
    """
    Normalise user-entered remarks: trimmed, capped length, empty string if blank.

    Parameters:
        remarks (str, optional): Raw remarks text.

    Returns:
        str: Cleaned remarks.
    """
    return (remarks or "").strip()[:MAX_REMARKS_LENGTH]


def __stash_key(doctype, name, user):
    """
    Redis key holding one user's pending remarks for one document.

    Parameters:
        doctype (str, required): Target document's DocType.
        name (str, required): Target document's name.
        user (str, required): Acting user.

    Returns:
        str: Cache key.
    """
    return f"approval_engine:transition_remarks:{user}:{doctype}:{name}"
