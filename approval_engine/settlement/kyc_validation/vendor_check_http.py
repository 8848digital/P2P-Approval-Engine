# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Single-vendor HTTP call mechanics for KYC checks. Split out of
vendor_check.py to keep that file under the line-count cap - call_vendor_api
is imported back there (see that file) for run_kyc_validation/
revalidate_in_run/test_kyc_vendor to use.
"""

import json
import re
import time

import frappe
import requests
from frappe import _

PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

# Field names (by convention) that should be masked in stored logs even if an
# admin forgets to list them explicitly - belt and suspenders for Aadhaar etc.
SENSITIVE_KEY_HINTS = ("aadhaar", "aadhar", "adhar")


def _mask(value: str) -> str:
	"""Mask all but the last 4 characters of value with asterisks."""
	value = str(value)
	if len(value) <= 4:
		return "*" * len(value)
	return "*" * (len(value) - 4) + value[-4:]


def _mask_sensitive(payload_str: str, field_map) -> str:
	"""Best-effort masking of Aadhaar-like values inside a JSON string before it
	is written to the log, controlled by KYC Settings.mask_sensitive_data_in_logs."""
	try:
		data = json.loads(payload_str)
	except Exception:
		return payload_str

	def walk(obj):
		if isinstance(obj, dict):
			for k, v in obj.items():
				if isinstance(v, str) and any(h in k.lower() for h in SENSITIVE_KEY_HINTS):
					obj[k] = _mask(v)
				elif isinstance(v, dict | list):
					walk(v)
		elif isinstance(obj, list):
			for item in obj:
				walk(item)

	walk(data)
	return json.dumps(data, indent=2)


def _get_by_path(data, path):
	"""Resolve a dotted/indexed path (e.g. "a.b.0.c") against a nested dict/list."""
	if not path:
		return None
	cur = data
	for part in path.split("."):
		if isinstance(cur, dict):
			cur = cur.get(part)
		elif isinstance(cur, list):
			try:
				cur = cur[int(part)]
			except (ValueError, IndexError):
				return None
		else:
			return None
	return cur


def _resolve_values(vendor, supplier_doc):
	"""Return {placeholder_key: value} and raise a clear error if a mandatory
	Supplier field used by this vendor is empty."""
	values = {}
	missing = []
	for row in vendor.field_map:
		val = supplier_doc.get(row.supplier_fieldname)
		if (val is None or val == "") and row.is_mandatory:
			missing.append(row.supplier_fieldname)
		values[row.placeholder_key] = val or ""

	if missing:
		frappe.throw(
			_(
				"Supplier '{0}' is missing required field(s) for '{1}': {2}. "
				"Please fill these in on the Supplier form and try again."
			).format(supplier_doc.name, vendor.vendor_name, ", ".join(missing))
		)
	return values


def _build_request(vendor, values):
	"""Substitute placeholder values into the vendor's URL path and body template."""
	template = vendor.request_body_template or "{}"
	body_str = template
	url_path = vendor.endpoint_path
	for key, val in values.items():
		token = "{{" + key + "}}"
		body_str = body_str.replace(token, str(val))
		url_path = url_path.replace(token, str(val))
	return url_path, body_str


def _do_request(vendor, cred, url, body_str, values, timeout):
	"""Issue the actual HTTP request to the KYC vendor per its configured request style."""
	headers = {"Content-Type": "application/json"}
	if cred.auth_type != "None":
		token = cred.get_password("token")
		prefix = "Bearer " if cred.auth_type == "Bearer" else ("Basic " if cred.auth_type == "Basic" else "")
		headers[cred.header_key or "Authorization"] = f"{prefix}{token}"

	if vendor.request_style == "JSON Body":
		return requests.request(vendor.http_method, url, headers=headers, data=body_str, timeout=timeout)

	if vendor.request_style == "Form Data":
		form_headers = {k: v for k, v in headers.items() if k.lower() != "content-type"}
		return requests.request(vendor.http_method, url, headers=form_headers, data=values, timeout=timeout)

	# Query Params — endpoint_path already has placeholders substituted
	return requests.request(vendor.http_method, url, headers=headers, timeout=timeout)


