# Copyright (c) 2026, p2p_customization
"""
Seeds KYC Credential + KYC Vendor records that mirror the endpoints in the
supplied Postman collection.

This is idempotent and safe to run multiple times: every insert is guarded
by a frappe.db.exists() check, so records that already exist are skipped,
not recreated or overwritten.

Wired into migrate via hooks.py:

    after_migrate = ["p2p_customization.settlement.kyc_validation.setup.run"]

It can still be run manually too:

    bench --site your-site execute p2p_customization.settlement.kyc_validation.setup.run

IMPORTANT: this creates credential rows with EMPTY tokens on purpose.
Open KYC Settings after running this and paste the real (rotated) tokens —
never hardcode secrets in code.

Seed data (VENDOR_DATA, CHECK_TYPES, CREDENTIALS, build_vendors) lives in
the sibling setup_data.py, split out to keep this file under the
line-count cap.
"""

import frappe

from p2p_customization.settlement.kyc_validation.setup_data import (
	CHECK_TYPES,
	CREDENTIALS,
	VENDOR_DATA,
	build_vendors,
)


def create_vendor_name() -> None:
	"""Seed the Vendor Name master records from VENDOR_DATA, skipping any that already exist."""
	for vendor_name in VENDOR_DATA:
		if frappe.db.exists("Vendor Name", vendor_name):
			continue
		frappe.get_doc({"doctype": "Vendor Name", "vendor": vendor_name}).insert(ignore_permissions=True)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit - migration/bench-execute seed script, not a web request


def _seed_check_types() -> None:
	"""Seed the KYC Type master records from CHECK_TYPES, skipping any that already exist."""
	for type_name in CHECK_TYPES:
		if frappe.db.exists("KYC Type", type_name):
			continue
		frappe.get_doc({"doctype": "KYC Type", "kyc": type_name}).insert(ignore_permissions=True)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit - migration/bench-execute seed script, not a web request


def _seed_credentials(settings) -> dict:
	"""Append any missing sandbox/prod credential rows to JFS Settings
	(left inactive with no token), and return {credential_label: name}
	for every credential row now present, including ones already there."""
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


def _seed_vendors(cred_by_label: dict) -> None:
	"""Seed the sample KYC Vendor configs (left disabled), skipping any
	kyc_type/vendor combination that already exists."""
	vendors = build_vendors(cred_by_label)

	created_any = False
	for v in vendors:
		if frappe.db.exists("KYC Vendor", f"{v['kyc_type']} - {v['vendor']}"):
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


def run():
	"""
	Entry point. Safe to call from bench execute OR from hooks.py's
	after_migrate list — every step below only creates records that don't
	already exist, and is a no-op otherwise.
	"""
	_seed_check_types()
	create_vendor_name()

	settings = frappe.get_single("JFS Settings")
	cred_by_label = _seed_credentials(settings)
	_seed_vendors(cred_by_label)

	print("Seed check complete (existing records were skipped). Now: open JFS Settings")
	print("(KYC Settings tab), paste real tokens, activate credentials, then open each")
	print("KYC Vendor, use 'Test with Sample Values', and tick Enabled.")
