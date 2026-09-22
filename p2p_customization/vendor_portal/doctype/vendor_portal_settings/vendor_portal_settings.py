import frappe
from frappe.model.document import Document


class VendorPortalSettings(Document):
	"""
	Single doctype configuring the vendor-facing portal: which DocTypes
	appear as sections, their labels/icons/routes, and per-section display
	and permission rules. `vendor_portal.utils` reads this document (via
	`frappe.get_cached_doc`) to build the portal's nav, filters, and pages.

	Carries no custom validation of its own; each row's shape is defined
	by the Portal Section Config child doctype.
	"""

	pass


DEFAULT_DOCTYPES = [
	{
		"document_type": "Purchase Order",
		"label": "Purchase Orders",
		"route": "purchase-orders",
		"icon": "shopping-cart",
		"party_fieldname": "supplier",
		"status_field": "status",
		"amount_field": "grand_total",
		"currency_field": "currency",
		"date_field": "transaction_date",
		"child_table_fieldname": "items",
		# Not meaningful (and not real Portal-User-linked data) until the
		# vendor has actually been onboarded -- manage_supplier_role_based_on_workflow
		# (p2p_customization/settlement/customization/supplier/doc_events.py)
		# grants this role automatically the moment their Supplier record
		# is created from the onboarding form.
		"role": "Supplier",
		"idx_order": 1,
		# Merged with Purchase Invoice into one "Orders & Invoices" sidebar
		# item, shown as tabs on one list page -- this row is first
		# (idx_order 1), so its own route is the default tab and it's the
		# one carrying the group's sidebar label/icon.
		"tab_group": "orders_invoices",
		"tab_group_label": "Orders & Invoices",
		"tab_group_icon": "shopping-cart",
		# Lets a vendor upload their invoice against an order that isn't
		# fully billed yet, straight from the order's own detail page.
		"allow_invoice_attach": 1,
		"billed_percent_fieldname": "per_billed",
		# Shows which Purchase Invoices were actually raised against this
		# order -- the link lives on the invoice's own line items
		# (Purchase Invoice Item.purchase_order), not the invoice itself.
		"linked_document_type": "Purchase Invoice",
		"linked_via_child_doctype": "Purchase Invoice Item",
		"linked_via_fieldname": "purchase_order",
	},
	{
		"document_type": "Purchase Invoice",
		"label": "Purchase Invoices",
		"route": "purchase-invoices",
		"icon": "receipt-indian-rupee",
		"party_fieldname": "supplier",
		"status_field": "status",
		"amount_field": "grand_total",
		"currency_field": "currency",
		"date_field": "posting_date",
		"tab_group": "orders_invoices",
		"child_table_fieldname": "items",
		"role": "Supplier",
		"idx_order": 2,
		# Unlike Purchase Order, a vendor should see every stage of their
		# own invoices -- draft, submitted, and cancelled -- not just
		# submitted ones.
		"docstatus_filter": "All (Draft, Submitted, Cancelled)",
	},
	{
		"document_type": "Supplier",
		"label": "My Profile",
		"route": "supplier-profile",
		"icon": "building-2",
		"party_fieldname": "name",
		"title_field": "supplier_name",
		"status_field": None,
		"edit_web_form": "vendor-onboarding-form",
		"show_in_nav": 0,
		# "Vendor Portal" (not "Supplier") -- every vendor account gets this
		# role the moment it's created (create_website_user), well before
		# their Supplier record exists, so this stays reachable for a
		# brand-new vendor still filling in onboarding.
		"role": "Vendor Portal",
		"idx_order": 3,
	},
]


def seed_default_settings() -> None:
	"""
	Idempotent: only runs the first time, if no Document Types are
	configured yet -- lets the portal work out of the box, while any admin
	edit to Vendor Portal Settings afterwards is left alone.

	Parameters:
		None.

	Returns:
		None
	"""
	settings = frappe.get_single("Vendor Portal Settings")
	if settings.doctypes:
		return

	for row in DEFAULT_DOCTYPES:
		settings.append("doctypes", row)
	settings.save(ignore_permissions=True)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit - defensive: seeded defaults survive even if a later step in this same request/hook call fails
