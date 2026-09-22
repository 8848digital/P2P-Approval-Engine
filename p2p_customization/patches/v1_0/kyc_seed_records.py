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

Seed data (CHECK_TYPES, VENDOR_DATA, CREDENTIALS, build_vendors) lives in
the sibling kyc_seed_records_data.py, split out to keep this file under
the line-count cap.

Registered in patches.txt as:
    p2p_customization.patches.v1_0.kyc_seed_records
"""

import frappe

from p2p_customization.patches.v1_0.kyc_seed_records_data import (
	CHECK_TYPES,
	CREDENTIALS,
	VENDOR_DATA,
	build_vendors,
)


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
	frappe.db.commit()  # nosemgrep: frappe-manual-commit - migration/bench-execute seed script, not a web request


def _seed_vendor_names():
	for vendor_name in VENDOR_DATA:
		if frappe.db.exists("Vendor Name", vendor_name):
			continue
		frappe.get_doc({"doctype": "Vendor Name", "vendor": vendor_name}).insert(ignore_permissions=True)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit - migration/bench-execute seed script, not a web request


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
		frappe.db.commit()  # nosemgrep: frappe-manual-commit - migration/bench-execute seed script, not a web request
		settings.reload()

	return {row.credential_label: row.name for row in settings.credentials}


def _seed_vendors(cred_by_label):
	vendors = build_vendors(cred_by_label)

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
		frappe.db.commit()  # nosemgrep: frappe-manual-commit - migration/bench-execute seed script, not a web request
