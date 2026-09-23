<!--
Copyright (c) 2026 8848 Digital LLP. All rights reserved.
Proprietary and confidential. Unauthorized copying, distribution, or use
of this file, via any medium, is strictly prohibited without prior
written permission from 8848 Digital LLP.
-->

# Vendor Portal

## Purpose
Owns the vendor-facing self-service portal: what shows up in it (Vendor
Portal Settings), how each section is configured (Portal Section Config),
and the shared access/context helpers (`utils.py`) that the portal's page
controllers and includes build on.

## DocTypes

| DocType | Purpose |
| ------- | ------- |
| Vendor Portal Settings | Single. The portal's configuration root -- portal title and the ordered list of Document Type sections (via its `doctypes` child table). Seeded with sane defaults on first visit by `seed_default_settings()`. |
| Portal Section Config | Child table row (on Vendor Portal Settings) describing one portal section: target DocType, route, label/icon, required Role, which fields drive title/status/amount/date display, docstatus filter, optional Tab Group, and optional linked-document config. |

## Portal Pages & API

This module has no `api/` package: it currently exposes no
`@frappe.whitelist()` endpoints of its own (the one whitelisted call the
portal UI makes, password change, lives in
`approval_engine.settlement.api.v1.vendor_portal.vendor_update_password`
and is out of this module's scope). Everything below is called directly from Python, not
over `frappe.call`.

`utils.py` is the single source of truth every portal entry point reads
through:
- `require_vendor_login()` / `require_vendor_portal_access()` -- access
  guards, gating every page below.
- `get_portal_doctypes()` / `get_visible_portal_doctypes()` /
  `get_portal_doctype_by_route()` / `get_portal_doctype_by_document_type()`
  -- read Vendor Portal Settings' configured, role-filtered sections.
- `get_portal_nav_items()` / `get_tab_siblings()` -- sidebar/tab-bar
  structure derived from those sections.
- `base_portal_context()` -- the common context (nav, brand, active item)
  every page below mixes into its own context.

Per Frappe convention, page controllers themselves live under the app's
`www/` directory (not inside this module folder) and Jinja includes shared
across them live under `templates/includes/vendor_portal/`:

| File | Route | What it does |
| ---- | ----- | ------------- |
| `www/vendor_login.py` | `/vendor-login` | Login entry point; redirects an already-authenticated vendor to their landing route, or renders the login form. |
| `www/vendor_portal.py` | `/vendor-portal` | Dashboard: seeds default settings on first visit, shows a count tile per visible section. |
| `www/vendor_portal_list.py` | `/vendor-portal-list` | Filterable/searchable/sortable list page for one section (or one tab within a Tab Group). |
| `www/vendor_portal_detail.py` | `/vendor-portal-detail` | Single-document detail view: key/value fields, child-table items, linked documents, optional invoice-attach uploader. |
| `www/vendor_profile.py` | `/vendor-profile` | The vendor's own Supplier record, read-only. |
| `www/vendor_account.py` | `/vendor-account` | Account settings (password change) for the logged-in vendor. |
| `www/vendor_embed.py` | `/vendor-embed` | Iframes a whitelisted, role-gated Web Form (e.g. onboarding) inside the portal shell. |
| `templates/includes/vendor_portal/nav.html`, `.../style.html` | -- | Shared sidebar/nav and styling include, rendered by every page above via `base_portal_context()`. |
