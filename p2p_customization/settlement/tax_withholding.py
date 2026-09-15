import frappe
from frappe.utils import flt
from erpnext.accounts.doctype.tax_withholding_entry.tax_withholding_entry import PurchaseTaxWithholding



def apply_tax_withholding(doc, method=None):
	"""
	In version-16 TDS was removed from Purchase Order entirely. Rather
	than re-implement it, this reuses core's own Purchase Invoice TDS
	engine (PurchaseTaxWithholding) as-is -- same line-item-wise category
	grouping, thresholds, and Lower Deduction Certificate handling PI
	gets. Purchase Order is missing a handful of fields that engine
	reads directly off doc (it was only ever written against Purchase
	Invoice), so those are filled in here before handing off.

	No GL entries are posted from this -- Purchase Order has no
	make_gl_entries at all, so that side of PurchaseTaxWithholding
	(which only runs from Purchase Invoice's on_submit/make_gl_entries)
	never gets reached.

	Note: this DOES write real Tax Withholding Entry rows into the same
	cross-document threshold ledger Purchase Invoice uses. A submitted
	PO and the Purchase Invoice later raised against it will each
	contribute their own entries for what is really one transaction,
	so cumulative threshold tracking will double-count that amount
	until/unless the PO's entries are reconciled when the PI is made.
	"""
	doc.posting_date = doc.transaction_date
	doc.tax_withholding_group = doc.get("tax_withholding_group")
	doc.override_tax_withholding_entries = doc.get("override_tax_withholding_entries") or 0
	doc.ignore_tax_withholding_threshold = doc.get("ignore_tax_withholding_threshold") or 0
	doc.advances = doc.get("advances") or []

	PurchaseTaxWithholding(doc).on_validate()


def _get_pi_tds_category_map(self):
    category_taxable_map = {}
    for item in self.get("items") or []:
        if not item.get("tax_withholding_category"):
            continue
        if not (item.get("custom_tds_within_allowance") or item.get("apply_tds")):
            continue
        category = item.tax_withholding_category
        category_taxable_map[category] = category_taxable_map.get(category, 0) + flt(item.amount)
    return category_taxable_map


def _get_supplier_allowance_settings(supplier, for_update=False):
    return frappe.db.get_value(
        "Supplier",
        supplier,
        ["set_allowance_limit_for_tds", "allowance_limit", "consumed_amount"],
        as_dict=True,
        for_update=for_update,
    )


def _tds_account_by_category(company, categories):
    """Company's configured Tax Withholding Account per category - only
    categories with a real account are ones the allowance-limit/reversal
    logic actually acts on, so callers use this set to decide what counts."""
    result = {}
    for category in categories:
        if category in result:
            continue
        account = frappe.db.get_value(
            "Tax Withholding Account", {"parent": category, "company": company}, "account"
        )
        if account:
            result[category] = account
    return result


def force_apply_tds_for_locked_allowance_rows(self, method=None):
    for item in self.get("items") or []:
        if item.get("custom_tds_within_allowance") and item.get("tax_withholding_category"):
            item.apply_tds = 1


def apply_supplier_allowance_limit(self, method=None):
    if not self.supplier or not self.get("items") or not self.get("taxes"):
        return

    if self.get("is_return"):
        return

    settings = _get_supplier_allowance_settings(self.supplier)
    if not settings or not settings.set_allowance_limit_for_tds:
        return

    _apply_supplier_allowance_limit_impl(self, settings)


