# Copyright (c) 2026, p2p_customization
"""Whitelisted endpoints for running KYC Vendor checks against a Supplier.

Thin wrappers only -- the actual vendor-call/logging logic lives in
settlement/kyc_validation/vendor_check.py.
"""

import frappe

from p2p_customization.settlement.kyc_validation import vendor_check


@frappe.whitelist(methods=["GET", "POST"])
def get_kyc_vendor_options(supplier: str | None = None):
	"""
		List the enabled KYC Vendors available for a Supplier's KYC dialog.

		**Endpoint:** `/api/method/p2p_customization.settlement.api.v1.kyc_validation.get_kyc_vendor_options`
		**HTTP Method:** GET, POST
		**Parameters:**
			- supplier (str, optional): The Supplier name (currently unused for
			  filtering, kept for forward-compatibility with the caller's args)
		**Response:**
	```json
			[{"name": "VEND-0001", "vendor_name": "Vendor A", "kyc_type": "PAN", "checked": true}]
	```
	"""
	return vendor_check.get_kyc_vendor_options(supplier)


@frappe.whitelist(methods=["POST"])
def run_kyc_validation(supplier: str, vendors: str | list):
	"""
		Create a fresh KYC Validation Run for a Supplier against the selected vendors.

		**Endpoint:** `/api/method/p2p_customization.settlement.api.v1.kyc_validation.run_kyc_validation`
		**HTTP Method:** POST
		**Parameters:**
			- supplier (str, required): The Supplier to validate
			- vendors (str | list, required): JSON-encoded list (or list) of KYC Vendor names to run
		**Response:**
	```json
			{
				"run": "KVR-0001",
				"overall_status": "Success",
				"total_checks": 2,
				"success_count": 2,
				"failed_count": 0,
				"rows": []
			}
	```
	"""
	return vendor_check.run_kyc_validation(supplier, vendors)


@frappe.whitelist(methods=["POST"])
def revalidate_in_run(run_name: str, vendors: str | list, remarks: str | None = None):
	"""
	Re-run one or more vendor checks inside an existing KYC Validation Run.

	Appends new log rows (attempt_no incremented) so the full history is
	preserved. Used by both the Supplier dialog's per-check revalidate
	action and the KYC Validation Run form's row-level/bulk revalidate buttons.

	**Endpoint:** `/api/method/p2p_customization.settlement.api.v1.kyc_validation.revalidate_in_run`
	**HTTP Method:** POST
	**Parameters:**
		- run_name (str, required): The KYC Validation Run to append to
		- vendors (str | list, required): JSON-encoded list (or list) of KYC Vendor names to re-run
		- remarks (str, optional): Free-text remarks stored against the new log rows
	**Response:** Same shape as `run_kyc_validation`.
	"""
	return vendor_check.revalidate_in_run(run_name, vendors, remarks)


@frappe.whitelist(methods=["POST"])
def test_kyc_vendor(vendor_name: str):
	"""
		Test a KYC Vendor's configured template using its Field Map sample values.

		Used by the 'Test with Sample Values' button on the KYC Vendor form to
		validate the request/response template before enabling a vendor.

		**Endpoint:** `/api/method/p2p_customization.settlement.api.v1.kyc_validation.test_kyc_vendor`
		**HTTP Method:** POST
		**Parameters:**
			- vendor_name (str, required): The KYC Vendor to test
		**Response:**
	```json
			{
				"status": "Success",
				"http_status_code": 200,
				"message": "Verified successfully",
				"request": "{}",
				"response": "{}"
			}
	```
	"""
	return vendor_check.test_kyc_vendor(vendor_name)


@frappe.whitelist(methods=["GET", "POST"])
def get_last_kyc_run(supplier: str):
	"""
		Return the most recent KYC Validation Run for a Supplier.

		One row per vendor/kyc_type, showing only its latest attempt.

		**Endpoint:** `/api/method/p2p_customization.settlement.api.v1.kyc_validation.get_last_kyc_run`
		**HTTP Method:** GET, POST
		**Parameters:**
			- supplier (str, required): The Supplier to look up
		**Response:**
	```json
			{
				"run": "KVR-0001",
				"overall_status": "Success",
				"success_count": 2,
				"total_checks": 2,
				"rows": []
			}
	```
		  or `null` if no prior run exists.
	"""
	return vendor_check.get_last_kyc_run(supplier)
