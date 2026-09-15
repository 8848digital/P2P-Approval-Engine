import frappe
from frappe.utils import getdate, add_months, get_first_day, get_last_day

def __delete_linked_files(supplier):
	get_linked_files = frappe.db.get_all(
		"File",
		filters={
			"attached_to_doctype": "Supplier",
			"attached_to_name": supplier,
			"attached_to_field": ["in", ["gstin_attachment", "pan_attachment"]]
		},
		pluck="name"
	)

	if get_linked_files:
		for file_name in get_linked_files:
			frappe.delete_doc("File", file_name, force=True)

def __update_supplier(supplier):
	frappe.db.set_value("Supplier", supplier,
		{
			"gstin": "",
			"pan": "",
			"pan_attachment": "",
			"gstin_attachment": ""
		},
		update_modified=False
	)

def _send_supplier_status_mail(supplier, reason, action):
	"""Send email to supplier for Reject or Comment workflow actions."""
	# __delete_linked_files(supplier)
	# __update_supplier(supplier)

	vendor_email, supplier_name = frappe.db.get_value(
		"Supplier", supplier, ["email_id", "supplier_name"]
	)

	frappe.get_doc("Supplier", supplier).add_comment(
		"Comment",
		f"{action}: {reason}"
	)

	if not vendor_email:
		return "no_email"

	site_url = frappe.utils.get_url()
	webform_link = f"{site_url}/vendor-onboarding-form/{supplier}"

	action_lower = action.lower().strip()

	if action_lower == "reject":
		subject = "Vendor Registration Rejected"
		message = f"""
		Dear {supplier_name},<br><br>

		Thank you for registering as a vendor with our organization.<br><br>

		After reviewing the information submitted during the vendor onboarding process,
		we regret to inform you that your vendor registration request has been
		<b>rejected</b>.<br><br>

		<b>Reason for Rejection:</b><br>
		{reason}<br><br>

		You may review and update the required information using the link below:<br><br>

		<a href="{webform_link}">Update Vendor Details</a><br><br>

		Once the necessary corrections have been completed, you may resubmit your
		registration for further review.<br><br>
		"""

	else:  # Comment / Awaiting Response
		subject = "Vendor Registration Review - Additional Information Required"
		message = f"""
		Dear {supplier_name},<br><br>

		Thank you for registering as a vendor with our organization.<br><br>

		During the review of your vendor registration, our team identified that
		additional information or updates are required before we can proceed with
		the approval process.<br><br>

		<b>Reviewer Comments:</b><br>
		{reason}<br><br>

		Please review the comments above and update the required details using the
		link below:<br><br>

		<a href="{webform_link}">Update Vendor Details</a><br><br>

		Once the requested information has been updated, your registration will be
		reviewed again by our team.<br><br>

		"""

	frappe.sendmail(
		recipients=[vendor_email],
		subject=subject,
		message=message,
		delayed = False
	)

	return "sent"

def approval_mail(supplier_name, email_id):
	if email_id:
		message = f"""
			<div style="font-family: Arial, sans-serif; font-size: 14px; color: #333;">
				<p>Dear <strong>{supplier_name}</strong>,</p>

				<p>We are pleased to inform you that your supplier registration has been <strong>approved</strong> and your onboarding process is now complete.</p>

				<p>Welcome to our supplier network!</p>

				<p>As a verified supplier, you can now:</p>
				<ul style="margin-top: 10px; margin-bottom: 10px;">
					<li>Access and review <strong>Purchase Orders</strong> created for you</li>
					<li>Create <strong>Purchase Invoices</strong> against approved Purchase Orders.</li>
				</ul>

				<br>
				<a href="{frappe.utils.get_url()}/me" style="color: #1a73e8; text-decoration: none;">Visit Supplier Portal</a></p>
			</div>
		"""

		frappe.sendmail(
			recipients=email_id,
			subject="Welcome Aboard! Your Supplier Registration Has Been Approved",
			message=message,
			delayed = False
		)
		return "sent"
	return "no_email"