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
runtime gating/audit of governed documents, and the Finance Overview
dashboard.

## DocTypes

| DocType | Purpose |
| ------- | ------- |
| Approval Matrix | Submittable per (company, document type) configuration of amount bands and per-tier approver pools; drives workflow generation. |
| Approval Matrix Detail | Child row of Approval Matrix — one amount band with its Approver 1–4 user pools. |
| Approval Amount Field Mapping | Child row of Approval Settings — maps a DocType to the amount field its bands compare against. |
| Approval Settings | Single DocType holding the DocType → amount-field mappings. See root `SETUP.md`. |
| Document Workflow Log | Full audit trail of every workflow state transition (who moved which document from which state to which, and when). |

## Pages

- **Finance Overview** (`finance-dashboard`) — per-DocType pending / on-hold / approved value for the logged-in user, scoped to a company.

## Dashboards

- `dashboard/finance_dashboard.py` — aggregation data provider backing the Finance Overview page (pending, on-hold, and approved summaries per target DocType).

## API

Whitelisted endpoints (versioned under `api/v1/`):

- `api/v1/dashboard.py` — Finance Overview summaries (pending / on-hold / approved / combined).
- `api/v1/activity.py` — managed DocTypes + per-document workflow-activity reconstruction for the form sidebar.
- `api/v1/workflow.py` — amount-field resolution for the Approval Matrix form.

## Runtime

- `runtime.py` — `validate` hook (registered for all DocTypes via `doc_events["*"]`); blocks saves with no matching matrix band and records every state change into Document Workflow Log.
- `generator.py` — builds/rebuilds the ERPNext Workflow from submitted Approval Matrix records.
- `activity.py` — reconstructs the approver chain for a single document (backs `api/v1/activity.py`).
