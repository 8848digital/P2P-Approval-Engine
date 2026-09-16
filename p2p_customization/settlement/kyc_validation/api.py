# Copyright (c) 2026, p2p_customization
import json
import re
import time

import frappe
import requests
from frappe import _
from frappe.utils import now_datetime

PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

# Field names (by convention) that should be masked in stored logs even if an
# admin forgets to list them explicitly - belt and suspenders for Aadhaar etc.
SENSITIVE_KEY_HINTS = ("aadhaar", "aadhar", "adhar")


def _settings():
	"""Return the singleton JFS Settings document."""
	return frappe.get_single("JFS Settings")


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
				elif isinstance(v, (dict, list)):
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


def _check_supplier_permission(supplier) -> None:
	"""Raise PermissionError unless the current user can write to this Supplier."""
	if not frappe.has_permission("Supplier", ptype="write", doc=supplier):
		frappe.throw(
			_("You do not have permission to run KYC validation for this Supplier"), frappe.PermissionError
		)


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


def call_vendor_api(vendor_doc, supplier_doc, settings=None):
	"""Executes one KYC Vendor check against one Supplier. Returns a result dict.
	Never raises for HTTP/network failures — those are captured as Error/Failed status.
	Raises frappe.throw only for configuration/data problems (missing mandatory field etc.)."""
	settings = settings or _settings()

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


def _append_log_row(run, vendor_name, result, attempt_no, remarks=None) -> None:
	"""Append one KYC Validation Log child row to run, from a call_vendor_api() result."""
	run.append(
		"logs",
		{
			"kyc_vendor": vendor_name,
			"kyc_type": frappe.db.get_value("KYC Vendor", vendor_name, "kyc_type"),
			"attempt_no": attempt_no,
			"status": result["status"],
			"http_status_code": result["http_status_code"],
			"message": result["message"],
			"request_payload": result["request"],
			"response_payload": result["response"],
			"remarks": remarks,
			"checked_on": now_datetime(),
			"checked_by": frappe.session.user,
		},
	)


@frappe.whitelist()
def get_kyc_vendor_options(supplier=None):
	"""Enabled vendors for the multiselect dialog, flagged with whether they
	should be pre-checked by default."""
	settings = _settings()
	default_names = {d.kyc_vendor for d in (settings.default_kyc_vendors or [])}

	vendors = frappe.get_all(
		"KYC Vendor",
		filters={"enabled": 1},
		fields=["name", "vendor_name", "kyc_type", "is_default", "description", "icon"],
		order_by="sort_order asc, kyc_type asc, vendor_name asc",
	)
	for v in vendors:
		v["checked"] = bool(v["is_default"]) or (v["name"] in default_names)

	return vendors


@frappe.whitelist()
def run_kyc_validation(supplier, vendors):
	"""Create a fresh KYC Validation Run for the given Supplier + selected vendors."""
	_check_supplier_permission(supplier)
	vendors = json.loads(vendors) if isinstance(vendors, str) else vendors
	if not vendors:
		frappe.throw(_("Select at least one KYC check to run"))

	supplier_doc = frappe.get_doc("Supplier", supplier)
	settings = _settings()

	run = frappe.new_doc("KYC Validation Run")
	run.supplier = supplier
	run.run_by = frappe.session.user
	run.run_on = now_datetime()

	for vendor_name in vendors:
		vendor_doc = frappe.get_doc("KYC Vendor", vendor_name)
		result = call_vendor_api(vendor_doc, supplier_doc, settings)
		_append_log_row(run, vendor_name, result, attempt_no=1)

	run.insert(ignore_permissions=True)
	frappe.db.commit()

	return _run_summary(run)


