from .doc_events import manage_supplier_role_based_on_workflow, update_vendor_email_doc, update_supplier_in_brn, create_supplier_address, create_bank_accounts_for_supplier

def on_update(self, method):
	manage_supplier_role_based_on_workflow(self)
	create_bank_accounts_for_supplier(self)

def before_insert(self, method):
	update_vendor_email_doc(self)

def after_insert(self, method):
	update_supplier_in_brn(self)
	# create_supplier_address(self)