<!--
Copyright (c) 2026 8848 Digital LLP. All rights reserved.
Proprietary and confidential. Unauthorized copying, distribution, or use
of this file, via any medium, is strictly prohibited without prior
written permission from 8848 Digital LLP.
-->

# SETUP.md

The Approval Engine has no external integrations of its own, but it sends
email (approval links and one-time codes), so it needs a working **outgoing
Email Account** and a correct **site URL**. It also requires one piece of
in-app configuration before the engine can process documents: the **Approval
Settings** Single DocType.

Required before go-live:

| # | What | Why |
| - | ---- | --- |
| 1 | [Approval Settings](#approval-settings) — amount field mapping | The engine cannot band amounts without it |
| 2 | [Outgoing Email Account](#email-approvals-act-from-email-without-signing-in) | Approval links and OTPs cannot be sent |
| 3 | [`host_name` in site config](#site-config--environment-variables) | Emailed links would point at an unreachable URL |
| 4 | [A business role per approver](#approver-roles-manual-step) | Approvers cannot save the document they approve |
| 5 | Background worker + scheduler running | Approval emails are queued and flushed by them |

## Approval Settings

### Overview

Before an Approval Matrix can be submitted for a DocType, the engine needs to
know which field on that DocType holds the amount its bands compare against.
This mapping lives in the **Approval Settings** Single DocType. Without a
mapping the engine falls back to a per-DocType default (`grand_total` for
Purchase Order / Purchase Invoice, `paid_amount` for Payment Entry, else
`grand_total`); configure it explicitly for any other target DocType.

### Settings DocType Fields

Configure at **Approval Settings** (single, one per site):

| Field | Type | Mandatory | Notes |
| ----- | ---- | --------- | ----- |
| Amount Field Mapping | Table (Approval Amount Field Mapping) | No¹ | One row per target DocType. |
| Email Link Validity (Hours) | Int | No | How long an emailed approval link stays usable, 1–720. Blank is stored as the default **72**. A link also dies as soon as it is used or the document moves state. |

Each **Amount Field Mapping** row:

| Field | Type | Mandatory | Notes |
| ----- | ---- | --------- | ----- |
| DocType | Link (DocType) | Yes | The target DocType governed by an Approval Matrix. |
| Amount Fieldname | Data | Yes | Fieldname (not label) of the Currency/Float/Int field to band on, e.g. `grand_total`. Must exist on the DocType. |

¹ Optional only because of the built-in defaults above. A row **is** required
for any target DocType whose amount field is not one of those defaults —
submitting an Approval Matrix hard-blocks if the resolved amount field does
not exist on the DocType.

### Site Config / Environment Variables

| Key | Where | Required? | Notes |
| --- | ----- | --------- | ----- |
| `host_name` | `site_config.json` | **Yes**, when email approvals are used | Absolute public URL of the site, e.g. `https://erp.example.com`. Emailed links are built from it (`frappe.utils.get_url`). Without it Frappe falls back to the site name (`http://<site>:<port>`), which recipients cannot open. It also makes PDF rendering hang, because the renderer fetches the print's assets from that URL. |

```bash
bench --site <site> set-config host_name https://erp.example.com
```

### How to Test

1. Open **Approval Settings** and add a row mapping a target DocType (e.g.
   `Purchase Order`) to its amount field (e.g. `grand_total`).
2. Create and submit an **Approval Matrix** for that DocType and a company,
   with at least one amount band and an Approver 1 user.
3. Open a document of that DocType — the generated `<DocType> Approval`
   workflow should be active and the "Workflow Activity" sidebar should
   render on the form.


## Email approvals (act from email without signing in)

### Overview

When a tier has **Action via Email** ticked on its Approval Matrix row, each
approver of that tier is emailed a personal, single-use link plus the document
PDF. The link opens a public page where they approve, hold or reject after
confirming a one-time code sent separately to their own mailbox. No ERP login
is involved. See `README.md` for the flow.

### Required Credentials

| Credential | Where it's stored | Required? |
| ---------- | ----------------- | --------- |
| Outgoing SMTP account | **Email Account** DocType, with **Enable Outgoing** and **Default Outgoing** ticked | Yes |

Use a dedicated no-reply mailbox (e.g. `erp-noreply@example.com`), not a
personal one. Gmail/Google Workspace accounts need 2-Step Verification and an
**App Password** (`smtp.gmail.com`, port 587, TLS); Microsoft 365 mailboxes
need Authenticated SMTP enabled, or the account's **Method** set to OAuth.

Without a default outgoing account, approval emails and OTPs fail with
"Please setup default outgoing Email Account from Tools > Email Account".

### Background processes

| Process | Needed for |
| ------- | ---------- |
| Background worker (`bench worker`) | Runs the job that issues links and queues approval emails |
| Scheduler (`bench schedule`) | Flushes the Email Queue (every ~4 min by default) and expires old links daily |
| Redis queue | Carries the job from the web request to the worker |

OTP emails are sent synchronously in the web request, so they do not depend on
the worker or scheduler.

### Approver roles (manual step)

The engine grants each approver `<DocType> - Approver N`, which carries
read/write/submit on the governed DocType plus read on Department and Company.
That is **not enough on its own**: approving saves the document, and ERPNext
re-validates it as the approving user, reading linked master data.

Give every approver a normal business role for the DocType they approve:

| Approves | Role to assign manually |
| -------- | ----------------------- |
| Purchase Order | Purchase User (or Purchase Manager) |
| Purchase Invoice / Payment Entry | Accounts User (or Accounts Manager) |

Without it, the approver sees "Your ERP account is missing access to
&lt;DocType&gt;, which is needed to complete this approval" on the email page,
and the equivalent permission error in Desk.

### Email templates

`approval_engine/templates/emails/approval_action_request.html` and
`approval_action_otp.html` are plain placeholder layouts — restyle them to the
client's branding without changing the Jinja variables they use.

### How to Test

1. Tick **Approver 1 Action via Email** on an Approval Matrix row and submit
   the matrix.
2. Create a document matching that row (company, department, amount band). The
   approver should receive "Approval required: …" with the PDF attached,
   usually within a few minutes (Email Queue flush interval).
3. Open the link in a private window: the page must render without a login.
4. Request a verification code, enter it, and confirm the action.
5. Check the document: the new state, the remarks in the Workflow Activity
   sidebar and timeline, and a **Document Workflow Log** row with **Via Email
   Link** ticked.
6. Reopen the same link — it must report that it has already been used.

If nothing arrives, check **Email Queue** (row status and error), **Error Log**
(failed jobs) and **Approval Action Token** (whether links were issued at all).
