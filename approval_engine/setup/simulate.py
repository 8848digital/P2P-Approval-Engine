"""Transition simulator — verify workflow correctness WITHOUT creating real documents.

For a hypothetical document (company, department, amount, state) it asks the real
ERPNext engine which actions each user may take (role + condition: pool, band,
department, no-repeat).

    bench --site v16.dev execute approval_engine.setup.simulate.run
    bench --site v16.dev execute approval_engine.setup.simulate.run --kwargs '{"document_type":"Purchase Order"}'
"""

import frappe
from frappe.model.workflow import get_workflow, get_workflow_safe_globals

from approval_engine.generator import amount_field_for, pool, configured_levels

CHECK_STATES = [
    "Pending", "Approved 1", "Approved 2", "Approved 3",
    "On Hold by Approver 1", "On Hold by Approver 2",
]


def available(document_type, company, department, amount, state, user, amount_field):
    wf = get_workflow(document_type)
    doc = frappe._dict({
        "doctype": document_type, "name": "SIM-DOC",
        "company": company, "department": department,
        amount_field: amount, "workflow_state": state,
    })
    prev = frappe.session.user
    frappe.set_user(user)
    try:
        roles = set(frappe.get_roles(user))
        actions = []
        for t in wf.transitions:
            if t.state != state or t.allowed not in roles:
                continue
            if t.condition:
                try:
                    if not frappe.safe_eval(t.condition, get_workflow_safe_globals(), {"doc": doc}):
                        continue
                except Exception:
                    continue
            actions.append(f"{t.action} -> {t.next_state}")
        return actions
    finally:
        frappe.set_user(prev)


def simulate(document_type, company, department, amount, users, amount_field=None):
    af = amount_field or amount_field_for(document_type)
    print(f"\n==== {document_type} | company={company} | dept={department} | {af}={amount} ====")
    for state in CHECK_STATES:
        print(f"  -- {state} --")
        for u in users:
            acts = available(document_type, company, department, amount, state, u, af)
            print(f"     {u:22} {acts if acts else '(no actions)'}")


def run(document_type="Purchase Order"):
    name = frappe.db.get_value(
        "Approval Matrix", {"document_type": document_type, "docstatus": 1}, "name")
    if not name:
        print(f"No submitted Approval Matrix for {document_type}")
        return
    m = frappe.get_doc("Approval Matrix", name)
    af = amount_field_for(document_type)

    # every user referenced anywhere in the matrix (so we can see who is blocked)
    all_users = set()
    for row in m.detail:
        for level in configured_levels(row):
            all_users |= set(pool(row, level))
    users = sorted(all_users)

    print(f"Matrix {m.name} | company {m.company} | amount field '{af}'")
    print("Rows:")
    for row in m.detail:
        cfg = {L: pool(row, L) for L in configured_levels(row)}
        print(f"  dept={row.department} band=({row.min_amount or 0},{row.max_amount or 0}) tiers={cfg}")

    # simulate each row at a representative in-band amount
    for row in m.detail:
        mn = row.min_amount or 0
        mx = row.max_amount or 0
        amount = (mn + mx) / 2 if mx else mn + 10000
        simulate(document_type, m.company, row.department, amount, users, af)

    # bonus: out-of-band amount for the first bounded row -> expect no actions
    first = m.detail[0]
    if first.max_amount:
        simulate(document_type, m.company, first.department, (first.max_amount or 0) + 999999,
                 users, af)
