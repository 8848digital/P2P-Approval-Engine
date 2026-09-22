# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Shared Procure-to-Pay / Payments Compliance dashboard data layer.

Used by TWO pages that render the identical dashboard but differ only in who
may access it and what extra actions they see:

  - page/procure_to_pay: open dashboard, no Payments Compliance Settings
    allowed_roles gate -- any user who can reach the page can view it.
  - page/procure_to_pay_management: the same dashboard, gated by Payments
    Compliance Settings' allowed_roles (see _check_permission), plus an
    "Update Account Closing" action gated by its own separate role list
    (see payments_compliance_period_closing_role.py / can_view_period_closing
    in that page's controller).

Everything in this module is access-control-agnostic on purpose -- each
page's own whitelisted controller decides whether to call _check_permission()
before calling into here. Do not add a permission check inside this module;
that decision belongs to the caller.

Personal by default, but not always: build_dashboard_payload's `scope_user`
picks between a personal view (documents a user created, UNIONed with
documents currently pending on them as an approval-workflow approver,
UNIONed with documents they already approved or rejected at their own
step -- see _my_scope_context) and a company-wide aggregate view with no
personal filtering at all (`scope_user=None`). The open dashboard only ever uses
the personal view, forced to frappe.session.user; the management dashboard
defaults to aggregate and can drill into any specific user's personal view
via its own "User" filter.

Bucketing rule (BRN / Payment Order / Purchase Order / Purchase Invoice all
land in one of [Approved/Processed, Rejected/Failed, Pending]), in priority
order -- see _resolve_bucket for the implementation:

  1. Workflow State Mapping wins, if configured. This site runs TWO
     different workflow engines depending on the doctype -- the custom
     user_based_workflow app's "Approval Workflow", or a standard Frappe
     "Workflow" -- both just write to the doctype's `workflow_state` field,
     so _is_workflow_active() checks for either one being active.
  2. Payment Order is the one exception that does NOT fall back to plain
     docstatus: it has its own real `status` field (Pending / Initiated /
     Failed / ...), which is the actual signal for whether a payment was
     processed -- docstatus=1 only means the record was submitted, not that
     a bank acted on it. See PAYMENT_ORDER_STATUS_BUCKET.
  3. Everything else falls back to plain docstatus: Draft=Pending,
     Submitted=Approved/Processed, Cancelled=Rejected/Failed.

Every bucket also carries an exact "which documents are in it" filter
(by document name, not an approximate docstatus/state filter) so a click
on a chart bucket always opens a list that matches the chart exactly --
see _status_counts.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, get_datetime, nowdate

ENABLE_VERBOSE_DEBUG_LOG = False


def _log(title, message):
	if not ENABLE_VERBOSE_DEBUG_LOG:
		return
	try:
		frappe.log_error(title=str(title)[:140], message=message)
	except Exception:
		pass


# target_keys convention used everywhere below: [FINAL_OK, FINAL_BAD, PENDING]
APPROVAL_TARGET_KEYS = ["Approved", "Rejected", "Pending"]
PAYMENT_TARGET_KEYS = ["Processed", "Failed", "Pending"]

DEBUGGABLE_DOCTYPES = ["BRN", "Payment Order", "Purchase Order", "Purchase Invoice"]

DOCTYPE_TARGET_KEYS = {
	"BRN": APPROVAL_TARGET_KEYS,
	"Purchase Order": APPROVAL_TARGET_KEYS,
	"Purchase Invoice": APPROVAL_TARGET_KEYS,
	"Payment Order": PAYMENT_TARGET_KEYS,
}

# Each doctype's real business/transaction date -- NOT `creation` (when the
# DB row was inserted), which can differ substantially from the transaction
# date for backdated entries or bulk imports. Filtering by `creation` made
# the dashboard's From/To Date disagree with what a user sees when they
# filter the doctype's own list view by the same range.
DOCTYPE_DATE_FIELD = {
	"BRN": "transaction_date",
	"Payment Order": "posting_date",
	"Purchase Order": "transaction_date",
	"Purchase Invoice": "posting_date",
}

# Payment Order has its own real `status` field (Pending / Pending Approval /
# Partially Approved / Approved / Partially Initiated / Initiated / Rejected
# / Failed / Partially Failed). Submission (docstatus=1) only means the
# record was saved -- it does NOT mean a bank has actually processed the
# payment, so "Payment Release Status" buckets by this field instead of
# docstatus. Values not present here fall back to plain docstatus bucketing
# (see _resolve_bucket) so nothing silently vanishes.
PAYMENT_ORDER_STATUS_BUCKET = {
	"approved": "Processed",
	"initiated": "Processed",
	"rejected": "Failed",
	"failed": "Failed",
	"partially failed": "Failed",
	"pending": "Pending",
	"pending approval": "Pending",
	"partially approved": "Pending",
	"partially initiated": "Pending",
}


def _get_settings():
	_log("PCD: _get_settings", "Fetching Payments Compliance Settings single doc")
	settings = frappe.get_single("Payments Compliance Settings")
	mapping_rows = settings.get("workflow_state_mapping") or []
	allowed_roles = [row.role for row in (settings.get("allowed_roles") or [])]
	_log(
		"PCD: settings loaded",
		f"allowed_roles={allowed_roles!r}\n"
		f"chart_types: brn={settings.brn_chart_type!r} payment_order={settings.payment_order_chart_type!r} "
		f"purchase_order={settings.purchase_order_chart_type!r} purchase_invoice={settings.purchase_invoice_chart_type!r} "
		f"msme={settings.msme_chart_type!r}\n"
		f"auto_refresh_seconds={settings.auto_refresh_seconds!r}\n"
		f"workflow_state_mapping rows={len(mapping_rows)}",
	)
	return settings


def _check_permission(settings):
	# Fail-closed by design: an empty Allowed Roles list blocks everyone,
	# not just users whose roles don't match. Callers decide whether to
	# invoke this at all -- see module docstring.
	allowed_roles = {row.role for row in (settings.get("allowed_roles") or []) if row.role}
	user_roles = set(frappe.get_roles())
	_log(
		"PCD: _check_permission",
		f"allowed_roles={allowed_roles!r}\nuser={frappe.session.user}\nuser_roles={user_roles}",
	)
	if not allowed_roles or not (allowed_roles & user_roles):
		_log(
			"PCD: PERMISSION DENIED",
			f"user={frappe.session.user} has none of allowed_roles={allowed_roles!r}.",
		)
		frappe.throw(
			_("You are not permitted to view the Payments Compliance Dashboard."),
			frappe.PermissionError,
		)


def _has_field(doctype, fieldname):
	return frappe.get_meta(doctype).has_field(fieldname)


def _get_count(row):
	return row.get("count", row.get("COUNT(`name`)", 0)) or 0


def _date_range_filter(from_date, to_date, fieldname="creation"):
	if from_date and to_date:
		result = {fieldname: ["between", [f"{from_date} 00:00:00", f"{to_date} 23:59:59"]]}
	elif from_date:
		result = {fieldname: [">=", f"{from_date} 00:00:00"]}
	elif to_date:
		result = {fieldname: ["<=", f"{to_date} 23:59:59"]}
	else:
		result = {}
	_log("PCD: _date_range_filter", f"from_date={from_date!r} to_date={to_date!r} -> {result}")
	return result


def _base_filters(doctype, company, from_date, to_date, extra=None, date_field=None):
	"""Company + date-range filters shared by both the count query and the
	click-through filter for every bucket of this doctype."""
	filters = {}
	if company and _has_field(doctype, "company"):
		filters["company"] = company
	filters.update(
		_date_range_filter(
			from_date, to_date, fieldname=date_field or DOCTYPE_DATE_FIELD.get(doctype, "creation")
		)
	)
	if extra:
		filters.update(extra)
	return filters


def _my_pending_approval_names(doctype, user):
	"""Documents where `user` is the current pending approver, per the
	user_based_workflow app's per-document Approval Workflow Action tracking
	doctype (reference_doctype/reference_name, approver/alternate_approver,
	is_current + status="Pending"). Returns an empty set if that app isn't
	installed or no Approval Workflow is configured for this doctype -- this
	is the doctype instance created per in-flight document, not the
	Approval Workflow template itself."""
	if not frappe.db.exists("DocType", "Approval Workflow Action"):
		return set()
	rows = frappe.get_all(
		"Approval Workflow Action",
		filters={"reference_doctype": doctype, "is_current": 1, "status": "Pending"},
		or_filters={"approver": user, "alternate_approver": user},
		pluck="reference_name",
	)
	_log(
		"PCD: _my_pending_approval_names",
		f"doctype={doctype!r} user={user!r} -> {len(rows)} pending-on-me action(s)",
	)
	return set(rows)


def _my_completed_approval_names(doctype, user):
	"""Documents where `user` has already completed (Approved) at least one
	step of the Approval Workflow Action chain -- action_by=user,
	status="Approved" -- regardless of whether the document has since moved
	on to a later approver. This is what lets a user who already did their
	part keep seeing the document (in their own Approved bucket, see
	_apply_scope_context_bucket) instead of dropping out of scope the moment
	it's no longer their turn."""
	if not frappe.db.exists("DocType", "Approval Workflow Action"):
		return set()
	rows = frappe.get_all(
		"Approval Workflow Action",
		filters={"reference_doctype": doctype, "status": "Approved", "action_by": user},
		pluck="reference_name",
	)
	_log(
		"PCD: _my_completed_approval_names",
		f"doctype={doctype!r} user={user!r} -> {len(rows)} completed-by-me action(s)",
	)
	return set(rows)


def _my_rejected_approval_names(doctype, user):
	"""Documents where `user` personally performed the Reject action at
	their own step -- action_by=user, status="Rejected". Kept separate from
	_my_completed_approval_names (which is Approved-only) so the bucket
	resolution can tell "I approved my step" apart from "I rejected my
	step" for a non-owner -- see _apply_scope_context_bucket."""
	if not frappe.db.exists("DocType", "Approval Workflow Action"):
		return set()
	rows = frappe.get_all(
		"Approval Workflow Action",
		filters={"reference_doctype": doctype, "status": "Rejected", "action_by": user},
		pluck="reference_name",
	)
	_log(
		"PCD: _my_rejected_approval_names",
		f"doctype={doctype!r} user={user!r} -> {len(rows)} rejected-by-me action(s)",
	)
	return set(rows)


def _my_scope_context(doctype, user):
	"""'My Items' scope for a doctype, broken down by WHY each document is
	in scope: created by `user`, currently pending on `user` as an
	approval-workflow approver, already approved by `user` at an earlier
	step (which may since have moved on to someone else entirely), or
	already rejected by `user` at their own step. Kept as separate sets
	(not just a union) so the bucket resolution can tell these apart --
	see _apply_scope_context_bucket."""
	owned = set(frappe.get_all(doctype, filters={"owner": user}, pluck="name"))
	pending_on_me = _my_pending_approval_names(doctype, user)
	completed_by_me = _my_completed_approval_names(doctype, user)
	rejected_by_me = _my_rejected_approval_names(doctype, user)
	_log(
		"PCD: _my_scope_context",
		f"doctype={doctype!r} user={user!r} owned={len(owned)} pending_on_me={len(pending_on_me)} "
		f"completed_by_me={len(completed_by_me)} rejected_by_me={len(rejected_by_me)}",
	)
	return {
		"owned": owned,
		"pending": pending_on_me,
		"completed": completed_by_me,
		"rejected": rejected_by_me,
	}


def _scope_context_filter(context):
	"""Ready-to-merge filter dict restricting a query to the union of a
	_my_scope_context() result. Uses a placeholder that matches nothing when
	the user has zero items, rather than relying on an empty `in` list."""
	names = context["owned"] | context["pending"] | context["completed"] | context["rejected"]
	return {"name": ["in", sorted(names) if names else [""]]}


def _apply_scope_context_bucket(name, doc_level_bucket, target_keys, scope_context):
	"""Per-viewing-user override of a document's bucket, given its
	doc-level bucket (the actual current/final state, same for everyone)
	and that user's _my_scope_context.

	The owner ALWAYS tracks the document's real, overall outcome -- Pending
	until it's actually fully resolved, then the real final bucket -- even
	if the owner also happens to be an approver at an early step and has
	already completed that step themselves (e.g. the creator is also the
	1st-level approver in some chains). Their own dashboard is "has MY
	request been fully processed", not "have I personally acted".

	A non-owner's bucket reflects the outcome of THEIR OWN action on the
	document, not the document's overall/final outcome -- these can differ
	once more than one approver is involved (e.g. Vinod and Shyam both
	approve their own steps, but Swati rejects at the final step: the
	document's real outcome is now Rejected, but Shyam should still see it
	in his own Approved bucket -- he did his part, and what happened at a
	later, unrelated step isn't his outcome to inherit). Concretely, for a
	non-owner:
	  - they rejected their own step -> Rejected, always.
	  - they approved their own step -> Approved, always (even after the
	    document later moves on, whether to further approval or to an
	    eventual rejection by someone downstream).
	  - otherwise, it's currently pending on them -> Pending.
	"""
	final_key, reject_key, pending_key = target_keys
	is_owner = name in scope_context["owned"]
	is_pending = name in scope_context["pending"]
	is_completed = name in scope_context["completed"]
	is_rejected = name in scope_context["rejected"]

	if is_owner:
		return doc_level_bucket

	if is_rejected:
		return reject_key
	if is_completed:
		return final_key
	if is_pending:
		return pending_key
	return doc_level_bucket


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
	custom_name = frappe.db.get_value("Approval Workflow", {"document_type": doctype, "is_active": 1}, "name")
	standard_name = frappe.db.get_value("Workflow", {"document_type": doctype, "is_active": 1}, "name")
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


def _msme_ageing(company, settings, from_date=None, to_date=None, extra_filters=None):
	base = _base_filters(
		"Purchase Invoice",
		company,
		from_date,
		to_date,
		extra={**(extra_filters or {}), "docstatus": 1, "status": ["not in", ["Paid", "Cancelled"]]},
	)

	_log("PCD: _msme_ageing filters", f"company={company!r} filters={base}")

	invoices = frappe.db.get_list(
		"Purchase Invoice", filters=base, fields=["name", "due_date"], ignore_permissions=True
	)
	_log("PCD: _msme_ageing invoices fetched", f"count={len(invoices)}\nsample={invoices[:5]}")
	if not invoices:
		_log("PCD: _msme_ageing ZERO INVOICES", f"No Purchase Invoice matched filters={base}.")

	b1 = settings.immediate_due_days or 5
	b2 = settings.bucket_2_end_days or 14
	b3 = settings.bucket_3_end_days or 30
	b4 = settings.bucket_4_end_days or 45

	# "Overdue" is last, not first: it's the worst case on the ageing
	# gradient (worse than merely being due in 31-45 days), matching the
	# existing green->red bucket color scheme (see BUCKET_COLORS in both
	# dashboards' JS) where later buckets are more severe.
	bucket_labels = [
		"Immediate Due",
		f"6-{b2} Days",
		f"{b2 + 1}-{b3} Days",
		f"{b3 + 1}-{b4} Days",
		"Overdue",
	]
	counts = {b: 0 for b in bucket_labels}
	today = nowdate()

	skipped_no_due_date = 0
	skipped_beyond_bucket4 = 0

	for inv in invoices:
		if not inv.due_date:
			skipped_no_due_date += 1
			continue
		# date_diff(due_date, today) is NEGATIVE once due_date is in the
		# past. That used to satisfy `days <= b1` same as a bill due days
		# from now, so an invoice overdue by months counted as "Immediate
		# Due" -- same bucket as one due tomorrow. Overdue (due_date
		# already passed) is now its own bucket, checked first.
		days = date_diff(inv.due_date, today)
		if days < 0:
			counts[bucket_labels[4]] += 1
		elif days <= b1:
			counts[bucket_labels[0]] += 1
		elif days <= b2:
			counts[bucket_labels[1]] += 1
		elif days <= b3:
			counts[bucket_labels[2]] += 1
		elif days <= b4:
			counts[bucket_labels[3]] += 1
		else:
			skipped_beyond_bucket4 += 1

	_log(
		"PCD: _msme_ageing RESULT",
		f"today={today}\nbucket_days=({b1},{b2},{b3},{b4})\ncounts={counts}\n"
		f"skipped_no_due_date={skipped_no_due_date}\nskipped_beyond_bucket4={skipped_beyond_bucket4}",
	)

	# Concrete due_date ranges per bucket, for click-through navigation.
	bucket_filters = {
		bucket_labels[4]: {**base, "due_date": ["<", today]},
		bucket_labels[0]: {**base, "due_date": ["between", [today, add_days(today, b1)]]},
		bucket_labels[1]: {**base, "due_date": ["between", [add_days(today, b1 + 1), add_days(today, b2)]]},
		bucket_labels[2]: {**base, "due_date": ["between", [add_days(today, b2 + 1), add_days(today, b3)]]},
		bucket_labels[3]: {**base, "due_date": ["between", [add_days(today, b3 + 1), add_days(today, b4)]]},
	}

	return counts, bucket_filters


def build_dashboard_payload(settings, company, from_date=None, to_date=None, scope_user=False):
	"""Single call: returns chart data + bucket click-through filters + UI settings.

	`scope_user` controls personal vs. aggregate scoping:
	  - Truthy (a user ID): every section is scoped to that user -- documents
	    they created, UNIONed with documents currently pending on them as an
	    approval-workflow approver, UNIONed with documents they already
	    approved or rejected at their own step (see _my_scope_context). This is the
	    open dashboard's only mode (always frappe.session.user), and the
	    management dashboard's mode when a specific "User" filter is set.
	  - `None` (explicitly, not just falsy): no personal scoping at all --
	    plain company-wide totals, every document's real current/final
	    bucket shown as-is. Only the management dashboard's default (no
	    User filter selected) uses this.
	  - The default value `False` is deliberately not a valid mode (neither
	    a user nor `None`) so a caller must pick one explicitly rather than
	    silently getting aggregate-by-omission.

	Access control is NOT this function's job -- see module docstring.
	"""
	_log(
		"PCD: build_dashboard_payload CALLED",
		f"company={company!r} from_date={from_date!r} to_date={to_date!r} "
		f"scope_user={scope_user!r} session_user={frappe.session.user}",
	)

	if scope_user is False:
		frappe.throw(
			_("build_dashboard_payload requires an explicit scope_user (a user ID, or None for aggregate).")
		)

	try:
		if not company:
			_log("PCD: build_dashboard_payload NO COMPANY", "company arg was empty/None -> throwing")
			frappe.throw(_("Please select a Company to view the dashboard."))

		def section(doctype, counts, bucket_filters):
			return {"doctype": doctype, "counts": counts, "bucket_filters": bucket_filters}

		scope_context = {}
		scope_filter = {}
		for dt in ("BRN", "Payment Order", "Purchase Order", "Purchase Invoice"):
			if scope_user:
				scope_context[dt] = _my_scope_context(dt, scope_user)
				scope_filter[dt] = _scope_context_filter(scope_context[dt])
			else:
				scope_context[dt] = None
				scope_filter[dt] = None

		brn_counts, brn_bf = _status_counts(
			"BRN",
			company,
			APPROVAL_TARGET_KEYS,
			settings,
			from_date,
			to_date,
			extra_filters=scope_filter.get("BRN"),
			scope_context=scope_context.get("BRN"),
		)
		po_counts, po_bf = _status_counts(
			"Payment Order",
			company,
			PAYMENT_TARGET_KEYS,
			settings,
			from_date,
			to_date,
			extra_filters=scope_filter.get("Payment Order"),
			scope_context=scope_context.get("Payment Order"),
		)
		puo_counts, puo_bf = _status_counts(
			"Purchase Order",
			company,
			APPROVAL_TARGET_KEYS,
			settings,
			from_date,
			to_date,
			extra_filters=scope_filter.get("Purchase Order"),
			scope_context=scope_context.get("Purchase Order"),
		)
		pi_counts, pi_bf = _status_counts(
			"Purchase Invoice",
			company,
			APPROVAL_TARGET_KEYS,
			settings,
			from_date,
			to_date,
			extra_filters=scope_filter.get("Purchase Invoice"),
			scope_context=scope_context.get("Purchase Invoice"),
		)
		msme_counts, msme_bf = _msme_ageing(
			company, settings, from_date, to_date, extra_filters=scope_filter.get("Purchase Invoice")
		)

		enable_related_party = cint(settings.get("enable_related_party_chart", 1))
		rp_counts, rp_bf = {}, {}
		if enable_related_party:
			rp_extra = {**(scope_filter.get("Purchase Invoice") or {}), "is_related_party_transaction": 1}
			rp_counts, rp_bf = _status_counts(
				"Purchase Invoice",
				company,
				APPROVAL_TARGET_KEYS,
				settings,
				from_date,
				to_date,
				extra_filters=rp_extra,
				scope_context=scope_context.get("Purchase Invoice"),
			)

		payload = {
			"brn": section("BRN", brn_counts, brn_bf),
			"payment_order": section("Payment Order", po_counts, po_bf),
			"purchase_order": section("Purchase Order", puo_counts, puo_bf),
			"purchase_invoice": section("Purchase Invoice", pi_counts, pi_bf),
			"msme": section("Purchase Invoice", msme_counts, msme_bf),
			"related_party": section("Purchase Invoice", rp_counts, rp_bf),
			"enable_related_party_chart": bool(enable_related_party),
			"chart_types": {
				"brn": settings.brn_chart_type or "Pie",
				"payment_order": settings.payment_order_chart_type or "Bar",
				"purchase_order": settings.purchase_order_chart_type or "Pie",
				"purchase_invoice": settings.purchase_invoice_chart_type or "Bar",
				"msme": settings.msme_chart_type or "Bar",
				"related_party": settings.related_party_chart_type or "Donut",
			},
			"auto_refresh_seconds": settings.auto_refresh_seconds or 0,
			"can_configure": "System Manager" in frappe.get_roles(),
			"is_aggregate_view": not bool(scope_user),
			"current_user": {
				"name": scope_user or None,
				"fullname": frappe.utils.get_fullname(scope_user) if scope_user else None,
			},
		}

		all_zero = all(
			all(v == 0 for v in section_data["counts"].values())
			for section_data in (
				payload["brn"],
				payload["payment_order"],
				payload["purchase_order"],
				payload["purchase_invoice"],
				payload["msme"],
			)
		)
		if all_zero:
			_log(
				"PCD: build_dashboard_payload ALL SECTIONS ZERO",
				f"company={company!r} from_date={from_date!r} to_date={to_date!r}\n"
				f"Every chart section came back all-zero -- check the per-doctype log entries just "
				f"above this one, and confirm with the 'Debug Raw Counts' dialog using the same "
				f"Company + date range.",
			)

		_log("PCD: build_dashboard_payload RETURNING", f"company={company!r}\npayload={payload}")
		return payload

	except frappe.PermissionError:
		raise
	except Exception:
		_log(
			"PCD: build_dashboard_payload EXCEPTION",
			f"company={company!r} user={frappe.session.user}\n\n{frappe.get_traceback()}",
		)
		raise


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
	_log("PCD: build_debug_raw_counts filters/total", f"filters={filters}\ntotal_matching_documents={total}")

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


def build_debug_line_items(settings, doctype, company=None, from_date=None, to_date=None, limit=200):
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
		_log("PCD: build_debug_line_items ZERO ROWS", f"No {doctype} documents matched filters={filters}.")

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


def build_error_logs(doctype=None, from_date=None, to_date=None, limit=100):
	"""Line-by-line Frappe Error Log viewer, scoped to this dashboard's doctypes and a date range."""
	_log(
		"PCD: build_error_logs CALLED",
		f"doctype={doctype!r} from_date={from_date!r} to_date={to_date!r} limit={limit!r}",
	)

	limit = cint(limit) or 100

	filters = {}
	filters.update(_date_range_filter(from_date, to_date, fieldname="creation"))
	if doctype:
		filters["error"] = ["like", f"%{doctype}%"]

	_log("PCD: build_error_logs filters", f"filters={filters}\nlimit={limit}")

	rows = frappe.db.get_list(
		"Error Log",
		filters=filters,
		fields=["name", "creation", "method", "error"],
		order_by="creation desc",
		limit_page_length=limit,
		ignore_permissions=True,
	)
	_log("PCD: build_error_logs raw row count", f"row_count={len(rows)}")

	out = []
	for r in rows:
		error_text = r.get("error") or ""
		lines = [ln for ln in error_text.splitlines() if ln.strip()]
		summary = lines[-1] if lines else "(empty error log)"
		out.append(
			{
				"name": r["name"],
				"creation": get_datetime(r["creation"]).strftime("%Y-%m-%d %H:%M:%S")
				if r.get("creation")
				else "",
				"method": r.get("method") or "",
				"summary": summary[:300],
				"line_count": len(lines),
				"full_text": error_text,
			}
		)

	return {"filters_applied": filters, "row_count": len(out), "hit_limit": len(out) == limit, "rows": out}
