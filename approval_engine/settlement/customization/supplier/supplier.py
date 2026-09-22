# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

from .doc_events import (
	create_bank_accounts_for_supplier,
	create_supplier_address,
	manage_supplier_role_based_on_workflow,
	update_supplier_in_brn,
	update_vendor_email_doc,
)


def on_update(self, method):
	manage_supplier_role_based_on_workflow(self)
	create_bank_accounts_for_supplier(self)


def before_insert(self, method):
	update_vendor_email_doc(self)


def after_insert(self, method):
	update_supplier_in_brn(self)
	# create_supplier_address(self)
