# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Whitelisted endpoints for the ad-hoc `Additional Approver` feature.

Thin wrappers over ``additional_approver_utils``; the authorisation, validation and
insertion logic lives there, these only expose it and shape the response envelope.
"""

import frappe

from approval_engine.approval_core.doctype.additional_approver import (
    additional_approver_utils as utils,
)
from approval_engine.utils.api_handlers.response_formatter import api_response


@frappe.whitelist(methods=["GET", "POST"])
def can_add(doctype: str, name: str):
    """Whether the current user may inject an additional approver into a document right now.

    Drives the "Add Additional Approver" button: the button shows only when the user is an
    approver of the document, the document sits in an insertable state, and no reviewer is
    already pending. Read-only; accepts POST because the desk client's `frappe.call` posts
    by default.

    **Endpoint:** `/api/method/approval_engine.approval_core.api.v1.additional_approver.can_add`
    **HTTP Method:** GET or POST
    **Parameters:**
        - doctype (str, required): Target document's DocType
        - name (str, required): Target document's name
    **Response:**
```json
        {
            "status": true,
            "status_code": 200,
            "message": "Eligibility resolved",
            "data": { "can_add": true, "insert_state": "Approved 2" },
            "errors": null
        }
```
    """
    state = frappe.db.get_value(doctype, name, "workflow_state")
    eligible = (
        state in utils.INSERTABLE_STATES
        and not utils.pending_reviewer(doctype, name)
        and utils.is_eligible_approver(doctype, name, frappe.session.user)
    )
    return api_response(
        data={"can_add": bool(eligible), "insert_state": state},
        message="Eligibility resolved",
    )


@frappe.whitelist(methods=["POST"])
def add(doctype: str, name: str, approver: str,
        can_hold: int = 0, can_reject: int = 0, action_via_email: int = 0):
    """Insert one ad-hoc additional approver into a single document's live approval chain.

    The reviewer acts before the next configured tier, then the normal chain resumes; the
    shared Approval Matrix and every other document are untouched.

    **Endpoint:** `/api/method/approval_engine.approval_core.api.v1.additional_approver.add`
    **HTTP Method:** POST
    **Parameters:**
        - doctype (str, required): Target document's DocType
        - name (str, required): Target document's name
        - approver (str, required): User to insert as the additional approver
        - can_hold (int, optional): Whether the reviewer may hold the document (default 0)
        - can_reject (int, optional): Whether the reviewer may reject the document (default 0)
        - action_via_email (int, optional): Whether to email the reviewer an action link (default 0)
    **Response:**
```json
        {
            "status": true,
            "status_code": 200,
            "message": "Additional approver added",
            "data": { "name": "a1b2c3d4e5" },
            "errors": null
        }
```
    """
    record = utils.add_additional_approver(
        doctype, name, approver,
        can_hold=can_hold, can_reject=can_reject, action_via_email=action_via_email,
    )
    # 200 (not 201): the desk client (frappe.request) only invokes success callbacks for
    # status codes it has an explicit handler for (200), so a 201 would leave the caller's
    # callback — e.g. the dialog's hide/reload — never firing.
    return api_response(message="Additional approver added", data={"name": record})
