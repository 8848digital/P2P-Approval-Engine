# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Guest endpoints behind the emailed approval page (`/approval_action`).

Thin wrappers over ``approval_core.email_action.link_actions``. The link token is
the only credential a visitor has, so both endpoints are POST-only (email scanners
pre-fetch GET links), rate-limited per link + IP, and every action additionally
needs the one-time code emailed to the approver.
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from approval_engine.approval_core.email_action import link_actions
from approval_engine.approval_core.email_action.errors import ApprovalLinkError
from approval_engine.utils.api_handlers.response_formatter import api_response

ONE_HOUR = 60 * 60


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(key="token", limit=10, seconds=ONE_HOUR)
def request_otp(token: str, action: str):
	"""
	    Email the approver a 6-digit verification code for the chosen action.

	    A new request replaces any previous code; requests within 60 seconds of the
	    last one are refused.

	    **Endpoint:** `/api/method/approval_engine.approval_core.api.v1.email_action.request_otp`
	    **HTTP Method:** POST
	    **Parameters:**
	        - token (str, required): Token from the emailed approval link
	        - action (str, required): Workflow action to authorise (Approve / Hold / Reject)
	    **Response:**
	```json
	        {
	            "status": true,
	            "status_code": 200,
	            "message": "Verification code sent",
	            "data": { "sent_to": "d****l@8848digital.com", "validity_minutes": 10 },
	            "errors": null
	        }
	```
	"""
	try:
		data = link_actions.request_otp(token, action)
	except ApprovalLinkError as error:
		return api_response(status=False, code=400, message=str(error))
	return api_response(message=_("Verification code sent"), data=data)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(key="token", limit=20, seconds=ONE_HOUR)
def submit_action(token: str, action: str, otp: str, remarks: str | None = None):
	"""
	    Apply the chosen workflow action as the link's approver, after checking the code.

	    A wrong code answers 401 with the attempts left; after 5 wrong tries the code is
	    burned and a new one must be requested.

	    **Endpoint:** `/api/method/approval_engine.approval_core.api.v1.email_action.submit_action`
	    **HTTP Method:** POST
	    **Parameters:**
	        - token (str, required): Token from the emailed approval link
	        - action (str, required): Workflow action to apply (Approve / Hold / Reject)
	        - otp (str, required): 6-digit code from the verification email
	        - remarks (str, optional): Approver's remarks; mandatory for Reject
	    **Response:**
	```json
	        {
	            "status": true,
	            "status_code": 200,
	            "message": "Action applied",
	            "data": { "applied": true, "workflow_state": "Approved 1" },
	            "errors": null
	        }
	```
	"""
	try:
		result = link_actions.perform_action(token, action, otp, remarks)
	except ApprovalLinkError as error:
		return api_response(status=False, code=400, message=str(error))

	if result["applied"]:
		return api_response(message=_("Action applied"), data=result)

	attempts_left = result["attempts_left"]
	message = (
		_("Incorrect verification code. {0} attempt(s) left.").format(attempts_left)
		if attempts_left
		else _("Too many incorrect attempts. Please request a new verification code.")
	)
	return api_response(
		status=False, code=401, message=message, errors={"attempts_left": attempts_left}
	)
