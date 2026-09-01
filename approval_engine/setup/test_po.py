"""DEV / TEST ONLY — do NOT run against a production site.

Comprehensive Purchase Order workflow integration check against the current active
Approval Matrix. It CREATES real data (test Supplier, Item, Purchase Orders) and
grants business roles to the matrix's approver users, then drives POs through every
path reporting PASS/FAIL. It does not modify the Approval Matrix itself.

This is a manual integration harness (run on a dev site), complementary to the
isolated unit tests in doctype/approval_matrix/test_approval_matrix.py. Converting
this into a fully-isolated Frappe integration test is a Milestone-3 item (the
workflow generation has global + DDL side-effects that don't cleanly roll back).

    bench --site v16.dev execute approval_engine.setup.test_po.run
"""

import frappe
from frappe.model.workflow import apply_workflow, get_transitions

from approval_engine.generator import configured_levels, pool

COMPANY = "8848Digital"
DT = "Purchase Order"
BUSINESS_ROLES = ["Purchase Manager", "Purchase User", "Stock Manager", "Stock User",
                  "Accounts Manager", "Accounts User", "Item Manager"]

results = []


# ---------------- helpers ----------------

def _ensure_supporting_masters():
    if not frappe.db.exists("Supplier", "AE Test Supplier"):
        sg = frappe.get_all("Supplier Group", filters={"is_group": 0}, pluck="name")[0]
        frappe.get_doc({"doctype": "Supplier", "supplier_name": "AE Test Supplier",
                        "supplier_group": sg}).insert(ignore_permissions=True)
    if not frappe.db.exists("Item", "AE-TEST-ITEM"):
        ig = frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name")[0]
        frappe.get_doc({"doctype": "Item", "item_code": "AE-TEST-ITEM", "item_name": "AE Test Item",
                        "item_group": ig, "stock_uom": "Nos", "is_stock_item": 0,
                        "is_purchase_item": 1}).insert(ignore_permissions=True)


def _grant_business_roles():
    roles = [r for r in BUSINESS_ROLES if frappe.db.exists("Role", r)]
    m = frappe.get_doc("Approval Matrix", frappe.db.get_value(
        "Approval Matrix", {"document_type": DT, "docstatus": 1}, "name"))
    users = set()
    for row in m.detail:
        for L in configured_levels(row):
            users.update(pool(row, L))
    for u in users:
        if u not in ("Administrator", "Guest") and frappe.db.exists("User", u):
            frappe.get_doc("User", u).add_roles(*roles)
    frappe.db.commit()


def _new_po(amount, department):
    po = frappe.get_doc({
        "doctype": "Purchase Order", "company": COMPANY, "supplier": "AE Test Supplier",
        "department": department, "schedule_date": frappe.utils.nowdate(),
        "transaction_date": frappe.utils.nowdate(),
        "items": [{"item_code": "AE-TEST-ITEM", "qty": 1, "rate": amount,
                   "schedule_date": frappe.utils.nowdate()}],
    })
    po.insert(ignore_permissions=True)
    frappe.db.commit()
    return po.name


def _state(name):
    return frappe.db.get_value("Purchase Order", name, ["workflow_state", "docstatus"], as_dict=True)


def _act(name, user, action):
    frappe.set_user(user)
    try:
        apply_workflow(frappe.get_doc("Purchase Order", name), action)
        frappe.db.commit()
    finally:
        frappe.set_user("Administrator")


def _actions(name, user):
    frappe.set_user(user)
    try:
        return sorted({t.get("action") for t in get_transitions(frappe.get_doc("Purchase Order", name))})
    finally:
        frappe.set_user("Administrator")