def call_vendor_api(vendor_doc, supplier_doc, settings):
	"""Executes one KYC Vendor check against one Supplier. Returns a result dict.
	Never raises for HTTP/network failures — those are captured as Error/Failed status.
	Raises frappe.throw only for configuration/data problems (missing mandatory field etc.)."""
	if not vendor_doc.enabled:
		return {
			"status": "Skipped",
			"http_status_code": None,
			"message": _("Vendor is disabled"),
			"request": None,
			"response": None,
		}

	cred = frappe.get_doc("KYC Credential", vendor_doc.credential)
	if not cred.is_active:
		return {
			"status": "Error",
			"http_status_code": None,
			"message": _("Credential '{0}' is inactive").format(cred.credential_label),
			"request": None,
			"response": None,
		}

	values = _resolve_values(vendor_doc, supplier_doc)
	url_path, body_str = _build_request(vendor_doc, values)
	url = cred.base_url.rstrip("/") + "/" + url_path.lstrip("/")

	timeout = settings.request_timeout_seconds or 30
	max_attempts = (settings.max_retry_attempts or 0) + 1

	last_exc = None
	resp = None
	for attempt in range(1, max_attempts + 1):
		try:
			resp = _do_request(vendor_doc, cred, url, body_str, values, timeout)
			break
		except requests.exceptions.RequestException as e:
			last_exc = e
			if attempt < max_attempts:
				time.sleep(min(2 * attempt, 5))
			continue

	if resp is None:
		frappe.log_error(
			title=f"KYC Vendor call failed: {vendor_doc.name}",
			message=f"Supplier: {supplier_doc.name}\nURL: {url}\nError: {last_exc}",
		)
		return {
			"status": "Error",
			"http_status_code": None,
			"message": _("Network error after {0} attempt(s): {1}").format(max_attempts, str(last_exc)),
			"request": body_str,
			"response": None,
		}

	try:
		resp_json = resp.json()
	except Exception:
		resp_json = {"raw": resp.text[:2000]}

	status, message = _classify_response(vendor_doc, resp, resp_json)
	response_str = json.dumps(resp_json, indent=2)
	request_str = body_str

	if settings.mask_sensitive_data_in_logs:
		response_str = _mask_sensitive(response_str, vendor_doc.field_map)
		request_str = _mask_sensitive(request_str, vendor_doc.field_map)

	return {
		"status": status,
		"http_status_code": resp.status_code,
		"message": message,
		"request": request_str,
		"response": response_str,
	}


def _classify_response(vendor_doc, resp, resp_json):
	"""Classify a vendor HTTP response as Success/Failed/Error using the
	vendor's configured error/success paths and system-error keywords."""
	error_type_val = (
		_get_by_path(resp_json, vendor_doc.error_type_path) if vendor_doc.error_type_path else None
	)
	error_message_val = (
		_get_by_path(resp_json, vendor_doc.error_message_path) if vendor_doc.error_message_path else None
	)
	has_error = bool(error_type_val) or bool(error_message_val)

	if has_error:
		haystack = f"{error_type_val or ''} {error_message_val or ''}".lower()
		keywords = [
			k.strip().lower() for k in (vendor_doc.system_error_type_keywords or "").splitlines() if k.strip()
		]
		is_system_error = any(k in haystack for k in keywords)

		message = error_message_val or error_type_val or _("Request failed")
		return ("Error" if is_system_error else "Failed"), message

	# No explicit error object — fall back to HTTP status + success path check
	if not resp.ok:
		return "Error", _("HTTP {0} from provider").format(resp.status_code)

	success_val = _get_by_path(resp_json, vendor_doc.success_path)

	if vendor_doc.expected_success_value:
		is_success = (
			str(success_val or "").strip().lower() == vendor_doc.expected_success_value.strip().lower()
		)
	else:
		is_success = success_val not in (None, False, "", 0, {}, [])

	if is_success:
		message = (
			_get_by_path(resp_json, vendor_doc.success_message_path)
			if vendor_doc.success_message_path
			else None
		) or _("Verified successfully")
		return "Success", message

	return "Failed", _("Verification failed — please check the entered value(s) and retry")
