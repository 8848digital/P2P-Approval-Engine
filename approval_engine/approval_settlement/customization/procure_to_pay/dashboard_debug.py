# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Debug tools for the Procure to Pay dashboards: raw counts and line items.
"""

import frappe
from frappe import _
from frappe.utils import cint, get_datetime

from approval_engine.approval_settlement.customization.procure_to_pay.dashboard_buckets import (
	_resolve_bucket,
	_state_field_for,
	_workflow_mode,
)
from approval_engine.approval_settlement.customization.procure_to_pay.dashboard_config import (
	APPROVAL_TARGET_KEYS,
	DEBUGGABLE_DOCTYPES,
	DOCTYPE_DATE_FIELD,
	DOCTYPE_TARGET_KEYS,
	_log,
)
from approval_engine.approval_settlement.customization.procure_to_pay.dashboard_filters import (
	_date_range_filter,
	_get_count,
	_has_field,
)
from approval_engine.approval_settlement.customization.procure_to_pay.dashboard_scope import (
	_my_pending_approval_names,
	_my_scope_context,
	_scope_context_filter,
)


def build_debug_raw_counts(settings, doctype, company=None, from_date=None, to_date=None):
	"""Scoped to the logged-in user, same as the dashboard itself -- this
	tool explains what that user's own chart is showing, not a company-wide
	total. Groups by (state, docstatus) and shows how each combination
	resolves via _resolve_bucket -- the same function the dashboard itself
	uses, so this can never disagree with what's on screen."""
	_log(
		"PCD: build_debug_raw_counts CALLED",
		f"doctype={doctype!r} company={company!r} from_date={from_date!r} to_date={to_date!r}",
	)

	if not doctype:
		_log("PCD: build_debug_raw_counts MISSING DOCTYPE", "Called with no 'doctype' argument.")
		frappe.throw(_("Please select a Doctype before running the debug tool."))

	# ignore_permissions below makes an open doctype argument a data leak --
	# same allowlist as build_debug_line_items.
	if doctype not in DEBUGGABLE_DOCTYPES:
		frappe.throw(_("Unsupported doctype for raw-count debug: {0}").format(doctype))

	target_keys = DOCTYPE_TARGET_KEYS.get(doctype, APPROVAL_TARGET_KEYS)
	is_payment_order = doctype == "Payment Order"

	filters = {}
	if company and _has_field(doctype, "company"):
		filters["company"] = company
	filters.update(
		_date_range_filter(from_date, to_date, fieldname=DOCTYPE_DATE_FIELD.get(doctype, "creation"))
	)
	filters.update(_scope_context_filter(_my_scope_context(doctype, frappe.session.user)))

	has_wf_field, wf_active, use_mapping, mapping = _workflow_mode(doctype, settings)
	state_field = _state_field_for(doctype, use_mapping, has_wf_field)

	total = frappe.db.count(doctype, filters=filters)
	_log(
		"PCD: build_debug_raw_counts filters/total",
		f"filters={filters}\ntotal_matching_documents={total}",
	)

	group_by = f"{state_field}, docstatus" if state_field else "docstatus"
	fields = ([f"{state_field} as state"] if state_field else []) + ["docstatus", {"COUNT": "name"}]
	rows = frappe.db.get_list(
		doctype, filters=filters, group_by=group_by, fields=fields, ignore_permissions=True
	)

	no_state_label = "(no workflow_state field on this doctype)"
	raw_counts = []
	for r in rows:
		bucket, source = _resolve_bucket(
			doctype, r.get("state"), r.docstatus, target_keys, mapping, use_mapping
		)
		raw_counts.append(
			{
				"workflow_state": r.get("state") or ("(blank)" if state_field else no_state_label),
				"docstatus": cint(r.docstatus),
				"count": _get_count(r),
				"resolved_bucket": bucket,
				"bucket_source": source,
			}
		)

	_log("PCD: build_debug_raw_counts RESULT", f"raw_counts={raw_counts}")

	return {
		"doctype": doctype,
		"filters_applied": filters,
		"has_workflow_state_field": has_wf_field,
		"workflow_active": wf_active,
		"mapping_rows_for_doctype": len(mapping),
		"using_mapping": use_mapping,
		"using_native_status_field": is_payment_order and not use_mapping,
		"total_matching_documents": total,
		"raw_counts": raw_counts,
	}


