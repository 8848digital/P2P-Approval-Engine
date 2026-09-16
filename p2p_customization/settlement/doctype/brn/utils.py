import base64
import urllib.parse

import frappe
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.utils import add_days, add_months, cint, getdate, today


def calculate_brn_expiry_date(date, months):
	"""
	Compute a BRN's service expiry date from its start date + duration.

	Parameters:
		date (str, required): The service start date.
		months (int, required): Duration of service, in months.

	Returns:
		date: date + months, anchored to the day before date (matches the
			existing "expires the day before the anniversary" convention).
	"""
	return add_months(getdate(add_days(date, -1)), cint(months))


# Send reminder emails to new vendors who haven't completed registration.
def send_reminder_for_non_registered_vendors():
	# Get BRNs that are new vendors
	vendors = frappe.get_all(
		"BRN",
		filters={"is_new_vendor": 1, "docstatus": 1, "sent_mail_on": add_days(today(), -2)},
		fields=["name", "new_vendor", "vendor_email"],
	)

	for vendor in vendors:
		if not vendor.vendor_email:
			continue

		# Check if Supplier already exists for this BRN
		exists = frappe.db.exists("Supplier", {"brn": vendor.name})
		if exists:
			continue  # skip reminder

		try:
			# Pre-fill both BRN and email in the webform
			webform_link = (
				f"{frappe.utils.get_url()}/vendor-onboarding-form/new?"
				f"brn={vendor.name}&email_id={encode_email(vendor.vendor_email)}"
			)

			subject = "Reminder: Complete Your Vendor Registration"
			message = f"""
			Hello {vendor.new_vendor},

			This is a reminder to complete your vendor registration.

			<a href="{webform_link}">Fill Vendor Details</a>
			"""

			frappe.sendmail(recipients=[vendor.vendor_email], subject=subject, message=message)

		except Exception as e:
			frappe.log_error(str(e), "Vendor Reminder Error")


# Encode email address in URL-safe Base64 format.
def encode_email(email):
	local, domain = email.split("@")
	encoded_local = encode_string_part(local)
	encoded_domain = encode_string_part(domain)
	encoded_email = f"{encoded_local}@{encoded_domain}"
	return encoded_email


# Encode a string part (local or domain) using Base64 without padding.
def encode_string_part(part):
	encoded_part = base64.urlsafe_b64encode(part.encode()).decode().rstrip("=")
	return encoded_part


# Decode a Base64-encoded email address back to normal.
@frappe.whitelist()
def decode_email(encoded_email):
	encoded_local, encoded_domain = encoded_email.split("@")
	decoded_local = decode_string_part(encoded_local)
	decoded_domain = decode_string_part(encoded_domain)
	decoded_email = f"{decoded_local}@{decoded_domain}"
	return decoded_email


# Decode a Base64-encoded string part back to text.
def decode_string_part(encoded_part):
	padding = "=" * (4 - len(encoded_part) % 4)
	encoded_part += padding
	decoded_part = base64.urlsafe_b64decode(encoded_part.encode()).decode()
	return decoded_part


# Create a Purchase Order document from a BRN using field mapping.
def create_po_from_brn(source_name, vendor=None):
	doc = get_mapped_doc(
		"BRN",
		source_name,
		{
			"BRN": {
				"doctype": "Purchase Order",
				"postprocess": lambda source, target, source_parent=None: set_supplier(
					source, target, vendor
				),
			},
			"BRN Item": {
				"doctype": "Purchase Order Item",
				"field_map": {"rate": "rate", "expense_gl": "expense_account"},
			},
		},
	)

	return doc


# Create a Purchase Invoice document from a BRN using field mapping.
def _create_pi_from_brn(source_name, vendor=None):
	doc = get_mapped_doc(
		"BRN",
		source_name,
		{
			"BRN": {
				"doctype": "Purchase Invoice",
				"postprocess": lambda source, target, source_parent=None: set_supplier(
					source, target, vendor
				),
			},
			"BRN Item": {
				"doctype": "Purchase Invoice Item",
				"field_map": {"rate": "rate", "expense_gl": "expense_account"},
			},
		},
	)

	return doc


def get_comparison_vendor_rows(brn_name):
	"""Comparision rows on this BRN that have an existing_vendor set --
	the candidates for the Create Purchase Order/Invoice flow. Not
	filtered on Preferred: that flag is for the new-vendor onboarding
	flow only (see add_onboard_vendor_button in brn.js), unrelated to
	which existing vendor a PO/PI gets created against."""
	return frappe.get_all(
		"BRN Comparision",
		filters={"parent": brn_name, "parenttype": "BRN", "existing_vendor": ["!=", ""]},
		fields=["existing_vendor"],
	)


def set_supplier(source, target, vendor=None):
	if not vendor:
		target.supplier = None
		return

	valid_vendors = {row.existing_vendor for row in get_comparison_vendor_rows(source.name)}
	if vendor not in valid_vendors:
		frappe.throw(
			_("{0} is not one of the vendors listed in this BRN's Comparision table.").format(vendor)
		)

	target.supplier = vendor


def msa_aggrement_validation(self, method):
	# Convert Supplier field (Yes/No) to checkbox value (1/0)
	msa_value = 1 if self.msa_agreement == 1 else 0

	# Get all BRNs where this supplier is selected as Existing Vendor or New Vendor
	brns = frappe.get_all(
		"Purchase Order",
		filters=[["docstatus", "!=", 2]],
		fields=["name", "is_existing_vendor", "is_new_vendor"],
	)

	for brn in brns:
		filters = {"name": brn.name}

		if brn.is_existing_vendor:
			filters["existing_vendor"] = self.name

		elif brn.is_new_vendor:
			filters["new_vendor"] = self.name

		else:
			continue

		if frappe.db.exists("BRN", filters):
			frappe.db.set_value("BRN", brn.name, "msa_agreement", msa_value, update_modified=False)