def _apply_supplier_allowance_limit_impl(self, settings):
    items_with_category = [i for i in self.items if i.get("apply_tds") and i.get("tax_withholding_category")]
    if not items_with_category:
        return

    category_rates = {
        entry.tax_withholding_category: flt(entry.tax_rate)
        for entry in self.get("tax_withholding_entries") or []
    }

    tds_account_by_category = _tds_account_by_category(
        self.company, {i.tax_withholding_category for i in items_with_category}
    )

    tds_accounts = set(tds_account_by_category.values())
    if not tds_accounts:
        return

    remaining_allowance = max(flt(settings.allowance_limit) - flt(settings.consumed_amount), 0)

    # Sequential per-item exempt/taxable split.
    running_total = 0
    item_taxable = {}
    category_taxable = {}
    for item in items_with_category:
        item_amount = flt(item.amount)
        cumulative_before = running_total
        running_total += item_amount
        if running_total <= remaining_allowance:
            taxable = 0
        elif cumulative_before >= remaining_allowance:
            taxable = item_amount
        else:
            taxable = running_total - remaining_allowance
        item_taxable[item.name] = taxable
        category = item.tax_withholding_category
        category_taxable[category] = category_taxable.get(category, 0) + taxable

    account_amounts = {}
    for category, taxable_amount in category_taxable.items():
        account = tds_account_by_category.get(category)
        if not account:
            continue
        rate = category_rates.get(category, 0)
        account_amounts[account] = account_amounts.get(account, 0) + flt(taxable_amount) * rate / 100

    remaining_taxes = []
    kept_tax_by_account = {}
    changed = False
    for tax in self.taxes:
        if tax.account_head not in tds_accounts:
            remaining_taxes.append(tax)
            continue
        changed = True
        new_amount = flt(account_amounts.get(tax.account_head, 0), tax.precision("tax_amount"))
        if new_amount:
            tax.tax_amount = new_amount
            tax.dont_recompute_tax = 1
            kept_tax_by_account[tax.account_head] = tax
            remaining_taxes.append(tax)
        # else: fully within the remaining allowance - drop the row entirely.

    if not changed:
        return

    self.set("taxes", remaining_taxes)
    self._item_wise_tax_details = [
        d for d in (self.get("_item_wise_tax_details") or [])
        if not (d.get("tax") and d["tax"].get("account_head") in tds_accounts)
    ]
    for item in items_with_category:
        taxable = item_taxable.get(item.name, 0)
        if not taxable:
            continue
        tax_row = kept_tax_by_account.get(tds_account_by_category.get(item.tax_withholding_category))
        if not tax_row:
            continue
        rate = category_rates.get(item.tax_withholding_category, 0)
        multiplier = -1 if tax_row.get("add_deduct_tax") == "Deduct" else 1
        self._item_wise_tax_details.append(
            frappe._dict(
                item=item,
                tax=tax_row,
                rate=rate,
                amount=flt(flt(taxable) * rate / 100 * multiplier, tax_row.precision("tax_amount")),
                taxable_amount=flt(taxable, tax_row.precision("tax_amount")),
            )
        )

    remaining_entries = []
    for entry in self.get("tax_withholding_entries") or []:
        if entry.tax_withholding_category not in category_taxable:
            remaining_entries.append(entry)
            continue
        taxable_amount = category_taxable[entry.tax_withholding_category]
        new_withholding = flt(
            flt(taxable_amount) * flt(entry.tax_rate) / 100, entry.precision("withholding_amount")
        )
        if new_withholding:
            entry.taxable_amount = flt(taxable_amount, entry.precision("taxable_amount"))
            entry.withholding_amount = new_withholding
            remaining_entries.append(entry)
        # else: fully within the remaining allowance - drop the ledger entry too.
    self.set("tax_withholding_entries", remaining_entries)

    self.calculate_taxes_and_totals()

    for item in items_with_category:
        taxable = item_taxable.get(item.name, 0)
        item.custom_allowance_exempt_amount = flt(item.amount) - flt(taxable)
        # server is authoritative here, not just a fallback for whatever the
        # client-side lock predicted - a row fully within the allowance gets
        # unchecked and locked read-only regardless of what apply_tds/
        # custom_tds_within_allowance were coming in.
        item.custom_tds_within_allowance = 0 if taxable else 1
        if item.custom_tds_within_allowance:
            item.apply_tds = 0


