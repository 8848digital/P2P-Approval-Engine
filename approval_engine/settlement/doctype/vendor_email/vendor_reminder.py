# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Scheduled reminder emails for not-yet-onboarded vendors. Split out of
utils.py to keep that file under the line-count cap - hooks.py's
scheduler_events still targets utils.send_reminder_for_non_registered_vendors
(re-exported there, see that file), so this dotted path stays out of it.
"""

import urllib.parse

import frappe

from approval_engine.settlement.doctype.vendor_email.vendor_email_encoding import (
	encode_email,
)


def send_reminder_for_non_registered_vendors() -> None:
	"""
	Send a reminder email to every vendor whose onboarding hasn't yet
	resulted in a Supplier being created (`supplier_created` = 0).
	Intended to run as a scheduled task.

	Parameters:
	        None

	Returns:
	        None
	"""
	# Get vendors that are new vendors
	vendors = frappe.get_all(
		"Vendor Email",
		filters={
			"supplier_created": 0,
		},
		fields=["name", "email_2", "company"],
	)
	if vendors:
		for vendor in vendors:
			try:
				redirect_url = f"/vendor-onboarding-form/new?email_id={encode_email(vendor.name)}"
				# custom_company is picked up the same way email_id is --
				# see the comment in build_vendor_webform_link().
				if vendor.company:
					redirect_url += f"&custom_company={urllib.parse.quote(vendor.company)}"
				encoded_redirect = urllib.parse.quote(redirect_url)

				webform_link = f"{frappe.utils.get_url()}/vendor-login?redirect-to={encoded_redirect}"

				subject = "Reminder: Complete Your Vendor Registration"
				message = f"""
				Hello,

				This is a reminder to complete your vendor registration.

				Login: {vendor.name} <br>
				<a href="{webform_link}">Fill Vendor Details</a>
				"""

				# Same link, same login (vendor.name / email) for both --
				# there's still only ever one account, against the primary
				# email, not email_2. Login line above is spelled out
				# explicitly since this same message also goes to email_2,
				# which has no account of its own to sign in with.
				recipients = [vendor.name] + ([vendor.email_2] if vendor.email_2 else [])

				frappe.sendmail(recipients=recipients, subject=subject, message=message, delayed=False)

			except Exception as e:
				frappe.log_error(str(e), "Vendor Reminder Error")
