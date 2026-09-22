# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Whitelisted endpoint for vendor onboarding invite emails.

Thin wrapper only -- the actual logic lives in
settlement/doctype/vendor_email/utils.py.
"""

import frappe

from approval_engine.settlement.doctype.vendor_email.utils import create_vendor


@frappe.whitelist(methods=["POST"])
def send_vendor_mail(
	mail: str,
	reference_doctype: str,
	reference_docname: str | None = None,
	name: str | None = None,
	email_2: str | None = None,
	company: str | None = None,
):
	"""
		Create a Vendor Email record and send the vendor onboarding invite email.

		**Endpoint:** `/api/method/approval_engine.settlement.api.v1.vendor_email.send_vendor_mail`
		**HTTP Method:** POST
		**Parameters:**
			- mail (str, required): The vendor's email address
			- reference_doctype (str, required): The doctype that triggered onboarding (e.g. Supplier)
			- reference_docname (str, optional): The referencing document's name
			- name (str, optional): The vendor's display name
			- email_2 (str, optional): A second recipient for the same invite
			- company (str, optional): The company context for the onboarding link
		**Response:**
	```json
			{"status": "success", "message": "Email sent to vendor@example.com"}
	```
	"""
	return create_vendor(mail, reference_doctype, reference_docname, name, email_2=email_2, company=company)
