# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import frappe
from frappe import _
from frappe.utils import today

from approval_engine.settlement.doctype.vendor_email.vendor_email_encoding import (
	encode_email,
	encode_string_part,
)
from approval_engine.settlement.doctype.vendor_email.vendor_mail import (
	build_vendor_webform_link,
	create_website_user,
	get_or_create_vendor_user,
	prepare_vendor_mail,
	send_vendor_email,
	send_vendor_mail_logic,
)
from approval_engine.settlement.doctype.vendor_email.vendor_reminder import (
	send_reminder_for_non_registered_vendors,
)

# Re-exported above so `utils.send_vendor_mail_logic` etc. stay valid
# import/mock.patch paths for existing callers and tests, even though the
# actual logic now lives in the sibling vendor_mail.py/vendor_reminder.py
# (split out to keep this file under the line-count cap).
__all__ = [
	"build_vendor_webform_link",
	"create_vendor",
	"create_website_user",
	"encode_email",
	"encode_string_part",
	"ensure_vendor_portal_role",
	"get_or_create_vendor_user",
	"prepare_vendor_mail",
	"send_reminder_for_non_registered_vendors",
	"send_vendor_email",
	"send_vendor_mail_logic",
]


def create_vendor(
	vendor_mail: str,
	reference_doctype: str,
	reference_docname: str | None,
	vendor_name: str | None = None,
	email_2: str | None = None,
	company: str | None = None,
) -> dict:
	"""
	Create a new Vendor Email record and kick off the onboarding invite
	email. Refuses to create a duplicate for an email that's already
	onboarding/onboarded.

	Parameters:
		vendor_mail (str, required): Vendor's primary email address.
		reference_doctype (str, required): DocType this onboarding is linked to.
		reference_docname (str, optional): Name of the linked reference document.
		vendor_name (str, optional): Vendor's display name.
		email_2 (str, optional): Secondary recipient for the same invite link.
		company (str, optional): Company the vendor is onboarding against.

	Returns:
		dict: Result of send_vendor_mail_logic() for a new vendor.

	Raises:
		frappe.ValidationError: If a Vendor Email record for `vendor_mail` already exists.
	"""
	if not frappe.db.exists("Vendor Email", vendor_mail):
		new_doc = frappe.new_doc("Vendor Email")
		new_doc.email = vendor_mail
		new_doc.email_2 = email_2 or ""
		new_doc.vendor_name = vendor_name or ""
		new_doc.company = company
		new_doc.reference_doctype = reference_doctype
		new_doc.reference_docname = reference_docname or ""
		new_doc.created_on = today()
		new_doc.flags.ignore_permissions = True
		new_doc.save()

		return send_vendor_mail_logic(
			new_doc.email,
			vendor_name,
			reference_docname,
			email_2=new_doc.email_2,
			company=new_doc.company,
		)
	else:
		frappe.throw(_("vendor <b>{0}</b> Already Exists").format(vendor_mail))


def ensure_vendor_portal_role() -> None:
	"""
	Idempotently create the "Vendor Portal" role and grant it read/write/
	create permission on Address, since vendors need to manage their own
	address records.

	Parameters:
		None

	Returns:
		None
	"""
	role_name = "Vendor Portal"

	# Create Role
	if not frappe.db.exists("Role", role_name):
		role = frappe.get_doc({"doctype": "Role", "role_name": role_name, "desk_access": 0})
		role.insert(ignore_permissions=True)

	# Create Address Permissions
	if not frappe.db.exists(
		"Custom DocPerm",
		{
			"parent": "Address",
			"role": role_name,
			"permlevel": 0,
		},
	):
		docperm = frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"parent": "Address",
				"parenttype": "DocType",
				"parentfield": "permissions",
				"role": role_name,
				"permlevel": 0,
				"read": 1,
				"write": 1,
				"create": 1,
			}
		)
		docperm.insert(ignore_permissions=True)
