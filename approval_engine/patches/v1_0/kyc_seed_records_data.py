# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Seed data for kyc_seed_records.py - split out to keep that patch file
under the line-count cap. See that file's docstring for context."""

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
	"SurePass KYC API": dict(
		provider="SurePass", base_url="https://kyc-api.surepass.app", auth_type="Bearer"
	),
	"FRSLab Prod": dict(provider="FRSLab", base_url="https://api.atlaskyc.com/v2/prod", auth_type="Basic"),
}


def build_vendors(cred_by_label):
	"""KYC Vendor seed rows -- a function (not a module-level constant) since
	each row's `credential` field needs the real Credential docname, only
	known after _seed_credentials() has run and returned cred_by_label."""
	return [
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
			field_map=[
				dict(
					supplier_fieldname="gstin",
					placeholder_key="gstin",
					is_mandatory=1,
					sample_value="08AKWPJ1234H1ZN",
				)
			],
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
			field_map=[
				dict(
					supplier_fieldname="pan", placeholder_key="pan", is_mandatory=1, sample_value="EKRPR1234F"
				)
			],
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
			field_map=[
				dict(
					supplier_fieldname="cin",
					placeholder_key="cin",
					is_mandatory=1,
					sample_value="U65999MH1995PLC123456",
				)
			],
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
			field_map=[
				dict(
					supplier_fieldname="pan", placeholder_key="pan", is_mandatory=1, sample_value="FXVPP8239P"
				)
			],
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
			field_map=[
				dict(
					supplier_fieldname="gstin",
					placeholder_key="gstin",
					is_mandatory=1,
					sample_value="27AABCR1466K1Z7",
				)
			],
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
			field_map=[
				dict(
					supplier_fieldname="pan",
					placeholder_key="pan_no",
					is_mandatory=1,
					sample_value="FXVPP8239P",
				)
			],
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