@frappe.whitelist()
def revalidate_in_run(run_name, vendors, remarks=None):
	"""Re-run one or more vendor checks inside an EXISTING run, appending new
	log rows (attempt_no incremented) so the full history is preserved.
	Used both by the Supplier dialog's per-check 'Revalidate' action and by
	the KYC Validation Run form's row-level / bulk revalidate buttons."""
	vendors = json.loads(vendors) if isinstance(vendors, str) else vendors
	run = frappe.get_doc("KYC Validation Run", run_name)
	_check_supplier_permission(run.supplier)

	supplier_doc = frappe.get_doc("Supplier", run.supplier)
	settings = _settings()

	for vendor_name in vendors:
		prior_attempts = [r.attempt_no for r in run.logs if r.kyc_vendor == vendor_name]
		next_attempt = (max(prior_attempts) + 1) if prior_attempts else 1

		vendor_doc = frappe.get_doc("KYC Vendor", vendor_name)
		result = call_vendor_api(vendor_doc, supplier_doc, settings)
		_append_log_row(run, vendor_name, result, attempt_no=next_attempt, remarks=remarks)

	run.save(ignore_permissions=True)
	frappe.db.commit()

	return _run_summary(run)


@frappe.whitelist()
def test_kyc_vendor(vendor_name):
	"""Used by the 'Test with Sample Values' button on the KYC Vendor form.
	Runs the API call using each Field Map row's Sample Value instead of a
	real Supplier's data — lets an admin validate the template before
	turning a vendor Enabled."""
	if not frappe.has_permission("KYC Vendor", ptype="write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	vendor_doc = frappe.get_doc("KYC Vendor", vendor_name)

	class _FakeSupplier(dict):
		def get(self, key, default=None):
			return dict.get(self, key, default)

	fake = _FakeSupplier(
		{row.supplier_fieldname: (row.sample_value or "TEST123") for row in vendor_doc.field_map}
	)
	fake.name = "TEST-SUPPLIER"

	settings = _settings()
	return call_vendor_api(vendor_doc, fake, settings)


def _run_summary(run):
	"""Build the {run, overall_status, ...rows} summary dict returned to the client."""
	return {
		"run": run.name,
		"overall_status": run.overall_status,
		"total_checks": run.total_checks,
		"success_count": run.success_count,
		"failed_count": run.failed_count,
		"rows": [
			{
				"vendor": r.kyc_vendor,
				"kyc_type": r.kyc_type,
				"status": r.status,
				"message": r.message,
				"attempt_no": r.attempt_no,
				"checked_on": frappe.utils.format_datetime(r.checked_on),
			}
			for r in run.logs
		],
	}


@frappe.whitelist()
def get_last_kyc_run(supplier):
	"""
	Return the most recent KYC Validation Run for supplier, with one row
	per vendor/kyc_type showing only its latest attempt.

	Kept as raw SQL rather than frappe.qb: this is a "latest row per
	group" query (max(attempt_no) per kyc_vendor, joined back to fetch
	the full matching row) -- exactly the kind of correlated-subquery
	shape database.md's skill carves out alongside window functions/CTEs
	as not cleanly expressible via frappe.qb.
	"""
	last_run = frappe.db.get_value(
		"KYC Validation Run",
		{"supplier": supplier},
		["name", "overall_status"],
		order_by="creation desc",
		as_dict=True,
	)
	if not last_run:
		return None

	rows = frappe.db.sql(
		"""
		select t1.kyc_vendor, t1.kyc_type, t1.status, t1.message, t1.attempt_no
		from `tabKYC Validation Log` t1
		inner join (
			select kyc_vendor, max(attempt_no) as max_attempt
			from `tabKYC Validation Log`
			where parent = %(run)s
			group by kyc_vendor
		) t2 on t1.kyc_vendor = t2.kyc_vendor and t1.attempt_no = t2.max_attempt
		where t1.parent = %(run)s
		""",
		{"run": last_run.name},
		as_dict=True,
	)
	success_count = len([r for r in rows if r.status == "Success"])
	return {
		"run": last_run.name,
		"overall_status": last_run.overall_status,
		"success_count": success_count,
		"total_checks": len(rows),
		"rows": rows,
	}
