# Copyright (c) 2026, p2p_customization
"""
Patch: seed KYC Type, Vendor Name, KYC Settings credentials, and KYC Vendor
records that mirror the endpoints in the supplied Postman collection.

Idempotent - every insert is guarded by frappe.db.exists() (or an
existing-labels check for the credentials child table), so records that
already exist are skipped, not recreated or overwritten. Safe to re-run.

IMPORTANT: this creates credential rows with EMPTY tokens on purpose and
leaves them inactive (is_active = 0). Open JFS Settings (KYC Settings tab)
after migrating and paste the real (rotated) tokens - never hardcode
secrets in code.

KYC Vendor records are created disabled - open each one after migrating,
use "Test with Sample Values", then tick Enabled.

Registered in patches.txt as:
    p2p_customization.patches.v1_0.kyc_seed_records
"""

import frappe

CHECK_TYPES = [
	"GSTIN",
	"PAN",
	"PAN-Aadhaar Link",
	"MSME",
	"CIN",
	"DIN",
	"AML",
	"Aadhaar Mask",
	"Bank Account",
]

VENDOR_DATA = [
	"FRSLab",
	"SurePass",
]

CREDENTIALS = {
	"SurePass Sandbox": dict(provider="SurePass", base_url="https://sandbox.surepass.io", auth_type="Bearer"),
	"SurePass KYC API": dict(provider="SurePass", base_url="https://kyc-api.surepass.app", auth_type="Bearer"),
	"FRSLab Prod": dict(provider="FRSLab", base_url="https://api.atlaskyc.com/v2/prod", auth_type="Basic"),
}


def execute():
	frappe.reload_doc("settlement", "doctype", "kyc_type")
	frappe.reload_doc("settlement", "doctype", "vendor_name")
	frappe.reload_doc("settlement", "doctype", "kyc_credential")
	frappe.reload_doc("settlement", "doctype", "kyc_vendor")
	frappe.reload_doc("settlement", "doctype", "kyc_vendor_field_map")

	_seed_check_types()
	_seed_vendor_names()
	cred_by_label = _seed_credentials()
	_seed_vendors(cred_by_label)


def _seed_check_types():
	for type_name in CHECK_TYPES:
		if frappe.db.exists("KYC Type", type_name):
			continue
		frappe.get_doc({"doctype": "KYC Type", "kyc": type_name}).insert(ignore_permissions=True)
	frappe.db.commit()


def _seed_vendor_names():
	for vendor_name in VENDOR_DATA:
		if frappe.db.exists("Vendor Name", vendor_name):
			continue
		frappe.get_doc({"doctype": "Vendor Name", "vendor": vendor_name}).insert(ignore_permissions=True)
	frappe.db.commit()


def _seed_credentials():
	settings = frappe.get_single("JFS Settings")
	existing_labels = {row.credential_label for row in settings.credentials}

	added_any = False
	for label, cfg in CREDENTIALS.items():
		if label in existing_labels:
			continue
		settings.append(
			"credentials",
			{
				"credential_label": label,
				"provider": cfg["provider"],
				"base_url": cfg["base_url"],
				"auth_type": cfg["auth_type"],
				"header_key": "Authorization",
				"is_active": 0,  # left inactive until a real token is pasted in
			},
		)
		added_any = True

	if added_any:
		settings.save(ignore_permissions=True)
		frappe.db.commit()
		settings.reload()

	return {row.credential_label: row.name for row in settings.credentials}