def _get_return_category_ratios(self, original):
    """Per tax_withholding_category, what fraction of the original
    invoice's TAXABLE amount in that category this return is reversing.

    Computed from each returned item's own original counterpart's taxable
    share (item.amount minus its stamped custom_allowance_exempt_amount),
    matched via purchase_invoice_item - not from raw item amounts. A
    category can span both fully-exempt and taxable items (the supplier
    allowance limit splits sequentially across items, not per category), so
    weighting by raw amount would misattribute TDS to a returned item that
    was never actually taxed. Also only counts items that were actually
    part of the TDS calc (custom_tds_within_allowance or apply_tds), so an
    item the user opted out of TDS entirely doesn't count as "taxable"
    merely because it was never stamped with an exempt amount.
    """
    original_items_by_name = {i.name: i for i in original.get("items") or []}

    def _taxable_share(item):
        if not (item.get("custom_tds_within_allowance") or item.get("apply_tds")):
            return None
        return flt(item.amount) - flt(item.get("custom_allowance_exempt_amount"))

    original_taxable_by_category = {}
    for item in original.get("items") or []:
        category = item.get("tax_withholding_category")
        taxable = _taxable_share(item)
        if category and taxable is not None:
            original_taxable_by_category[category] = original_taxable_by_category.get(category, 0) + taxable

    returned_taxable_by_category = {}
    for item in self.get("items") or []:
        category = item.get("tax_withholding_category")
        source = original_items_by_name.get(item.get("purchase_invoice_item"))
        if not category or not source or not source.amount:
            continue
        source_taxable = _taxable_share(source)
        if source_taxable is None:
            continue
        # signed: item.amount is negative on a return, so this naturally
        # comes out negative (reversing) and scales down for a partial
        # quantity/value return of the same row.
        item_ratio = flt(item.amount) / flt(source.amount)
        returned_taxable_by_category[category] = (
            returned_taxable_by_category.get(category, 0) + source_taxable * item_ratio
        )

    ratios = {}
    for category, returned_taxable in returned_taxable_by_category.items():
        original_taxable = original_taxable_by_category.get(category)
        if original_taxable:
            ratios[category] = returned_taxable / original_taxable
    return ratios


def apply_return_tds_reversal(self, method=None):
    """A debit note's own item amounts don't reflect whatever
    allowance-limit exemption reduced the TDS on the original invoice, so
    letting core recompute TDS independently on the return over-reverses it.
    Instead, mirror the original invoice's actual withholding, scaled by how
    much of it this return covers - the same number that would come out of
    cancelling that portion of the original."""
    if not self.get("is_return") or not self.get("return_against"):
        return
    if not self.supplier or not self.get("items") or not self.get("taxes"):
        return

    settings = _get_supplier_allowance_settings(self.supplier)
    if not settings or not settings.set_allowance_limit_for_tds:
        return

    original = frappe.get_doc("Purchase Invoice", self.return_against)
    original_entries_by_category = {
        e.tax_withholding_category: e for e in original.get("tax_withholding_entries") or []
    }
    if not original_entries_by_category:
        return

    ratios = _get_return_category_ratios(self, original)
    if not ratios:
        return

    tds_account_by_category = _tds_account_by_category(self.company, original_entries_by_category.keys())

    tds_accounts = set(tds_account_by_category.values())
    if not tds_accounts:
        return

    category_reversal = {}
    account_amounts = {}
    for category, ratio in ratios.items():
        entry = original_entries_by_category.get(category)
        account = tds_account_by_category.get(category)
        if not entry or not account:
            continue
        withholding = flt(entry.withholding_amount) * ratio
        taxable = flt(entry.taxable_amount) * ratio
        category_reversal[category] = {
            "taxable": taxable,
            "withholding": withholding,
            "rate": entry.tax_rate,
            "ldc": entry.lower_deduction_certificate,
            "reason": entry.under_withheld_reason,
        }
        account_amounts[account] = account_amounts.get(account, 0) + withholding

    if not category_reversal:
        return

    remaining_taxes = []
    kept_tax_by_account = {}
    changed = False
    for tax in self.taxes:
        if tax.account_head not in tds_accounts:
            remaining_taxes.append(tax)
            continue
        changed = True
        new_amount = flt(account_amounts.get(tax.account_head, 0), tax.precision("tax_amount"))
        if new_amount:
            tax.tax_amount = new_amount
            tax.dont_recompute_tax = 1
            kept_tax_by_account[tax.account_head] = tax
            remaining_taxes.append(tax)
        # else: nothing to reverse for this account - drop the row.

    if not changed:
        return

    self.set("taxes", remaining_taxes)
    self._item_wise_tax_details = [
        d for d in (self.get("_item_wise_tax_details") or [])
        if not (d.get("tax") and d["tax"].get("account_head") in tds_accounts)
    ]

    items_by_category = {}
    for item in self.items:
        category = item.get("tax_withholding_category")
        if category in category_reversal:
            items_by_category.setdefault(category, []).append(item)
            item.apply_tds = 1

    for category, data in category_reversal.items():
        items = items_by_category.get(category) or []
        tax_row = kept_tax_by_account.get(tds_account_by_category.get(category))
        if not tax_row or not items:
            continue
        multiplier = -1 if tax_row.get("add_deduct_tax") == "Deduct" else 1
        category_amount_total = sum(flt(i.amount) for i in items) or 1
        for item in items:
            share = flt(item.amount) / category_amount_total
            self._item_wise_tax_details.append(
                frappe._dict(
                    item=item,
                    tax=tax_row,
                    rate=data["rate"],
                    amount=flt(data["withholding"] * share * multiplier, tax_row.precision("tax_amount")),
                    taxable_amount=flt(data["taxable"] * share, tax_row.precision("tax_amount")),
                )
            )

    remaining_entries = []
    for entry in self.get("tax_withholding_entries") or []:
        if entry.tax_withholding_category not in category_reversal:
            remaining_entries.append(entry)
            continue
        data = category_reversal[entry.tax_withholding_category]
        if data["withholding"]:
            entry.taxable_amount = flt(data["taxable"], entry.precision("taxable_amount"))
            entry.withholding_amount = flt(data["withholding"], entry.precision("withholding_amount"))
            entry.lower_deduction_certificate = data["ldc"]
            entry.under_withheld_reason = data["reason"]
            remaining_entries.append(entry)
        # else: nothing to reverse - drop the ledger entry too.
    self.set("tax_withholding_entries", remaining_entries)

    self.calculate_taxes_and_totals()


