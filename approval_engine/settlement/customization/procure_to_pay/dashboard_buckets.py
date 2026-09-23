# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Bucketing of documents into Approved/Rejected/Pending (or Processed/Failed/
Pending for Payment Order) -- see dashboard_data.py's module docstring.
"""

import frappe
from frappe.utils import cint

from approval_engine.settlement.customization.procure_to_pay.dashboard_config import (
	PAYMENT_ORDER_STATUS_BUCKET,
	_log,
)
from approval_engine.settlement.customization.procure_to_pay.dashboard_filters import (
	_base_filters,
	_has_field,
)
from approval_engine.settlement.customization.procure_to_pay.dashboard_scope import (
	_apply_scope_context_bucket,
)


def _docstatus_bucket(docstatus, target_keys):
	"""Plain, no-workflow bucketing: 0=Pending, 1=Approved(final), 2=Rejected/Cancelled(final-bad)."""
	final_key, reject_key, pending_key = target_keys
	d = cint(docstatus)
	if d == 1:
		return final_key
	if d == 2:
		return reject_key
	return pending_key


def _payment_order_bucket(status, docstatus):
	"""Resolve a single Payment Order's bucket from its native `status`
	field (see PAYMENT_ORDER_STATUS_BUCKET). A cancelled document
	(docstatus=2) is always Failed regardless of what `status` still says --
	cancellation overrides an in-flight/terminal status value that may not
	have been updated at cancel time. Returns None for a blank/unrecognised
	status so the caller can fall back to plain docstatus bucketing."""
	if cint(docstatus) == 2:
		return "Failed"
	return PAYMENT_ORDER_STATUS_BUCKET.get((status or "").strip().lower())


def _is_workflow_active(doctype):
	"""True if EITHER an active user_based_workflow "Approval Workflow" OR an
	active standard Frappe "Workflow" governs this doctype's workflow_state.
	Both mechanisms are in real use across this site's doctypes (e.g.
	Purchase Order/Purchase Invoice run on standard Frappe Workflow, not the
	custom app) and both write to the same `workflow_state` field, so a
	Workflow State Mapping row must be able to take effect regardless of
	which engine produced the state."""
	custom_name = frappe.db.get_value(
		"Approval Workflow", {"document_type": doctype, "is_active": 1}, "name"
	)
	standard_name = frappe.db.get_value(
		"Workflow", {"document_type": doctype, "is_active": 1}, "name"
	)
	_log(
		"PCD: _is_workflow_active",
		f"doctype={doctype!r} -> custom Approval Workflow={custom_name!r} standard Workflow={standard_name!r}",
	)
	return bool(custom_name or standard_name)


def _get_state_mapping(doctype, settings) -> dict:
	"""Build {workflow_state (lowercased) -> status_bucket} for doctype from
	Payments Compliance Settings' Workflow State Mapping rows, skipping any
	row for a different doctype or missing a state/bucket value."""
	mapping = {}
	for row in settings.get("workflow_state_mapping") or []:
		if row.reference_doctype != doctype:
			continue
		if not row.workflow_state or not row.status_bucket:
			continue
		mapping[row.workflow_state.strip().lower()] = row.status_bucket
	_log("PCD: _get_state_mapping", f"doctype={doctype!r} mapping={mapping}")
	return mapping


def _workflow_mode(doctype, settings):
	"""Single place that decides HOW a doctype gets bucketed. Returns
	(use_mapping, mapping): use_mapping is True only when a workflow is
	active for this doctype AND Payments Compliance Settings has at least
	one Workflow State Mapping row for it -- otherwise every doctype falls
	back to its own rule (see module docstring)."""
	has_wf_field = _has_field(doctype, "workflow_state")
	wf_active = _is_workflow_active(doctype) if has_wf_field else False
	mapping = _get_state_mapping(doctype, settings) if (has_wf_field and wf_active) else {}
	use_mapping = bool(mapping)
	return has_wf_field, wf_active, use_mapping, mapping


def _state_field_for(doctype, use_mapping, has_wf_field):
	"""Which single field to fetch as the "state" value for _resolve_bucket.

	A mapping match is ALWAYS against workflow_state, never Payment Order's
	`status` -- even for Payment Order, once a Workflow State Mapping is
	configured for it, workflow_state wins (see module docstring), so this
	must not just check "is this Payment Order" first."""
	if use_mapping:
		return "workflow_state"
	if doctype == "Payment Order":
		return "status"
	if has_wf_field:
		return "workflow_state"
	return None


def _resolve_bucket(doctype, state_value, docstatus, target_keys, mapping, use_mapping):
	"""Single source of truth for 'which bucket does this one document
	belong to' -- used by the dashboard counts, every click-through filter,
	and both debug tools, so none of them can ever disagree with each other.

	`state_value` is whatever state/status value was fetched for this row:
	workflow_state for a mapping lookup, or Payment Order's own `status`
	field when there's no mapping override (see module docstring).

	Returns (bucket_label, source) -- source is a short machine-readable
	tag explaining why, surfaced in the debug tools:
	  "mapping"                  -- matched a Workflow State Mapping row
	  "unmapped_fallback_to_docstatus" -- has workflow_state, but no mapping row for it
	  "status_field"             -- Payment Order's own status field, no workflow override
	  "cancelled_override"       -- docstatus=2 overrides a stale status/workflow_state value
	  "unrecognised_status_fallback_to_docstatus" -- Payment Order status not in our table
	  "docstatus_only"           -- plain docstatus (no workflow_state, or not active)
	"""
	final_key, reject_key, pending_key = target_keys
	bucket_label_for = {"Approved": final_key, "Rejected": reject_key, "Pending": pending_key}
	docstatus = cint(docstatus)

	if use_mapping:
		# Cancelled always wins, checked BEFORE consulting the mapping.
		# workflow_state is not cleared on cancel, so a state string mapped
		# to "Approved" can still be sitting on a docstatus=2 row (real
		# example: Purchase Order's "Proposal Created,PV&Final Approval"
		# appears on both genuinely-approved docstatus=1 rows and 29
		# cancelled docstatus=2 rows) -- without this check those cancelled
		# documents would incorrectly count as Approved.
		if docstatus == 2:
			return reject_key, "cancelled_override"
		generic_bucket = mapping.get((state_value or "").strip().lower())
		if generic_bucket:
			return bucket_label_for[generic_bucket], "mapping"
		return _docstatus_bucket(docstatus, target_keys), "unmapped_fallback_to_docstatus"

	if doctype == "Payment Order":
		bucket = _payment_order_bucket(state_value, docstatus)
		if bucket and docstatus == 2:
			return bucket, "cancelled_override"
		if bucket:
			return bucket, "status_field"
		return _docstatus_bucket(docstatus, target_keys), "unrecognised_status_fallback_to_docstatus"

	return _docstatus_bucket(docstatus, target_keys), "docstatus_only"


def _status_counts(
	doctype,
	company,
	target_keys,
	settings,
	from_date=None,
	to_date=None,
	extra_filters=None,
	scope_context=None,
):
	"""Bucket `doctype`'s documents into target_keys (see module docstring
	for the rule), and return (counts, bucket_filters):

	counts: {bucket_label: count}
	bucket_filters: {bucket_label: filter_dict} -- a ready-to-use frappe
	filter dict, keyed by exact document name, that reproduces exactly the
	rows counted in that bucket, for click-through navigation.

	Row-level, not a grouped/aggregate query: every call here is already
	scoped to "my items" (see _scope_context_filter), so result sets are
	small, and fetching full rows lets every bucket's click-through filter
	be an exact document-name list rather than an approximate docstatus/
	state filter -- important for Payment Order in particular, whose
	`status` field doesn't correlate with docstatus the way workflow_state
	does for the other three doctypes.

	`scope_context`: the _my_scope_context() dict for the user this call is
	personal-scoped to, or None for the aggregate/company-wide view (no
	per-user override -- every document's doc-level bucket is shown as-is).
	When given, a document that's only in scope because this user already
	completed their own step (see _apply_scope_context_bucket) shows in
	THEIR OWN Approved bucket while the document is still in flight,
	instead of its raw current-state bucket.
	"""
	filters = _base_filters(doctype, company, from_date, to_date, extra=extra_filters)
	has_wf_field, wf_active, use_mapping, mapping = _workflow_mode(doctype, settings)
	state_field = _state_field_for(doctype, use_mapping, has_wf_field)

	_log(
		f"PCD: {doctype} bucketing mode",
		f"has_wf_field={has_wf_field} workflow_active={wf_active} mapping_rows={len(mapping)} "
		f"-> use_mapping={use_mapping} state_field={state_field!r} filters={filters}",
	)

	# ignore_permissions: this dashboard's OWN access control is the page/
	# settings-level allowed_roles check (see module docstring) -- not
	# per-document read permissions. A user who can reach the dashboard
	# but lacks doctype-level read access to e.g. BRN (a real, common case
	# for Payments Compliance Viewer and similar roles) would otherwise get
	# "Insufficient Permission" instead of their chart data.
	fields = ["name", "docstatus"] + ([f"{state_field} as state"] if state_field else [])
	rows = frappe.db.get_list(doctype, filters=filters, fields=fields, ignore_permissions=True)
	_log(f"PCD: {doctype} raw rows", f"row_count={len(rows)}")

	counts = {k: 0 for k in target_keys}
	bucket_names = {k: [] for k in target_keys}
	for r in rows:
		bucket, source = _resolve_bucket(
			doctype, r.get("state"), r.docstatus, target_keys, mapping, use_mapping
		)
		if source == "unmapped_fallback_to_docstatus":
			_log(
				f"PCD: {doctype} UNMAPPED workflow_state",
				f"workflow_state={r.get('state')!r} docstatus={cint(r.docstatus)} document={r.name!r} "
				f"-> fell back to docstatus bucket {bucket!r}. Add a row for this state in "
				f"Payments Compliance Settings > Workflow State Mapping to control it explicitly.",
			)
		if scope_context is not None:
			bucket = _apply_scope_context_bucket(r.name, bucket, target_keys, scope_context)
		bucket_names[bucket].append(r.name)
		counts[bucket] += 1

	bucket_filters = {
		key: {**filters, "name": ["in", sorted(bucket_names[key]) or [""]]} for key in target_keys
	}
	_log(f"PCD: {doctype} RESULT", f"counts={counts}")
	return counts, bucket_filters
