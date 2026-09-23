# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""doc_events hook wiring for Supplier. Delegates to doc_events.py and
supplier_onboarding.py for the actual logic.
"""

from .doc_events import (
	create_bank_accounts_for_supplier,
	create_supplier_address,
	manage_supplier_role_based_on_workflow,
	update_supplier_in_brn,
	update_vendor_email_doc,
)
from .supplier_onboarding import (
	sync_company_to_supplier,
	update_brn_msa_agreement,
	validate_vendor_onboarding,
)


def validate(self, method):
	"""
	Supplier validate hook: onboarding checks (FAQ answers, change log),
	MSA sync onto Supplier Quotations, and company sync -- in that order.

	Parameters:
	        self (Document, required): The Supplier being validated.
	        method (str, required): The hook event name passed by Frappe.

	Returns:
	        None
	"""
	validate_vendor_onboarding(self, method)
	update_brn_msa_agreement(self, method)
	sync_company_to_supplier(self, method)


def on_update(self, method):
	"""Supplier on_update hook: role by workflow state, bank accounts from onboarding."""
	manage_supplier_role_based_on_workflow(self)
	create_bank_accounts_for_supplier(self)


def before_insert(self, method):
	"""Supplier before_insert hook: link the onboarding Vendor Email record."""
	update_vendor_email_doc(self)


def after_insert(self, method):
	"""Supplier after_insert hook: link the new Supplier back to its BRN."""
	update_supplier_in_brn(self)
	# create_supplier_address(self)
