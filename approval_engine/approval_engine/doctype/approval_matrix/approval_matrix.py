# Copyright (c) 2026, 8848 Digital and contributors
# For license information, please see license.txt

from collections import defaultdict
from decimal import Decimal

import frappe
from frappe import _
from frappe.model.document import Document

from approval_engine.generator import (
    MAX_LEVELS, configured_levels, setup_workflow, on_matrix_cancel,
    resolve_amount_field,
)


class ApprovalMatrix(Document):
    def validate(self):
        self._validate_unique_active()
        self._validate_departments_company()
        self._validate_rows()
        self._validate_bands()

    def on_submit(self):
        # Guard here (not in validate) so a WIP draft can still be saved while the amount-field
        # mapping is being sorted out; the client shows a live hint meanwhile. Hard-block at
        # submit, since submit bakes the amount field into the generated conditions.
        self._validate_amount_field()
        setup_workflow(self.document_type)

    def on_cancel(self):
        on_matrix_cancel(self.document_type)

    # ------------------------------------------------------------------
    # validations
    # ------------------------------------------------------------------

    def _validate_amount_field(self):
        """The amount field the bands compare against is resolved from Approval Settings (or a
        default) and baked into every generated condition. Catch a missing/misconfigured field
        here, before submit, instead of silently generating a broken workflow condition."""
        info = resolve_amount_field(self.document_type)
        if not info.get("exists"):
            frappe.throw(_(
                "Amount field <b>{0}</b> is not a valid amount field on {1}. Set the correct "
                "field for {1} in <b>Approval Settings</b> before submitting this matrix — the "
                "bands compare document amounts against it."
            ).format(info.get("amount_field"), self.document_type))

    def _validate_unique_active(self):
        dupe = frappe.db.exists("Approval Matrix", {
            "document_type": self.document_type,
            "company": self.company,
            "docstatus": 1,
            "name": ("!=", self.name),
        })
        if dupe:
            frappe.throw(_("An active Approval Matrix ({0}) already exists for {1} / {2}.")
                         .format(dupe, self.document_type, self.company))

    def _validate_departments_company(self):
        """Every row's Department must belong to this matrix's Company. The generated workflow
        conditions pair `doc.company == <company>` with `doc.department == <department>`, so a
        cross-company department yields a condition no real document can satisfy — and the
        runtime band check (runtime.py) would reject the document at save. Block it here."""
        for row in self.detail:
            if not row.department:
                continue
            dept_company = frappe.db.get_value("Department", row.department, "company")
            if dept_company and dept_company != self.company:
                frappe.throw(_("Row #{0}: Department {1} belongs to {2}, not {3}. "
                               "Pick a department that belongs to {3}.")
                             .format(row.idx, row.department, dept_company, self.company))

    def _validate_rows(self):
        for row in self.detail:
            levels = configured_levels(row)
            if 1 not in levels:
                frappe.throw(_("Row #{0} ({1}): Approver 1 must have at least one user.")
                             .format(row.idx, row.department))
            # contiguous tiers: e.g. Approver 3 requires Approver 1 & 2
            if levels != list(range(1, max(levels) + 1)):
                frappe.throw(_("Row #{0} ({1}): approver tiers must be filled in order "
                               "(you can only fill Approver {2} if 1..{3} are filled).")
                             .format(row.idx, row.department, max(levels), max(levels) - 1))

    def _validate_bands(self):
        """Per department, bands must start at 0, be contiguous & non-overlapping,
        with exactly one unbounded (Max = 0) top band."""
        by_dept = defaultdict(list)
        for row in self.detail:
            by_dept[row.department].append(row)

        # Smallest representable step for this currency field (e.g. 2 decimals -> 0.01).
        # Decimal (not float) so band boundaries never drift from rounding error.
        precision = frappe.get_precision("Approval Matrix Detail", "min_amount") or 2
        step = Decimal(1).scaleb(-precision)

        for dept, rows in by_dept.items():
            bands = sorted(
                [(Decimal(str(r.min_amount or 0)), Decimal(str(r.max_amount or 0)), r) for r in rows],
                key=lambda x: (x[0], x[1] if x[1] else Decimal("Infinity")),
            )
            # Bands are inclusive [Min, Max]; each band starts at the previous band's
            # Max + the smallest currency unit (e.g. Max=100000 -> next Min=100000.01) so no
            # boundary value is shared between rows.
            expected_min = Decimal(0)
            for i, (mn, mx, r) in enumerate(bands):
                is_last = i == len(bands) - 1
                if mn != expected_min:
                    frappe.throw(_("Department {0}: amount bands must be contiguous with no "
                                   "gaps/overlaps. Expected the next band to start at {1} "
                                   "(previous Max + {2}), found {3}.")
                                 .format(dept, expected_min, step, mn))
                if is_last:
                    if mx != 0:
                        frappe.throw(_("Department {0}: the highest band must have Max Amount = 0 "
                                       "(unbounded) to cover all amounts.").format(dept))
                else:
                    if mx == 0:
                        frappe.throw(_("Department {0}: only the highest band may have "
                                       "Max Amount = 0.").format(dept))
                    if mx < mn:
                        frappe.throw(_("Department {0}: Max Amount ({1}) must be greater than or "
                                       "equal to Min Amount ({2}).").format(dept, mx, mn))
                    expected_min = mx + step
