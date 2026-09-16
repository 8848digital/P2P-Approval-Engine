import base64

import frappe
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.utils import add_days, today


def send_reminder_for_non_registered_vendors() -> None:
	"""Send a reminder email to each new-vendor BRN whose onboarding
	webform was sent 2 days ago and still has no Supplier created."""
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


def encode_email(email: str) -> str:
	"""Encode an email address's local/domain parts separately as
	URL-safe base64, so it can ride in a query string (see
	send_reminder_for_non_registered_vendors's webform_link)."""
	local, domain = email.split("@")
	encoded_local = encode_string_part(local)
	encoded_domain = encode_string_part(domain)
	return f"{encoded_local}@{encoded_domain}"


def encode_string_part(part: str) -> str:
	"""Base64url-encode one string part (local or domain), padding stripped."""
	return base64.urlsafe_b64encode(part.encode()).decode().rstrip("=")


@frappe.whitelist()
def decode_email(encoded_email: str) -> str:
	"""
	Decode an email address previously encoded by encode_email().

	**Endpoint:** `/api/method/p2p_customization.settlement.doctype.brn.utils.decode_email`
	**HTTP Method:** GET, POST
	**Parameters:**
		- encoded_email (str, required): The base64url-encoded "local@domain" string
	**Response:** The decoded email address (str), serialized as JSON.
	"""
	encoded_local, encoded_domain = encoded_email.split("@")
	decoded_local = decode_string_part(encoded_local)
	decoded_domain = decode_string_part(encoded_domain)
	return f"{decoded_local}@{decoded_domain}"


def decode_string_part(encoded_part: str) -> str:
	"""Base64url-decode one string part encoded by encode_string_part()."""
	padding = "=" * (4 - len(encoded_part) % 4)
	encoded_part += padding
	return base64.urlsafe_b64decode(encoded_part.encode()).decode()


def create_po_from_brn(source_name, vendor=None):
	"""
	Map a submitted BRN into an unsaved Purchase Order.

	Parameters:
		source_name (str, required): The BRN document name to map from.
		vendor (str, optional): An existing_vendor from the BRN's
			Comparision table to set as the PO's supplier.

	Returns:
		Document: The mapped (unsaved) Purchase Order.
	"""
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


def _create_pi_from_brn(source_name, vendor=None):
	"""
	Map a submitted BRN into an unsaved Purchase Invoice.

	Parameters:
		source_name (str, required): The BRN document name to map from.
		vendor (str, optional): An existing_vendor from the BRN's
			Comparision table to set as the PI's supplier.

	Returns:
		Document: The mapped (unsaved) Purchase Invoice.
	"""
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


def set_supplier(source, target, vendor=None) -> None:
	"""
	get_mapped_doc postprocess: set target.supplier from vendor, after
	checking it's actually one of the BRN's Comparision-table vendors.

	Parameters:
		source (Document, required): The source BRN document.
		target (Document, required): The mapped Purchase Order/Invoice.
		vendor (str, optional): An existing_vendor to set as the supplier;
			leaves target.supplier unset if not given.

	Returns:
		None
	"""
	if not vendor:
		target.supplier = None
		return

	valid_vendors = {row.existing_vendor for row in get_comparison_vendor_rows(source.name)}
	if vendor not in valid_vendors:
		frappe.throw(
			_("{0} is not one of the vendors listed in this BRN's Comparision table.").format(vendor)
		)

	target.supplier = vendor
