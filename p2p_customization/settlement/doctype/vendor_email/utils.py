import base64
import urllib.parse

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import random_string, today
from frappe.utils.password import update_password


def send_vendor_mail_logic(
	vendor_email: str,
	vendor_name: str | None = None,
	reference_docname: str | None = None,
	email_2: str | None = None,
	company: str | None = None,
) -> dict:
	"""
	Send the vendor onboarding invite email(s), creating a website User for
	the vendor if one doesn't already exist.

	Parameters:
		vendor_email (str, required): Vendor's primary email address (also the login).
		vendor_name (str, optional): Vendor's display name.
		reference_docname (str, optional): Name of the linked reference document.
		email_2 (str, optional): Secondary recipient for the same invite link.
		company (str, optional): Company the vendor is onboarding against.

	Returns:
		dict: {"status": "ignored"|"success"|"error", "message": str}
	"""
	if not vendor_email:
		return {"status": "ignored", "message": "Not a new vendor or invalid conditions"}

	# Only ever one User, created against vendor_email -- email_2 (if given)
	# is just a second recipient for the same invite/login link, not a
	# second account.
	_user, password = get_or_create_vendor_user(vendor_email, vendor_name)
	webform_link = build_vendor_webform_link(
		vendor_email,
		reference_docname,
		company,
	)

	subject, message = prepare_vendor_mail(vendor_email, webform_link, password)
	results = [send_vendor_email(vendor_email, subject, message)]

	if email_2:
		# secondary_recipient=True swaps in a line clarifying that login
		# uses vendor_email, not this address -- there's no account under
		# email_2 to sign in with.
		subject_2, message_2 = prepare_vendor_mail(
			vendor_email, webform_link, password, secondary_recipient=True
		)
		results.append(send_vendor_email(email_2, subject_2, message_2))

	failures = [r for r in results if r.get("status") != "success"]
	if failures:
		return {"status": "error", "message": "; ".join(r["message"] for r in failures)}

	recipients = vendor_email + (f" and {email_2}" if email_2 else "")
	return {"status": "success", "message": f"Email sent to {recipients}"}


def get_or_create_vendor_user(vendor_email: str, vendor_name: str | None) -> tuple[Document, str | None]:
	"""
	Fetch the existing website User for a vendor email, or create one.
	Grants vendor-portal access on either path.

	Parameters:
		vendor_email (str, required): Vendor's email address, used as the User's name.
		vendor_name (str, optional): Vendor's display name, used for a new User's first name.

	Returns:
		tuple[Document, str | None]: The User document, and the newly
		generated password (None if the User already existed).
	"""
	password = None
	if not frappe.db.exists("User", vendor_email):
		password = random_string(10)
		user = create_website_user(vendor_email, vendor_name)
		update_password(user.name, password)
	else:
		user = frappe.get_doc("User", vendor_email)
		# Grant vendor-login access even if the account already existed --
		# this function only runs as part of vendor onboarding.
		if not user.get("vendor"):
			frappe.db.set_value("User", user.name, "vendor", 1)
	return user, password


def create_website_user(vendor_email: str, vendor_name: str | None) -> Document:
	"""
	Create a new Website User with the Vendor Portal role, enabling
	vendor-login access.

	Parameters:
		vendor_email (str, required): Email address for the new User.
		vendor_name (str, optional): First name to use; defaults to "Vendor".

	Returns:
		Document: The newly inserted User document.
	"""
	ensure_vendor_portal_role()

	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": vendor_email,
			"first_name": vendor_name or "Vendor",
			"enabled": 1,
			"send_welcome_email": 0,
			"user_type": "Website User",
			# Only users created through vendor onboarding may use /vendor-login.
			"vendor": 1,
		}
	)

	user.append("roles", {"role": "Vendor Portal"})

	user.insert(ignore_permissions=True)

	return user


