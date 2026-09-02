"""Workflow generation engine (LITERAL model).

For a target DocType, (re)build ONE standard ERPNext Workflow from all submitted
Approval Matrix records. Transitions are generated PER (company, department, band,
tier, action) with company/department/amount-band/approver-pool/no-repeat conditions
written literally into each transition. Escalate-vs-finalize is baked in at
generation time (we know which tiers are configured per row).

Roles (`<DocType> - Approver N`) are a coarse gate; the exact per-row approver pool
is embedded in each condition so only that department/band's approvers can act.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

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

# ---------------------------------------------------------------------------
# naming helpers
# ---------------------------------------------------------------------------

def role_name(document_type, level):
    return f"{document_type} - Approver {level}"


def workflow_name(document_type):
    return f"{document_type} Approval"


# ---------------------------------------------------------------------------
# row helpers
# ---------------------------------------------------------------------------

def pool(row, level):
    return [row.get(f"approver_{level}_user_{u}")
            for u in range(1, 6) if row.get(f"approver_{level}_user_{u}")]


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
    explicit = next((r.amount_field for r in settings.amount_fields
                     if r.document_type == document_type), None)
    amount_field = explicit or DEFAULT_AMOUNT_FIELDS.get(document_type, "grand_total")

    df = frappe.get_meta(document_type).get_field(amount_field) if document_type else None
    exists = bool(df and df.fieldtype in AMOUNT_FIELDTYPES)
    return {
        "amount_field": amount_field,
        "is_explicit": bool(explicit),
        "exists": exists,
        "label": (df.label if df else None) or amount_field,
    }


@frappe.whitelist()
def get_amount_field_info(document_type):
    """API for the Approval Matrix form: which amount field its bands will use, and whether it's
    an explicit Approval Settings mapping or a fallback default."""
    if not document_type:
        return {}
    return resolve_amount_field(document_type)


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


# ---------------------------------------------------------------------------
# ensure masters
# ---------------------------------------------------------------------------

def ensure_roles(document_type):
    for level in range(1, MAX_LEVELS + 1):
        name = role_name(document_type, level)
        if not frappe.db.exists("Role", name):
            frappe.get_doc({"doctype": "Role", "role_name": name, "desk_access": 1}).insert(
                ignore_permissions=True)


def ensure_role_permissions(document_type):
    """Grant read/write/submit on the target DocType to each approver role,
    so approvers can open and act on the document."""
    from frappe.permissions import add_permission, update_permission_property
    for level in range(1, MAX_LEVELS + 1):
        role = role_name(document_type, level)
        has_perm = frappe.db.exists(
            "Custom DocPerm", {"parent": document_type, "role": role, "permlevel": 0}
        )
        if not has_perm:
            add_permission(document_type, role, 0)
        for ptype in ("read", "write", "submit"):
            update_permission_property(document_type, role, 0, ptype, 1)


def _grant_read_to_flow_roles(target_doctype, document_type):
    """Grant read on `target_doctype` to every role that touches `document_type`'s flow: its
    approver roles, and any role that can already create the target document. A real,
    admin-visible/editable Custom DocPerm (shows up in Role Permission Manager like any other
    permission) -- deliberately NOT a permission bypass at the query/API layer, so the admin
    stays in control of it exactly like any other grant in the system.
    """
    from frappe.permissions import add_permission, update_permission_property

    roles = {role_name(document_type, level) for level in range(1, MAX_LEVELS + 1)}
    for perm_dt in ("DocPerm", "Custom DocPerm"):
        roles.update(frappe.get_all(
            perm_dt, filters={"parent": document_type, "create": 1, "permlevel": 0},
            pluck="role"))

    for role in roles:
        already = frappe.db.exists("Custom DocPerm",
                                   {"parent": target_doctype, "role": role, "permlevel": 0}) \
            or frappe.db.exists("DocPerm",
                                {"parent": target_doctype, "role": role, "permlevel": 0})
        if not already:
            add_permission(target_doctype, role, 0)
        update_permission_property(target_doctype, role, 0, "read", 1)


def ensure_department_read(document_type):
    """Grant read on `Department` to everyone who touches the flow.

    `Department` is HR-restricted by default. Since the engine adds a `department`
    field to the target DocType and requires it for routing, the document's
    creators (roles that can create the target) and the approver roles must be able
    to read Department, or saving/opening the document raises
    'Insufficient Permission for Department'. (Department names aren't sensitive;
    this grants READ only.)
    """
    _grant_read_to_flow_roles("Department", document_type)


def ensure_company_read(document_type):
    """Grant read on `Company` to everyone who touches the flow.

    `Company` is ERPNext-restricted to specific business roles (Accounts User, Employee,
    etc.) by default, but an approver needs to see company names regardless of their
    business-role footprint -- e.g. the Finance dashboard's company selector, which any
    approver should be able to use. Same reasoning as ensure_department_read. (Company
    name/abbr/tax_id aren't sensitive; this grants READ only.)
    """
    _grant_read_to_flow_roles("Company", document_type)


def ensure_actions():
    for action in ACTIONS:
        if not frappe.db.exists("Workflow Action Master", action):
            frappe.get_doc({
                "doctype": "Workflow Action Master",
                "workflow_action_name": action,
            }).insert(ignore_permissions=True)


def ensure_workflow_states():
    for name in STATE_ORDER:
        if not frappe.db.exists("Workflow State", name):
            frappe.get_doc({
                "doctype": "Workflow State",
                "workflow_state_name": name,
                "style": WORKFLOW_STATE_STYLES.get(name, ""),
            }).insert(ignore_permissions=True)


def ensure_amount_field(document_type):
    settings = frappe.get_single("Approval Settings")
    if not any(r.document_type == document_type for r in settings.amount_fields):
        settings.append("amount_fields", {
            "document_type": document_type,
            "amount_field": DEFAULT_AMOUNT_FIELDS.get(document_type, "grand_total"),
        })
        settings.save(ignore_permissions=True)


LEGACY_HISTORY_FIELDS = ("ae_section", "custom_workflow_history")


def remove_legacy_history_field(document_type):
    """Drop the old per-DocType `custom_workflow_history` child-table field, if present.

    History now lives centrally in `Document Workflow Log` (reference_doctype/reference_name)
    instead of a Table field added to every target DocType — no per-DocType schema needed.
    """
    for fieldname in LEGACY_HISTORY_FIELDS:
        name = f"{document_type}-{fieldname}"
        if frappe.db.exists("Custom Field", name):
            frappe.delete_doc("Custom Field", name, ignore_permissions=True)


def ensure_department_field(document_type):
    """Ensure the target DocType has a `department` field (routing needs it)."""
    if frappe.get_meta(document_type).get_field("department"):
        return
    create_custom_fields({document_type: [
        {"fieldname": "department", "fieldtype": "Link", "label": "Department",
         "options": "Department", "insert_after": "company"},
    ]}, ignore_validate=True)


def find_band_row(document_type, company, department, amount):
    """Return the matching Approval Matrix Detail row for (company, dept, amount), or None."""
    name = frappe.db.get_value(
        "Approval Matrix",
        {"document_type": document_type, "company": company, "docstatus": 1}, "name")
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


# ---------------------------------------------------------------------------
# transitions (literal, per row)
# ---------------------------------------------------------------------------

def _t(state, action, next_state, allowed, condition):
    return {
        "state": state,
        "action": action,
        "next_state": next_state,
        "allowed": allowed,
        "condition": condition,
        "allow_self_approval": 1,
    }


def build_transitions(document_type):
    amt = amount_field_for(document_type)
    transitions = []

    matrices = frappe.get_all(
        "Approval Matrix",
        filters={"document_type": document_type, "docstatus": 1},
        pluck="name",
    )
    for mname in matrices:
        m = frappe.get_doc("Approval Matrix", mname)
        for row in m.detail:
            levels = configured_levels(row)
            if not levels:
                continue
            band = band_condition(amt, row.min_amount, row.max_amount)
            gate = f"doc.company == {m.company!r} and doc.department == {row.department!r}"
            if band:
                gate = f"{gate} and {band}"

            for level in levels:
                role = role_name(document_type, level)
                # Condition = company + department + amount band + this row's tier pool.
                # The Role is still the coarse gate, but the embedded pool clause pins
                # eligibility to the specific approvers configured for THIS row/tier, so a
                # same-tier approver from another row/department can no longer act here
                # even though they hold the shared `<DocType> - Approver N` role.
                base = f"{gate} and frappe.session.user in {pool(row, level)!r}"
                src = STATE_FOR_TIER[level]
                can_hold = row.get(f"approver_{level}_can_hold")
                can_reject = row.get(f"approver_{level}_can_reject")
                hold_state = f"On Hold by Approver {level}"

                # --- Approve: escalate vs finalize decided at RUNTIME by reading the
                # matrix row live (is the NEXT approver tier configured?). Both
                # transitions are emitted; the condition selects which one fires. ---
                if level < MAX_LEVELS:
                    # readable-filter form: identify the matrix row by
                    # matrix + department + band (matches the client's Excel intent)
                    next_configured = (
                        "frappe.db.get_value('Approval Matrix Detail', "
                        f"{{'parent': {m.name!r}, 'department': {row.department!r}, "
                        f"'min_amount': {row.min_amount or 0}, 'max_amount': {row.max_amount or 0}}}, "
                        f"'approver_{level + 1}_user_1')"
                    )
                    esc_cond = f"{base} and {next_configured}"          # next tier exists -> escalate
                    fin_cond = f"{base} and not {next_configured}"      # next tier blank  -> finalize
                    transitions.append(_t(src, "Approve", f"Approved {level}", role, esc_cond))
                    transitions.append(_t(src, "Approve", "Approved", role, fin_cond))
                    if can_hold:
                        transitions.append(_t(hold_state, "Approve", f"Approved {level}", role, esc_cond))
                        transitions.append(_t(hold_state, "Approve", "Approved", role, fin_cond))
                else:
                    # top tier (4): no next approver -> always finalize
                    transitions.append(_t(src, "Approve", "Approved", role, base))
                    if can_hold:
                        transitions.append(_t(hold_state, "Approve", "Approved", role, base))

                # --- Hold / Reject (company + dept + band + pool + no-repeat) ---
                if can_hold:
                    transitions.append(_t(src, "Hold", hold_state, role, base))
                    if can_reject:
                        transitions.append(_t(hold_state, "Reject", "Rejected", role, base))
                if can_reject:
                    transitions.append(_t(src, "Reject", "Rejected", role, base))

    return transitions


def _allow_edit(document_type, state):
    v = ALLOW_EDIT[state]
    return "All" if v == "All" else role_name(document_type, v)


def build_workflow(document_type):
    existing = frappe.db.get_value("Workflow", {"document_type": document_type}, "name")
    if existing:
        wf = frappe.get_doc("Workflow", existing)
        wf.states = []
        wf.transitions = []
    else:
        wf = frappe.new_doc("Workflow")
        wf.workflow_name = workflow_name(document_type)

    wf.document_type = document_type
    wf.is_active = 1
    wf.workflow_state_field = "workflow_state"
    wf.send_email_alert = 0
    wf.override_status = 0

    for state in STATE_ORDER:
        wf.append("states", {
            "state": state,
            "doc_status": STATE_DOCSTATUS[state],
            "allow_edit": _allow_edit(document_type, state),
        })
    for tr in build_transitions(document_type):
        wf.append("transitions", tr)

    wf.save(ignore_permissions=True)
    return wf.name


# ---------------------------------------------------------------------------
# role <-> user reconciliation
# ---------------------------------------------------------------------------

def reconcile_roles(document_type):
    matrices = frappe.get_all(
        "Approval Matrix",
        filters={"document_type": document_type, "docstatus": 1},
        pluck="name",
    )
    desired = {level: set() for level in range(1, MAX_LEVELS + 1)}
    for mname in matrices:
        m = frappe.get_doc("Approval Matrix", mname)
        for row in m.detail:
            for level in range(1, MAX_LEVELS + 1):
                for user in pool(row, level):
                    desired[level].add(user)

    for level in range(1, MAX_LEVELS + 1):
        role = role_name(document_type, level)
        current = set(frappe.get_all(
            "Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent"))
        for user in desired[level] - current:
            _grant_role(user, role)
        for user in current - desired[level]:
            _revoke_role(user, role)


def _grant_role(user, role):
    if user in ("Administrator", "Guest") or not frappe.db.exists("User", user):
        return
    frappe.get_doc("User", user).add_roles(role)


def _revoke_role(user, role):
    if not frappe.db.exists("User", user):
        return
    frappe.get_doc("User", user).remove_roles(role)


# ---------------------------------------------------------------------------
# public entry points
# ---------------------------------------------------------------------------

def setup_workflow(document_type):
    ensure_workflow_states()
    ensure_actions()
    ensure_roles(document_type)
    ensure_role_permissions(document_type)
    ensure_department_read(document_type)
    ensure_company_read(document_type)
    ensure_amount_field(document_type)
    remove_legacy_history_field(document_type)
    ensure_department_field(document_type)
    build_workflow(document_type)
    reconcile_roles(document_type)
    frappe.clear_cache(doctype=document_type)


def on_matrix_cancel(document_type):
    reconcile_roles(document_type)
    remaining = frappe.db.count(
        "Approval Matrix", {"document_type": document_type, "docstatus": 1})
    wf = frappe.db.get_value("Workflow", {"document_type": document_type}, "name")
    if wf:
        if remaining:
            build_workflow(document_type)  # rebuild without the cancelled matrix
        else:
            frappe.db.set_value("Workflow", wf, "is_active", 0)
    frappe.clear_cache(doctype=document_type)
