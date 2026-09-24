<!--
Copyright (c) 2026 8848 Digital LLP. All rights reserved.
Proprietary and confidential. Unauthorized copying, distribution, or use
of this file, via any medium, is strictly prohibited without prior
written permission from 8848 Digital LLP.
-->

# Approval Core

## Purpose

Owns the entire config-driven approval engine: the Approval Matrix
configuration, the generation of standard ERPNext Workflows from it, the
runtime gating/audit of governed documents, approving from email without
signing in, and the Finance Overview dashboard. This is the app's single
module.

## DocTypes

| DocType | Purpose |
| ------- | ------- |
| Approval Matrix | Submittable per (company, document type) configuration of amount bands and per-tier approver pools; drives workflow generation. |
| Approval Matrix Detail | Child row of Approval Matrix — one amount band with its Approver 1–4 user pools. |
| Approval Amount Field Mapping | Child row of Approval Settings — maps a DocType to the amount field its bands compare against. |
| Approval Settings | Single DocType holding the DocType → amount-field mappings. See root `SETUP.md`. |
| Document Workflow Log | Full audit trail of every workflow state transition — who moved which document from which state to which, when, their remarks, and whether the action came from an email link. |
| Approval Action Token | One emailed approval link: the approver it was issued to, the state it was issued for, its status (Active / Used / Superseded / Expired) and how it was used. Stores only hashes of the link token and OTP. |
| Additional Approver | One ad-hoc approver injected into a single document's live chain by an eligible approver, at the current juncture, without touching the shared matrix. Carries the target reference, the approver, the captured `insert_state`, per-record `can_hold`/`can_reject`/`action_via_email` flags, and `active`/`completed` lifecycle flags. |

## Portal Pages

- **`/approval_action`** (`www/approval_action.*`, app root) — public,
  login-free page an emailed approval link opens: document summary, the actions
  that approver may take, remarks, and OTP confirmation.

## Pages

- **Finance Overview** (`finance-dashboard`) — per-DocType pending / on-hold / approved value for the logged-in user, scoped to a company.

## Dashboards

- `dashboard/finance_dashboard.py` — aggregation data provider backing the Finance Overview page (pending, on-hold, and approved summaries per target DocType).

## API

Whitelisted endpoints (versioned under `api/v1/`):

- `api/v1/dashboard.py` — Finance Overview summaries (pending / on-hold / approved / combined).
- `api/v1/activity.py` — managed DocTypes + per-document workflow-activity reconstruction for the form sidebar.
- `api/v1/workflow.py` — amount-field resolution for the Approval Matrix form, and the remarks stash used by the Desk workflow-action dialog.
- `api/v1/email_action.py` — guest (`allow_guest`) endpoints behind the approval page: request an OTP, submit an action. POST-only and rate limited.
- `api/v1/additional_approver.py` — inject an ad-hoc additional approver into one document (`add`), and resolve whether the current user may do so right now (`can_add`, drives the form button).

## Runtime

- `runtime.py` — `validate` and `on_update` hooks (registered for all DocTypes via `doc_events["*"]`); blocks saves with no matching matrix band, records every state change into Document Workflow Log with its remarks, retires open email links and queues the next actor's emails, and keeps the active Additional Approver record in step (marks it completed on entering `Additionally Approved`, retires it once the chain moves past the review).
- `generator.py` — builds/rebuilds the ERPNext Workflow from submitted Approval Matrix records, including the generic `Additionally Approved` states/transitions that route a document through an ad-hoc reviewer when one is inserted.
- `doctype/additional_approver/` — the ad-hoc reviewer's data model, eligibility/one-at-a-time rules, per-record role grant/revoke, and reviewer notification.
- `activity.py` — reconstructs the approver chain for a single document (backs `api/v1/activity.py`).
- `remarks.py` — approver remarks attached to a transition; enforces the mandatory rejection reason for every channel.
- `tasks.py` — background/scheduled jobs: send approval-link emails after a state change, expire old links daily.
- `email_action/` — the email-link flow: issuing and validating links (`action_link.py`), one-time codes (`otp.py`), emailing the approvers who must act next (`notify.py`), and what the guest page may do (`link_actions.py`). See root `SETUP.md` for what must be configured.

## Email Templates

- `templates/emails/approval_action_request.html` — the approval request with the personal link (placeholder layout).
- `templates/emails/approval_action_otp.html` — the one-time code (placeholder layout).
