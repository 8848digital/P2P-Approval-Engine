# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
app_name = "approval_engine"
app_title = "Approval Engine"
app_publisher = "8848 Digital"
app_description = "Config-driven P2P approval workflow engine (Approval Matrix -> auto Workflow)"
app_email = "dhaval@8848digital.com"
app_license = "Proprietary"

# Exported by `bench --site <site> 8848-export-fixtures --app approval_engine`
# (see commands/README.md); imported into fixtures/ on migrate.
custom_fixtures = [{"dt": "Custom Field", "filters": {"module": "Settlement"}}]

commands = ["approval_engine.commands.export_fixtures.export_fixtures"]

# Apps
# ------------------

# settlement customizes Purchase Order / Purchase Invoice / Supplier /
# Supplier Quotation, all owned by erpnext.
required_apps = ["erpnext"]

# jfs_report_customization owns the "JFS Settings" Single doctype that
# settlement/kyc_validation and several settlement modules read via
# frappe.get_single("JFS Settings") -- not vendored into this app.
# Commented out for now to avoid a migration failure on sites without
# jfs_report_customization installed; code paths that touch
# "JFS Settings" will still fail at runtime until it's available and
# this is added back to required_apps above.
# required_apps.append("jfs_report_customization")

# Includes
# ------------------

# include js, css files in header of desk.html
app_include_css = [
	"workflow_activity.bundle.css",
	"/assets/approval_engine/css/kyc_validation.css",
]
app_include_js = [
	"workflow_activity.bundle.js",
	"vendor_mail.bundle.js",
]

# include js in doctype views
doctype_js = {
	"Purchase Order": "settlement/customization/purchase_order/purchase_order.js",
	"Purchase Invoice": "settlement/customization/purchase_invoice/purchase_invoice.js",
	"Supplier": [
		"settlement/customization/supplier/supplier.js",
		"settlement/customization/supplier/supplier_kyc.js",
	],
	"Supplier Quotation": "settlement/customization/supplier_quotation/supplier_quotation.js",
}
doctype_list_js = {
	"Supplier": "settlement/customization/supplier/supplier_list.js",
	"Supplier Quotation": "settlement/customization/supplier_quotation/supplier_quotation_list.js",
	"Purchase Invoice": "settlement/customization/purchase_invoice/purchase_invoice_list.js",
}

# Install / Migrate / Boot
# ------------------

after_install = "approval_engine.install.after_install"

after_migrate = [
	"approval_engine.settlement.setup.create_custom_fields",
]

boot_session = "approval_engine.boot_session.boot_session"

# Permissions
# -----------
# Permissions evaluated in scripted ways

permission_query_conditions = {
	"FAQ Master": "approval_engine.settlement.permissions.get_permission_query_conditions",
}

has_permission = {
	"FAQ Master": "approval_engine.settlement.permissions.has_permission",
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"*": {
		"validate": "approval_engine.approval_core.runtime.target_validate",
		"on_update": "approval_engine.approval_core.runtime.target_on_update",
	},
	"Payment Request": {
		"before_validate": "approval_engine.settlement.customization.payment_request.payment_request.before_validate",
	},
	"Purchase Order": {
		"validate": "approval_engine.settlement.customization.purchase_order.purchase_order.validate",
		"before_save": "approval_engine.settlement.customization.purchase_order.purchase_order.before_save",
	},
	"Purchase Invoice": {
		"before_validate": "approval_engine.settlement.customization.purchase_invoice.purchase_invoice.before_validate",
		"validate": "approval_engine.settlement.customization.purchase_invoice.purchase_invoice.validate",
		"after_insert": "approval_engine.settlement.customization.purchase_invoice.purchase_invoice.after_insert",
		"on_update": "approval_engine.settlement.customization.purchase_invoice.purchase_invoice.on_update",
		"on_submit": "approval_engine.settlement.customization.purchase_invoice.purchase_invoice.on_submit",
		"on_cancel": "approval_engine.settlement.customization.purchase_invoice.purchase_invoice.on_cancel",
	},
	"Supplier": {
		"validate": "approval_engine.settlement.customization.supplier.supplier.validate",
		"on_update": "approval_engine.settlement.customization.supplier.supplier.on_update",
		"before_insert": "approval_engine.settlement.customization.supplier.supplier.before_insert",
		"after_insert": "approval_engine.settlement.customization.supplier.supplier.after_insert",
	},
	"Supplier Quotation": {
		"on_update_after_submit": "approval_engine.settlement.customization.supplier_quotation.supplier_quotation.on_update_after_submit",
	},
	"Payment Entry": {
		"before_submit": "approval_engine.settlement.customization.payment_entry.payment_entry.before_submit",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"cron": {
		"0 9 * * *": [
			"approval_engine.settlement.tasks.send_vendor_onboarding_reminders",
		],
	},
	"daily": [
		"approval_engine.approval_core.tasks.expire_action_links",
		"approval_engine.settlement.tasks.reverse_prior_year_itc",
	],
}

# Request Events
# ----------------

# Rewrites every /api/method/approval_engine* response into the standard
# 8848 response envelope {status, status_code, message, data, errors}.
after_request = [
	"approval_engine.utils.api_handlers.response_formatter.format_frappe_response_to_custom"
]

# Website / Vendor Portal
# ------------------

update_website_context = [
	"approval_engine.settlement.vendor_auth_hooks.update_website_context",
]

on_login = "approval_engine.settlement.vendor_auth_hooks.block_vendor_from_standard_login"

website_route_rules = [
	{"from_route": "/brn", "to_route": "BRN"},
	{
		"from_route": "/brn/<path:name>",
		"to_route": "brn",
		"defaults": {
			"doctype": "BRN",
			"parents": [{"label": "Approved Proposals", "route": "brn"}],
		},
	},
]

standard_portal_menu_items = [
	{"title": "Approved Proposals", "route": "/brn", "reference_doctype": "BRN", "role": "Supplier"},
]

website_path_resolver = "approval_engine.website.resolve_website_path"

website_context = {
	"post_login": [
		{"label": "My Account", "url": "/me"},
		{
			"label": "Log out",
			"url": "/api/method/approval_engine.settlement.api.v1.vendor_portal.vendor_web_logout",
		},
	]
}
