# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Approval workflow constants and small shared helpers: role/workflow names,
approver pools, amount-field resolution and band conditions.
"""

import frappe

MAX_LEVELS = 4


# state -> docstatus ("0" draft, "1" submitted)
STATE_DOCSTATUS = {
	"Pending": "0",
	"Approved 1": "0",
	"Approved 2": "0",
	"Approved 3": "0",
	"Approved": "1",
	"On Hold by Approver 1": "0",
	"On Hold by Approver 2": "0",
	"On Hold by Approver 3": "0",
	"On Hold by Approver 4": "0",
	"Rejected": "1",
}


STATE_ORDER = list(STATE_DOCSTATUS.keys())


# Workflow State master styles
WORKFLOW_STATE_STYLES = {
	"Pending": "Warning",
	"Approved 1": "Primary",
	"Approved 2": "Primary",
	"Approved 3": "Primary",
	"Approved": "Success",
	"On Hold by Approver 1": "Inverse",
	"On Hold by Approver 2": "Inverse",
	"On Hold by Approver 3": "Inverse",
	"On Hold by Approver 4": "Inverse",
	"Rejected": "Danger",
}


# allow_edit role per state ("All" = built-in role held by everyone; int = Approver N)
ALLOW_EDIT = {
	"Pending": "All",
	"Approved 1": 1,
	"Approved 2": 2,
	"Approved 3": 3,
	"Approved": "All",
	"On Hold by Approver 1": 1,
	"On Hold by Approver 2": 2,
	"On Hold by Approver 3": 3,
	"On Hold by Approver 4": 4,
	"Rejected": "All",
}


# state a given tier acts FROM
STATE_FOR_TIER = {1: "Pending", 2: "Approved 1", 3: "Approved 2", 4: "Approved 3"}


ACTIONS = ["Approve", "Hold", "Reject"]


DEFAULT_AMOUNT_FIELDS = {
	"Purchase Order": "grand_total",
	"Purchase Invoice": "grand_total",
	"Payment Entry": "paid_amount",
}


def role_name(document_type, level):
	return f"{document_type} - Approver {level}"


def workflow_name(document_type):
	return f"{document_type} Approval"


def pool(row, level):
	return [
		row.get(f"approver_{level}_user_{u}")
		for u in range(1, 6)
		if row.get(f"approver_{level}_user_{u}")
	]


def configured_levels(row):
	return [level for level in range(1, MAX_LEVELS + 1) if pool(row, level)]


def amount_field_for(document_type):
	settings = frappe.get_single("Approval Settings")
	for r in settings.amount_fields:
		if r.document_type == document_type:
			return r.amount_field
	return DEFAULT_AMOUNT_FIELDS.get(document_type, "grand_total")


# Field types that can hold an amount to compare bands against.
AMOUNT_FIELDTYPES = ("Currency", "Float", "Int")


def resolve_amount_field(document_type):
	"""Describe the amount field the bands WILL compare against for `document_type`, so it can be
	shown/validated before a matrix is submitted (the field gets baked into conditions at
	generation, and today is silently defaulted). Returns:
	    amount_field : the resolved fieldname
	    is_explicit  : True if it comes from an Approval Settings mapping, False if a fallback default
	    exists       : True if that field actually exists as an amount field on the target DocType
	    label        : the field's label (or the fieldname if unresolved)
	"""
	settings = frappe.get_single("Approval Settings")
	explicit = next(
		(r.amount_field for r in settings.amount_fields if r.document_type == document_type), None
	)
	amount_field = explicit or DEFAULT_AMOUNT_FIELDS.get(document_type, "grand_total")

	df = frappe.get_meta(document_type).get_field(amount_field) if document_type else None
	exists = bool(df and df.fieldtype in AMOUNT_FIELDTYPES)
	return {
		"amount_field": amount_field,
		"is_explicit": bool(explicit),
		"exists": exists,
		"label": (df.label if df else None) or amount_field,
	}


def band_condition(amt_field, min_amount, max_amount):
	"""Bake the amount band into a condition. Bounds are INCLUSIVE on both ends
	(Min <= amount <= Max); bands start at the previous band's Max + the smallest
	currency unit (e.g. 100000 -> next Min 100000.01) — enforced in
	approval_matrix.py's _validate_bands, not here (this just embeds the row's own values).
	Max=0 => unbounded above, Min=0 => no lower bound (from 0), both 0 => matches all."""
	minv = min_amount or 0
	maxv = max_amount or 0
	parts = []
	if minv:
		parts.append(f"doc.{amt_field} >= {minv}")
	if maxv:
		parts.append(f"doc.{amt_field} <= {maxv}")
	return " and ".join(parts)


def find_band_row(document_type, company, department, amount):
	"""Return the matching Approval Matrix Detail row for (company, dept, amount), or None."""
	name = frappe.db.get_value(
		"Approval Matrix", {"document_type": document_type, "company": company, "docstatus": 1}, "name"
	)
	if not name:
		return None
	m = frappe.get_doc("Approval Matrix", name)
	for row in m.detail:
		if row.department != department:
			continue
		mn = row.min_amount or 0
		mx = row.max_amount or 0
		if (mn == 0 or amount >= mn) and (mx == 0 or amount <= mx):
			return row
	return None
