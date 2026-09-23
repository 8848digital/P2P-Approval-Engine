# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Personal-scope rules: which documents belong to a user's own dashboard view
(created by them, pending on them, or already approved/rejected by them).
"""

import frappe

from approval_engine.approval_settlement.customization.procure_to_pay.dashboard_config import _log


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