def _seed_vendors(cred_by_label):
	vendors = [
		dict(
			vendor_name="GSTIN Verification - SurePass",
			vendor="SurePass",
			kyc_type="GSTIN",
			credential=cred_by_label["SurePass Sandbox"],
			http_method="POST",
			request_style="JSON Body",
			endpoint_path="/api/v1/corporate/gstin",
			request_body_template='{"id_number": "{{gstin}}"}',
			success_path="data.gstin",
			field_map=[dict(supplier_fieldname="gstin", placeholder_key="gstin", is_mandatory=1, sample_value="08AKWPJ1234H1ZN")],
		),
		dict(
			vendor_name="PAN Comprehensive - SurePass",
			kyc_type="PAN",
			vendor="SurePass",
			credential=cred_by_label["SurePass KYC API"],
			http_method="POST",
			request_style="JSON Body",
			endpoint_path="/api/v1/pan/pan-comprehensive",
			request_body_template='{"id_number": "{{pan}}"}',
			success_path="data.pan_number",
			field_map=[dict(supplier_fieldname="pan", placeholder_key="pan", is_mandatory=1, sample_value="EKRPR1234F")],
		),
		dict(
			vendor_name="MSME/Udyam Verification - SurePass",
			kyc_type="MSME",
			vendor="SurePass",
			credential=cred_by_label["SurePass Sandbox"],
			http_method="POST",
			request_style="JSON Body",
			endpoint_path="/api/v1/corporate/udyog-aadhaar",
			request_body_template='{"id_number": "{{udyam_no}}"}',
			success_path="data.udyam_number",
			field_map=[
				dict(
					supplier_fieldname="custom_udyam_registration_number",
					placeholder_key="udyam_no",
					is_mandatory=1,
					sample_value="UDYAM-GJ-25-00000000",
				)
			],
		),
		dict(
			vendor_name="CIN / Company Details - SurePass",
			kyc_type="CIN",
			vendor="SurePass",
			credential=cred_by_label["SurePass Sandbox"],
			http_method="POST",
			request_style="JSON Body",
			endpoint_path="/api/v1/corporate/company-details",
			request_body_template='{"id_number": "{{cin}}"}',
			success_path="data.company_name",
			field_map=[dict(supplier_fieldname="cin", placeholder_key="cin", is_mandatory=1, sample_value="U65999MH1995PLC123456")],
		),
		dict(
			vendor_name="PAN Verify - FRSLab",
			kyc_type="PAN",
			vendor="FRSLab",
			credential=cred_by_label["FRSLab Prod"],
			http_method="POST",
			request_style="Query Params",
			endpoint_path="/verify/pan?pan_number={{pan}}",
			request_body_template="",
			success_path="data",
			field_map=[dict(supplier_fieldname="pan", placeholder_key="pan", is_mandatory=1, sample_value="FXVPP8239P")],
		),
		dict(
			vendor_name="GSTIN Verify - FRSLab",
			kyc_type="GSTIN",
			vendor="FRSLab",
			credential=cred_by_label["FRSLab Prod"],
			http_method="POST",
			request_style="Query Params",
			endpoint_path="/verify/gstin?gst_number={{gstin}}",
			request_body_template="",
			success_path="data",
			field_map=[dict(supplier_fieldname="gstin", placeholder_key="gstin", is_mandatory=1, sample_value="27AABCR1466K1Z7")],
		),
		dict(
			vendor_name="PAN to Aadhaar Link Check - FRSLab",
			kyc_type="PAN-Aadhaar Link",
			vendor="FRSLab",
			credential=cred_by_label["FRSLab Prod"],
			http_method="POST",
			request_style="Form Data",
			endpoint_path="/verify/pantoadr",
			request_body_template='{"pan_no": "{{pan_no}}"}',
			success_path="data",
			field_map=[dict(supplier_fieldname="pan", placeholder_key="pan_no", is_mandatory=1, sample_value="FXVPP8239P")],
		),
		dict(
			vendor_name="MSME Verify - FRSLab",
			kyc_type="MSME",
			vendor="FRSLab",
			credential=cred_by_label["FRSLab Prod"],
			http_method="POST",
			request_style="Form Data",
			endpoint_path="/verify/msme",
			request_body_template='{"udyam_no": "{{udyam_no}}"}',
			success_path="data",
			field_map=[
				dict(
					supplier_fieldname="custom_udyam_registration_number",
					placeholder_key="udyam_no",
					is_mandatory=1,
					sample_value="UDYAM-MA-03-0009988",
				)
			],
		),
	]

	created_any = False
	for v in vendors:
		# autoname is f"{kyc_type} - {vendor}", not vendor_name -- check the
		# actual docname, or this guard never matches and every re-run tries
		# (and fails) to re-insert the same row.
		expected_name = f"{v['kyc_type']} - {v['vendor']}"
		if frappe.db.exists("KYC Vendor", expected_name):
			continue
		doc = frappe.new_doc("KYC Vendor")
		doc.update({k: val for k, val in v.items() if k != "field_map"})
		doc.enabled = 0  # left disabled until credentials are filled + tested
		for fm in v["field_map"]:
			doc.append("field_map", fm)
		doc.insert(ignore_permissions=True)
		created_any = True

	if created_any:
		frappe.db.commit()