def update_supplier_allowance_consumed(self, method=None):
    if not self.supplier:
        return

    # for_update: this is the write path (unlike the settings reads in
    # apply_supplier_allowance_limit/apply_return_tds_reversal, which only
    # predict the split during validate) - locks the row so two concurrent
    # submits for the same supplier can't both read the same stale
    # consumed_amount and both write forward independently past the limit.
    settings = _get_supplier_allowance_settings(self.supplier, for_update=True)
    if not settings or not settings.set_allowance_limit_for_tds:
        return

    if self.get("is_return"):
        _reverse_supplier_allowance_consumed_for_return(self, settings)
        return

    category_map = _get_pi_tds_category_map(self)
    # Only count categories that actually have a configured Tax Withholding
    # Account for this company - apply_supplier_allowance_limit bails out
    # entirely (no exemption applied, TDS left to core's own calc) when none
    # of a doc's categories have one, so consumed_amount must not advance
    # either in that case.
    valid_accounts = _tds_account_by_category(self.company, category_map.keys())
    total_amount = sum(amount for category, amount in category_map.items() if category in valid_accounts)
    if total_amount <= 0:
        return

    current = flt(settings.consumed_amount)
    limit = flt(settings.allowance_limit)
    # max(current, ...): if allowance_limit was lowered below what's already
    # consumed, this submit shouldn't claw consumed_amount back down - only
    # a cancel/return does that, via a positive stored contribution it can
    # reverse. Without this, a negative "contributed" here would make a
    # later cancel of *this* invoice incorrectly increase consumed_amount.
    new_total = max(current, min(current + total_amount, limit))
    contributed = new_total - current
    if not contributed:
        return

    frappe.db.set_value("Supplier", self.supplier, "consumed_amount", new_total)
    frappe.db.set_value("Purchase Invoice", self.name, "custom_allowance_consumed_amount", contributed)