def _check(label, ok, detail=""):
    results.append((label, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  ({detail})" if detail else ""))


# ---------------- scenarios ----------------

def scenario_full_cycle():
    print("\n# A. Full approval cycle (Purchase - 8, 50000: tiers b/c -> cfo/a/b -> d)")
    po = _new_po(50000, "Purchase - 8")
    _check("created -> Pending", _state(po).workflow_state == "Pending")
    _act(po, "b@example.com", "Approve")
    _check("tier1 b -> Approved 1", _state(po).workflow_state == "Approved 1")
    _act(po, "a@example.com", "Approve")
    _check("tier2 a -> Approved 2", _state(po).workflow_state == "Approved 2")
    _act(po, "d@example.com", "Approve")
    s = _state(po)
    _check("tier3 d -> Approved (submitted)", s.workflow_state == "Approved" and s.docstatus == 1,
           f"state={s.workflow_state} docstatus={s.docstatus}")


def scenario_hold_resume():
    print("\n# B. Hold then resume (Purchase - 8, 50000)")
    po = _new_po(50000, "Purchase - 8")
    _act(po, "b@example.com", "Hold")
    _check("tier1 b Hold -> On Hold by Approver 1", _state(po).workflow_state == "On Hold by Approver 1")
    _act(po, "b@example.com", "Approve")
    _check("resume: b Approve -> Approved 1", _state(po).workflow_state == "Approved 1")


def scenario_reject():
    print("\n# C. Reject (Purchase - 8, 50000)")
    po = _new_po(50000, "Purchase - 8")
    _act(po, "c@example.com", "Reject")
    s = _state(po)
    _check("tier1 c Reject -> Rejected (submitted)", s.workflow_state == "Rejected" and s.docstatus == 1,
           f"state={s.workflow_state} docstatus={s.docstatus}")


def scenario_single_tier_finalize():
    print("\n# D. Single-tier band finalize (Purchase - 8, 150000: tier1 Administrator only)")
    po = _new_po(150000, "Purchase - 8")
    _check("created -> Pending", _state(po).workflow_state == "Pending")
    _act(po, "Administrator", "Approve")
    s = _state(po)
    _check("tier1 Approve -> Approved directly (no tier 2)",
           s.workflow_state == "Approved" and s.docstatus == 1,
           f"state={s.workflow_state} docstatus={s.docstatus}")


def scenario_second_department():
    print("\n# E. Second department full cycle (Operations - 8, 50000: tiers 1,2)")
    po = _new_po(50000, "Operations - 8")
    _act(po, "atul.test@example.com", "Approve")
    _check("tier1 atul -> Approved 1", _state(po).workflow_state == "Approved 1")
    _act(po, "c@example.com", "Approve")
    s = _state(po)
    _check("tier2 c -> Approved (finalize, no tier 3)",
           s.workflow_state == "Approved" and s.docstatus == 1,
           f"state={s.workflow_state} docstatus={s.docstatus}")


def scenario_band_routing():
    print("\n# F. Band routing by amount (Purchase - 8)")
    lo = _new_po(50000, "Purchase - 8")     # band (0,100000]  -> tier1 b/c, hold+reject allowed
    hi = _new_po(150000, "Purchase - 8")    # band (100000,inf) -> single tier1, no hold/reject
    b_lo = _actions(lo, "b@example.com")
    b_hi = _actions(hi, "b@example.com")
    # amount picks a different band -> different available actions (band-2 tier1 has no hold/reject)
    _check("50000 -> band 1 (Approve/Hold/Reject offered)", b_lo == ["Approve", "Hold", "Reject"], f"actions={b_lo}")
    _check("150000 -> band 2 (only Approve offered; band-2 tier1 has no hold/reject)",
           b_hi == ["Approve"], f"actions={b_hi}")
    # single-tier band-2 finalizes straight to Approved
    _act(hi, "b@example.com", "Approve")
    s = _state(hi)
    _check("150000 Approve -> Approved directly (single-tier band)",
           s.workflow_state == "Approved" and s.docstatus == 1, f"state={s.workflow_state}")
    print("    note: b (not a band-2 configured user) could act here = accepted role-only gating (pool removed per client)")


def scenario_block():
    print("\n# G. Block when no band matches (Dispatch - 8)")
    try:
        _new_po(5000, "Dispatch - 8")
        _check("unconfigured department blocked", False, "was NOT blocked!")
    except Exception as e:
        _check("unconfigured department blocked", "No approval matrix band" in str(e), str(e)[:60])
    frappe.db.rollback()


def run():
    frappe.set_user("Administrator")
    _ensure_supporting_masters()
    _grant_business_roles()

    scenario_full_cycle()
    scenario_hold_resume()
    scenario_reject()
    scenario_single_tier_finalize()
    scenario_second_department()
    scenario_band_routing()
    scenario_block()

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n==== SUMMARY: {passed}/{len(results)} checks passed ====")
    for label, ok, detail in results:
        if not ok:
            print(f"   FAILED: {label} ({detail})")
