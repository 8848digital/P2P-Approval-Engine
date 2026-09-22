# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Whitelisted endpoints for the vendor-portal login/logout/password/upload flow.

Thin wrappers only -- the actual auth/session logic lives in
settlement/vendor_portal_auth.py (moved out of settlement/api.py, which held
these functions inline before this endpoint consolidation).
"""

import frappe

from approval_engine.settlement.vendor_portal_auth import (
	attach_vendor_invoice_copy,
	change_vendor_password,
	logout_vendor_user,
)
from approval_engine.settlement.vendor_portal_auth import authenticate_vendor_login as _authenticate


# This IS the login endpoint -- no session exists yet, so it must allow Guest.
@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
def vendor_login(usr: str, pwd: str):
	"""
		Custom login endpoint for the vendor portal.

		Authenticates the given credentials, then additionally checks that the
		account is actually a vendor before establishing the session. This keeps
		the vendor portal separate from the standard Frappe /login flow, so an
		arbitrary system user (or a vendor trying to use the wrong door) can't
		just log in here.

		**Endpoint:** `/api/method/approval_engine.settlement.api.v1.vendor_portal.vendor_login`
		**HTTP Method:** POST
		**Parameters:**
			- usr (str, required): The login email/username
			- pwd (str, required): The login password
		**Response:**
	```json
			{
				"success": true,
				"redirect_to": "/portal"
			}
	```
	"""
	return _authenticate(usr, pwd)


@frappe.whitelist(methods=["GET", "POST"])
def vendor_web_logout():
	"""
	Custom logout for portal users.

	Redirects to /vendor-login if the logged-out user had vendor access,
	otherwise falls back to the standard /login page. Declared GET (in
	addition to POST) because it's reached via a plain `<a href>` navigation
	link in the portal nav, not a `frappe.call`.

	**Endpoint:** `/api/method/approval_engine.settlement.api.v1.vendor_portal.vendor_web_logout`
	**HTTP Method:** GET, POST
	**Parameters:** None
	**Response:** HTTP redirect to /vendor-login or /login (no JSON body)
	"""
	logout_vendor_user()


@frappe.whitelist(methods=["POST"])
def vendor_update_password(old_password: str, new_password: str):
	"""
	Change the current vendor-portal user's password.

	**Endpoint:** `/api/method/approval_engine.settlement.api.v1.vendor_portal.vendor_update_password`
	**HTTP Method:** POST
	**Parameters:**
		- old_password (str, required): The user's current password
		- new_password (str, required): The new password to set
	**Response:** `null` message body on success (raises on failure)
	"""
	change_vendor_password(old_password, new_password)


@frappe.whitelist(methods=["POST"])
def vendor_attach_invoice_copy(route: str, docname: str):
	"""
		Attach an uploaded invoice-copy file to a vendor-visible document.

		Lets a vendor upload their invoice copy straight from a record's own
		detail page in the portal, for Portal Section Config rows with Allow
		Attaching Invoice Copy enabled, while the record isn't fully billed yet.

		**Endpoint:** `/api/method/approval_engine.settlement.api.v1.vendor_portal.vendor_attach_invoice_copy`
		**HTTP Method:** POST
		**Parameters:**
			- route (str, required): The portal route identifying the section config row
			- docname (str, required): The name of the document to attach the file to
		**Response:**
	```json
			{
				"file_name": "invoice.pdf",
				"file_url": "/files/invoice.pdf"
			}
	```
	"""
	return attach_vendor_invoice_copy(route, docname)