def _reverse_supplier_allowance_consumed_for_return(self, settings):
    """Mirror of cancel_supplier_allowance_consumed, but for a debit note
    instead of an actual cancellation: give back exactly the slice of
    Supplier.consumed_amount that the returned row(s) contributed.

    Each original item's own exempt amount was stamped onto
    custom_allowance_exempt_amount by _apply_supplier_allowance_limit_impl
    at submit time, so this sums exactly the returned items' shares instead
    of approximating from the original invoice's total exempted amount -
    exact even for a return that covers only some of a multi-item, multi
    -category invoice, or a partial quantity/value return of one row."""
    if not self.get("return_against") or not self.get("items"):
        return

    original_items = {
        i.name: i
        for i in frappe.get_all(
            "Purchase Invoice Item",
            filters={"parent": self.return_against},
            fields=["name", "amount", "custom_allowance_exempt_amount"],
        )
    }
    if not original_items:
        return

    reversal = 0
    for item in self.items:
        source = original_items.get(item.get("purchase_invoice_item"))
        if not source or not source.amount or not source.custom_allowance_exempt_amount:
            continue
        ratio = abs(flt(item.amount)) / flt(source.amount)
        reversal += flt(source.custom_allowance_exempt_amount) * ratio

    if not reversal:
        return

    current = flt(settings.consumed_amount)
    new_total = max(current - reversal, 0)
    frappe.db.set_value("Supplier", self.supplier, "consumed_amount", new_total)
    frappe.db.set_value("Purchase Invoice", self.name, "custom_allowance_consumed_amount", -reversal)


def cancel_supplier_allowance_consumed(self, method=None):
    if not self.supplier:
        return

    contributed = flt(self.get("custom_allowance_consumed_amount"))
    if not contributed:
        return

    current = flt(frappe.db.get_value("Supplier", self.supplier, "consumed_amount"))
    new_total = max(current - contributed, 0)
    frappe.db.set_value("Supplier", self.supplier, "consumed_amount", new_total)


def update_tds_rate_for_po(self, method=None):
    rcm=frappe.get_doc("RCM Setting")
    if self.company not in [i.get('company') for i in rcm.rcm_company]:
        if self.get("tax_withholding_category"):
            get_tds_account = frappe.db.get_value("Tax Withholding Account", {
                                                "parent": self.tax_withholding_category, "company": self.company}, "account")
            tax_amount=0
            if self.items:
                for item in self.items:
                    if item.get("apply_tds"):
                        tax_amount+=item.amount

            if get_tds_account:
                if self.taxes:
                    for tax in self.taxes:
                        if tax.account_head == get_tds_account:
                            tds_rate = (float(tax.tax_amount) / float(tax_amount))*100
                            tax.tds_rate = tds_rate
    else:
        if self.get("tax_withholding_category"):
            # Fetch the existing TDS account
            get_tds_account = frappe.db.get_value(
                "Tax Withholding Account",
                {"parent": self.tax_withholding_category, "company": self.company},
                "account"
            )
            tax_amount=0
            if self.items:
                for item in self.items:
                    if item.get("apply_tds"):
                        tax_amount+=item.amount
            # Calculate the tax amount for items where TDS is applied
            # tax_amount = sum(item.amount for item in self.items if item.apply_tds) if self.items else 0

            # Set TDS rate if the tax account exists
            # if self.taxes and tax_amount > 0:
            #     for tax in self.taxes:
            #         if tax.account_head == get_tds_account:
            #             tax.tds_rate = (float(tax.tax_amount) / float(tax_amount)) * 100
            if get_tds_account:
                if self.taxes:
                    for tax in self.taxes:
                        if tax.account_head == get_tds_account:
                            tds_rate = (float(tax.tax_amount) / float(tax_amount))*100
                            tax.tds_rate = tds_rate

def update_tds_rate(self, method=None):

    if not self.items or not self.taxes:
        return

    rcm = frappe.get_doc("RCM Setting")
    rcm_companies = [i.company for i in rcm.rcm_company]

    if self.company in rcm_companies:
        return

    #  Build category-wise taxable map
    category_taxable_map = {}

    for item in self.items:
        if item.apply_tds and item.tax_withholding_category:
            category = item.tax_withholding_category
            category_taxable_map.setdefault(category, 0)
            category_taxable_map[category] += item.amount or 0

    for category, tax_amount in category_taxable_map.items():

        tds_account = frappe.db.get_value(
            "Tax Withholding Account",
            {
                "parent": category,
                "company": self.company
            },
            "account"
        )

        if not tds_account:
            continue

        for tax in self.taxes:
            if tax.account_head == tds_account:
                tax.tds_rate = (tax.tax_amount / tax_amount * 100) if tax_amount else ""
