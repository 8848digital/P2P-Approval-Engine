# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Business logic for running KYC Vendor checks against a Supplier.

Relocated out of settlement/kyc_validation/api.py (which is no longer a
whitelisted-endpoint file, see approval_settlement/api/v1/kyc_validation.py) so the
whitelisted wrappers stay thin per the app's api.md convention. Behavior is
unchanged from the original api.py implementation -- only the location and
whitelist decorators are new (removed here, since none of these are
directly HTTP-callable any more).

The single-vendor HTTP call mechanics (call_vendor_api and its helpers)
live in the sibling vendor_check_http.py, split out to keep this file
under the line-count cap.
"""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from approval_engine.approval_settlement.kyc_validation.vendor_check_http import call_vendor_api


def _settings():
	"""Return the singleton JFS Settings document."""
	return frappe.get_single("JFS Settings")


def _check_supplier_permission(supplier) -> None:
	"""Raise PermissionError unless the current user can write to this Supplier."""
	if not frappe.has_permission("Supplier", ptype="write", doc=supplier):
		frappe.throw(
			_("You do not have permission to run KYC validation for this Supplier"), frappe.PermissionError
		)


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
	frappe.db.commit()  # nosemgrep: frappe-manual-commit - durably persist the run/logs right after a slow, multi-vendor HTTP call loop

	return _run_summary(run)


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
	frappe.db.commit()  # nosemgrep: frappe-manual-commit - durably persist the run/logs right after a slow, multi-vendor HTTP call loop

	return _run_summary(run)


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