def build_vendor_webform_link(
	vendor_email: str, reference_docname: str | None = None, company: str | None = None
) -> str:
	"""
	Build the /vendor-login redirect URL that lands a vendor on the bare
	onboarding web form, with their email (and optionally company)
	pre-filled via URL-encoded query params.

	Parameters:
		vendor_email (str, required): Vendor's email address.
		reference_docname (str, optional): Name of the linked reference document.
		company (str, optional): Company to pre-fill via `custom_company`.

	Returns:
		str: Full /vendor-login redirect URL.
	"""
	# Straight to the bare onboarding form, no portal shell -- a brand-new
	# vendor isn't "in the portal" until onboarding is actually done (see
	# get_vendor_landing_route()); the sidebar/embed only applies once
	# they're back to edit an existing Supplier record afterwards.
	#
	# custom_company (like email_id) is picked up automatically by the web
	# form's own set_default_values(), which merges every URL query param
	# straight into field values matched by exact fieldname -- the field
	# is read-only there, so this URL prefill is the only way it ever
	# shows a value before the vendor submits (sync_company_to_supplier
	# only runs at validate/submit time, too late for what's on screen).
	redirect_url = (
		f"/vendor-onboarding-form/new?"
		f"email_id={encode_email(vendor_email)}"
		f"&reference_docname={urllib.parse.quote(reference_docname or '')}"
	)
	if company:
		redirect_url += f"&custom_company={urllib.parse.quote(company)}"

	encoded_redirect = urllib.parse.quote(redirect_url)

	return f"{frappe.utils.get_url()}/vendor-login?redirect-to={encoded_redirect}"


def encode_email(email: str) -> str:
	"""
	Base64url-encode the local and domain parts of an email address
	independently, so the address survives being embedded in a URL query
	param without further escaping.

	Parameters:
		email (str, required): Email address in "local@domain" form.

	Returns:
		str: "<encoded_local>@<encoded_domain>"
	"""
	local, domain = email.split("@")
	encoded_local = encode_string_part(local)
	encoded_domain = encode_string_part(domain)
	encoded_email = f"{encoded_local}@{encoded_domain}"
	return encoded_email


def encode_string_part(part: str) -> str:
	"""
	Base64url-encode a single string, stripping padding.

	Parameters:
		part (str, required): String to encode.

	Returns:
		str: URL-safe base64 encoding of `part`, without `=` padding.
	"""
	encoded_part = base64.urlsafe_b64encode(part.encode()).decode().rstrip("=")
	return encoded_part


def prepare_vendor_mail(
	vendor_email: str,
	webform_link: str,
	password: str | None = None,
	secondary_recipient: bool = False,
) -> tuple[str, str]:
	"""
	Build the subject and HTML body for the vendor onboarding invite email.

	Parameters:
		vendor_email (str, required): Vendor's email address (the login).
		webform_link (str, required): Onboarding form URL to include in the message.
		password (str, optional): Generated password, included only for a brand-new User.
		secondary_recipient (bool, optional): True when this copy is going to `email_2`,
			to clarify that vendor_email (not this address) is the login. Defaults to False.

	Returns:
		tuple[str, str]: (subject, HTML message).
	"""
	subject = "Complete Your Vendor Registration"
	# Only one User/login exists, against vendor_email -- when this same
	# message goes to the second email address, make clear that's still
	# the login to use, not the address this landed in.
	secondary_note = (
		"You've been added as a second contact for this vendor registration. "
		"Please sign in with the email below, not this address. <br><br>"
		if secondary_recipient
		else ""
	)
	message = f"""
	Hello

	Welcome onboard! Please complete your vendor registration by logging in here:

	{secondary_note}
	Login: {vendor_email} <br>
	{"Password: " + password + "<br>" if password else ""}
	<a href="{webform_link}">Click here to fill your Vendor Details</a>
	"""
	return subject, message


def send_vendor_email(recipient: str, subject: str, message: str) -> dict:
	"""
	Send a single vendor-facing email, logging (rather than raising) on
	failure.

	Parameters:
		recipient (str, required): Email address to send to.
		subject (str, required): Email subject line.
		message (str, required): HTML email body.

	Returns:
		dict: {"status": "success"|"error", "message": str}
	"""
	try:
		frappe.sendmail(recipients=[recipient], subject=subject, message=message, delayed=False)
		return {"status": "success", "message": f"Email sent to {recipient}"}
	except Exception as e:
		frappe.log_error(message=str(e), title="Vendor Mail Error")
		return {"status": "error", "message": str(e)}


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
