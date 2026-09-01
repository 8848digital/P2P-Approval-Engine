# Approval Engine — Documentation

Config-driven P2P approval engine for ERPNext v16. An **Approval Matrix** record (per
DocType + Company, with per-department **amount bands** and approver tiers) is submitted,
and the system **auto-generates / updates a standard ERPNext Workflow** (states, roles,
transitions, conditions) for that DocType and reconciles role→user assignments. Uses
**literal transitions** (company/department/band/approver-pool/no-repeat baked into each
transition), evaluated live by ERPNext — no snapshot.

## Documents

| Doc | Contents |
|-----|----------|
| [HANDOFF.md](HANDOFF.md) | **Read first** — status, how to run, design summary, what's pending |
| [SPEC.md](SPEC.md) | Context, glossary, data model |
| [DECISIONS.md](DECISIONS.md) | Every requirement question and its answer |
| [WORKFLOW_DESIGN.md](WORKFLOW_DESIGN.md) | State machine, transition conditions, runtime lifecycle, generation engine |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | Phased build plan + current status |
| [VERIFICATION.md](VERIFICATION.md) | End-to-end test plan |

## Target DocTypes
BRN (custom), Purchase Order, Purchase Invoice, Payment Entry — the engine stays generic
and is not hardcoded to these.

## Dev environment
- Bench: `/Users/dg/frappe-bench-v16` (frappe 16.x, erpnext 16.x, Node 24, Python 3.14)
- Site: `v16.dev` — `cd /Users/dg/frappe-bench-v16 && nvm use 24 && bench start` → http://v16.dev:8000
