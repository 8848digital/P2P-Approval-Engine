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

# Apps
# ------------------

# settlement customizes Purchase Order / Purchase Invoice / Supplier /
# Supplier Quotation, all owned by erpnext.
required_apps = ["erpnext"]

# jfs_report_customization owns the "JFS Settings" Single doctype that
# settlement/kyc_validation and several doc_events read via
# frappe.get_single("JFS Settings") -- not vendored into this app.
# Commented out for now to avoid a migration failure on sites without
# jfs_report_customization installed; code paths that touch
# "JFS Settings" will still fail at runtime until it's available and
# this is added back to required_apps above.
# required_apps.append("jfs_report_customization")

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "approval_engine",
# 		"logo": "/assets/approval_engine/logo.png",
# 		"title": "Approval Engine",
# 		"route": "/approval_engine",
# 		"has_permission": "approval_engine.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = [
	"workflow_activity.bundle.css",
	"/assets/approval_engine/css/kyc_validation.css",
]
app_include_js = "workflow_activity.bundle.js"

# include js, css files in header of web template
# web_include_css = "/assets/approval_engine/css/approval_engine.css"
# web_include_js = "/assets/approval_engine/js/approval_engine.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "approval_engine/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"Purchase Order": "settlement/customization/purchase_order/purchase_order.js",
	"Purchase Invoice": "settlement/customization/purchase_invoice/purchase_invoice.js",
	"Supplier": [
		"settlement/customization/supplier/supplier.js",
		"settlement/public/js/supplier_kyc.js",
	],
	"Supplier Quotation": "settlement/customization/supplier_quotation/supplier_quotation.js",
	"BRN": "settlement/public/js/vendor_mail.js",
}
doctype_list_js = {
	"Supplier": [
		"settlement/customization/supplier/supplier_list.js",
		"settlement/public/js/vendor_mail.js",
	],
	"Supplier Quotation": "settlement/customization/supplier_quotation/supplier_quotation_list.js",
	"Purchase Invoice": "settlement/customization/purchase_invoice/purchase_invoice_list.js",
}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "approval_engine/public/icons.svg"

after_migrate = [
	"approval_engine.settlement.setup.create_custom_fields",
]

extend_bootinfo = "approval_engine.settlement.boot.boot_session"

update_website_context = [
	"approval_engine.settlement.vendor_auth_hooks.update_website_context",
]

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "approval_engine.utils.jinja_methods",
# 	"filters": "approval_engine.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "approval_engine.install.before_install"
after_install = "approval_engine.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "approval_engine.uninstall.before_uninstall"
# after_uninstall = "approval_engine.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "approval_engine.utils.before_app_install"
# after_app_install = "approval_engine.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "approval_engine.utils.before_app_uninstall"
# after_app_uninstall = "approval_engine.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "approval_engine.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "approval_engine.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["approval_engine.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

permission_query_conditions = {
	"FAQ Master": "approval_engine.settlement.permissions.faq_master.get_permission_query_conditions",
}

has_permission = {
	"FAQ Master": "approval_engine.settlement.permissions.faq_master.has_permission",
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"*": {
		"validate": "approval_engine.approval_core.runtime.target_validate",
	},
	"Payment Request": {
		"before_validate": "approval_engine.settlement.doc_events.payment_request.msa_agreement_validation",
	},
	"Purchase Order": {
		"validate": "approval_engine.settlement.customization.purchase_order.purchase_order.validate",
		"before_save": "approval_engine.settlement.customization.purchase_order.purchase_order.before_save",
	},
	"Purchase Invoice": {
		"before_validate": [
			"approval_engine.settlement.tax_withholding.force_apply_tds_for_locked_allowance_rows",
		],
		"on_update": [
			"approval_engine.settlement.doc_events.purchase_invoice_itc_reversal.set_itc_status",
		],
		"validate": [
			"approval_engine.settlement.tax_withholding.apply_supplier_allowance_limit",
			"approval_engine.settlement.tax_withholding.apply_return_tds_reversal",
			"approval_engine.settlement.customization.purchase_invoice.purchase_invoice.validate",
		],
		"after_insert": [
			"approval_engine.settlement.doc_events.purchase_invoice_itc_reversal.set_itc_status",
		],
		"on_submit": [
			"approval_engine.settlement.tax_withholding.update_supplier_allowance_consumed",
			"approval_engine.settlement.doc_events.validate_po_status.on_purchase_invoice_submit",
			"approval_engine.settlement.doc_events.purchase_invoice_itc_reversal.handle_itc_reversal_on_submit",
		],
		"on_cancel": [
			"approval_engine.settlement.tax_withholding.cancel_supplier_allowance_consumed",
		],
	},
	"FAQ Master": {
		"validate": "approval_engine.settlement.doc_events.faq_master.validate",
		"after_insert": "approval_engine.settlement.doc_events.faq_master.sync_supplier_custom_field",
		"on_update": "approval_engine.settlement.doc_events.faq_master.sync_supplier_custom_field",
		"on_trash": "approval_engine.settlement.doc_events.faq_master.delete_supplier_custom_field",
	},
	"Supplier": {
		"validate": [
			"approval_engine.settlement.doc_events.supplier.validate_vendor_onboarding",
			"approval_engine.settlement.doc_events.supplier.update_brn_msa_agreement",
			"approval_engine.settlement.doc_events.supplier.sync_company_to_supplier",
		],
		"on_update": "approval_engine.settlement.customization.supplier.supplier.on_update",
		"before_insert": "approval_engine.settlement.customization.supplier.supplier.before_insert",
		"after_insert": "approval_engine.settlement.customization.supplier.supplier.after_insert",
	},
	"Supplier Quotation": {
		"on_update_after_submit": "approval_engine.settlement.customization.supplier_quotation.supplier_quotation.on_update_after_submit",
	},
	"Payment Entry": {
		"before_submit": "approval_engine.settlement.doc_events.payment_entry.block_payment_without_msa_attachment",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"cron": {
		"0 9 * * *": [
			"approval_engine.settlement.doctype.vendor_email.utils.send_reminder_for_non_registered_vendors",
		],
	},
	"daily": [
		"approval_engine.settlement.doc_events.purchase_invoice_itc_reversal.run_daily_itc_reversal_sweep",
	],
}

# Testing
# -------

# before_tests = "approval_engine.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "approval_engine.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "approval_engine.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "approval_engine.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["approval_engine.utils.before_request"]

# Rewrites every /api/method/approval_engine* response into the standard
# 8848 response envelope {status, status_code, message, data, errors}.
after_request = [
	"approval_engine.utils.api_handlers.response_formatter.format_frappe_response_to_custom"
]

# Job Events
# ----------
# before_job = ["approval_engine.utils.before_job"]
# after_job = ["approval_engine.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"approval_engine.auth.validate"
# ]

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

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
