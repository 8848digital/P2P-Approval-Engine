import base64
import frappe
import urllib.parse
from frappe import _
from frappe.utils import today, random_string
from frappe.utils.password import update_password


def send_vendor_mail_logic(vendor_email, vendor_name=None, reference_docname=None, email_2=None, company=None):
	if not vendor_email:
		return {"status": "ignored", "message": "Not a new vendor or invalid conditions"}

	# Only ever one User, created against vendor_email -- email_2 (if given)
	# is just a second recipient for the same invite/login link, not a
	# second account.
	user, password = get_or_create_vendor_user(vendor_email, vendor_name)
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
		subject_2, message_2 = prepare_vendor_mail(vendor_email, webform_link, password, secondary_recipient=True)
		results.append(send_vendor_email(email_2, subject_2, message_2))

	failures = [r for r in results if r.get("status") != "success"]
	if failures:
		return {"status": "error", "message": "; ".join(r["message"] for r in failures)}

	recipients = vendor_email + (f" and {email_2}" if email_2 else "")
	return {"status": "success", "message": f"Email sent to {recipients}"}

def get_or_create_vendor_user(vendor_email, vendor_name):
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

def create_website_user(vendor_email, vendor_name):
	ensure_vendor_portal_role()

	user = frappe.get_doc({
		"doctype": "User",
		"email": vendor_email,
		"first_name": vendor_name or "Vendor",
		"enabled": 1,
		"send_welcome_email": 0,
		"user_type": "Website User",
		# Only users created through vendor onboarding may use /vendor-login.
		"vendor": 1,
	})

	user.append("roles", {
		"role": "Vendor Portal"
	})

	user.insert(ignore_permissions=True)

	return user

def build_vendor_webform_link(vendor_email, reference_docname=None, company=None):
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

def encode_email(email):
	local, domain = email.split("@")
	encoded_local = encode_string_part(local)
	encoded_domain = encode_string_part(domain)
	encoded_email = f"{encoded_local}@{encoded_domain}"
	return encoded_email

def encode_string_part(part):
	encoded_part = base64.urlsafe_b64encode(part.encode()).decode().rstrip("=")
	return encoded_part

def prepare_vendor_mail(vendor_email, webform_link, password=None, secondary_recipient=False):
	subject = "Complete Your Vendor Registration"
	# Only one User/login exists, against vendor_email -- when this same
	# message goes to the second email address, make clear that's still
	# the login to use, not the address this landed in.
	secondary_note = (
		f"You've been added as a second contact for this vendor registration. "
		f"Please sign in with the email below, not this address. <br><br>"
		if secondary_recipient else ""
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

def send_vendor_email(recipient, subject, message):
	try:
		frappe.sendmail(
			recipients=[recipient],
			subject=subject,
			message=message,
			delayed = False
		)
		return {"status": "success", "message": f"Email sent to {recipient}"}
	except Exception as e:
		frappe.log_error(message=str(e), title="Vendor Mail Error")
		return {"status": "error", "message": str(e)}

def create_vendor(vendor_mail, reference_doctype, reference_docname, vendor_name=None, email_2=None, company=None):
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

def send_reminder_for_non_registered_vendors():
	# Get vendors that are new vendors
	vendors = frappe.get_all(
		"Vendor Email",
		filters={
			"supplier_created": 0,
		},
		fields=["name", "email_2", "company"]
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

				frappe.sendmail(
					recipients=recipients,
					subject=subject,
					message=message,
					delayed=False
				)

			except Exception as e:
				frappe.log_error(str(e), "Vendor Reminder Error")

def ensure_vendor_portal_role():
	role_name = "Vendor Portal"

	# Create Role
	if not frappe.db.exists("Role", role_name):
		role = frappe.get_doc({
			"doctype": "Role",
			"role_name": role_name,
			"desk_access": 0
		})
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
		docperm = frappe.get_doc({
			"doctype": "Custom DocPerm",
			"parent": "Address",
			"parenttype": "DocType",
			"parentfield": "permissions",
			"role": role_name,
			"permlevel": 0,
			"read": 1,
			"write": 1,
			"create": 1,
		})
		docperm.insert(ignore_permissions=True)