def build_debug_line_items(
	settings, doctype, company=None, from_date=None, to_date=None, limit=200
):
	"""One row per individual document, with the resolved bucket, so a
	specific record can be traced. Scoped to the logged-in user, same as
	the dashboard itself."""
	_log(
		"PCD: build_debug_line_items CALLED",
		f"doctype={doctype!r} company={company!r} from_date={from_date!r} to_date={to_date!r} limit={limit!r}",
	)

	if not doctype:
		_log("PCD: build_debug_line_items MISSING DOCTYPE", "Called with no 'doctype' argument.")
		frappe.throw(_("Please select a Doctype before running the debug tool."))

	if doctype not in DEBUGGABLE_DOCTYPES:
		_log("PCD: build_debug_line_items UNSUPPORTED DOCTYPE", f"doctype={doctype!r}")
		frappe.throw(_("Unsupported doctype for line-item debug: {0}").format(doctype))

	limit = cint(limit) or 200

	target_keys = DOCTYPE_TARGET_KEYS.get(doctype, APPROVAL_TARGET_KEYS)
	is_payment_order = doctype == "Payment Order"

	filters = {}
	if company and _has_field(doctype, "company"):
		filters["company"] = company
	filters.update(
		_date_range_filter(from_date, to_date, fieldname=DOCTYPE_DATE_FIELD.get(doctype, "creation"))
	)
	filters.update(_scope_context_filter(_my_scope_context(doctype, frappe.session.user)))

	has_wf_field, wf_active, use_mapping, mapping = _workflow_mode(doctype, settings)
	state_field = _state_field_for(doctype, use_mapping, has_wf_field)

	fields = ["name", "docstatus", "creation", "modified", "modified_by", "owner"]
	if state_field:
		# Always aliased to `workflow_state` in the result so the debug
		# dialog's single "state" column works unchanged for every doctype,
		# even when the underlying source is Payment Order's own `status`
		# field rather than a real workflow_state (see PAYMENT_ORDER_STATUS_BUCKET).
		fields.insert(1, f"{state_field} as workflow_state")

	_log("PCD: build_debug_line_items query", f"filters={filters}\nfields={fields}\nlimit={limit}")

	rows = frappe.db.get_list(
		doctype,
		filters=filters,
		fields=fields,
		order_by="creation desc",
		limit_page_length=limit,
		ignore_permissions=True,
	)
	_log("PCD: build_debug_line_items raw row count", f"row_count={len(rows)}")
	if not rows:
		_log(
			"PCD: build_debug_line_items ZERO ROWS", f"No {doctype} documents matched filters={filters}."
		)

	pending_on_me = _my_pending_approval_names(doctype, frappe.session.user) if rows else set()

	for r in rows:
		r["docstatus"] = cint(r["docstatus"])
		r["resolved_bucket"], r["bucket_source"] = _resolve_bucket(
			doctype, r.get("workflow_state"), r["docstatus"], target_keys, mapping, use_mapping
		)
		r["pending_on_me"] = r["name"] in pending_on_me
		if r.get("creation"):
			r["creation"] = get_datetime(r["creation"]).strftime("%Y-%m-%d %H:%M:%S")
		if r.get("modified"):
			r["modified"] = get_datetime(r["modified"]).strftime("%Y-%m-%d %H:%M:%S")

	return {
		"doctype": doctype,
		"filters_applied": filters,
		"has_workflow_state_field": has_wf_field,
		"workflow_active": wf_active,
		"using_mapping": use_mapping,
		"using_native_status_field": is_payment_order and not use_mapping,
		"row_count": len(rows),
		"hit_limit": len(rows) == limit,
		"rows": rows,
	}
