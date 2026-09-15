import frappe

from frappe import _

def msa_agreement_validation(self, method):
    if self.party_type == "Supplier" and self.party:
        msa_agreement = frappe.db.get_value(
            "Supplier",
            self.party,
            "custom_msa_agreement"
        )

        if msa_agreement == "No":
            frappe.throw(_("If MSA is not attached, payment will be blocked."))
        elif not msa_agreement:
            frappe.throw(_("MSA Agreement Is Mandatory Select Yes/No"))