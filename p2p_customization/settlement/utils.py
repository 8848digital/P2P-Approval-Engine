import frappe
from frappe import _
from frappe.utils import getdate, get_link_to_form
from erpnext.accounts.utils import get_fiscal_year



def backdated_po_validation(self, method):
    # Get the current date (in date format)
    current_date = frappe.utils.getdate(frappe.utils.nowdate())
    # Get the fiscal year start and end date (convert to date format)
    fiscal_year = frappe.db.get_value("Fiscal Year", self.custom_fiscal_year, ["year_start_date", "year_end_date"], as_dict=True)
    fiscal_year_start = frappe.utils.getdate(fiscal_year['year_start_date'])
    fiscal_year_end = frappe.utils.getdate(fiscal_year['year_end_date'])
    # Convert transaction_date to date format if it's not already
    transaction_date = frappe.utils.getdate(self.transaction_date)
    # If the transaction date is not within the current fiscal year, apply stricter validation
    if not (fiscal_year_start <= transaction_date <= fiscal_year_end):
        # Calculate the difference in days between the current date and the transaction date
        days_difference = frappe.utils.date_diff(current_date, transaction_date)
        # If the transaction date is more than 7 days old, throw an error
        if days_difference > 7:
            frappe.throw("In case of change in FY, Backdate posting of Purchase Order is not allowed if the Posting Date is prior to 7 days.")
            return False  # Indicating the validation failed
    # If the transaction date is in the current fiscal year, apply the 30-day rule
    else:
        # Calculate the difference in days for the current fiscal year
        days_difference = frappe.utils.date_diff(current_date, transaction_date)
        # If the transaction date is more than 30 days old, throw an error
        if days_difference > 30:
            frappe.throw("Backdate posting of Purchase Order is not allowed if the Posting Date is prior to 30 days from today.")
            return False  # Indicating the validation failed


def _get_fiscal_year_and_validity(posting_date, brn=None):
    if not posting_date:
        frappe.throw("Posting Date is required")

    fiscal_year, fy_start, fy_end = get_fiscal_year(getdate(posting_date))

    result = {
        "fiscal_year": fiscal_year
    }

    if brn:
        service_start_date, expiry_date = frappe.db.get_value(
            "BRN", brn, ["service_start_date", "expiry_date"]
        )

        if service_start_date and expiry_date:
            service_start = getdate(service_start_date)
            service_end = getdate(expiry_date)

            # No overlap between BRN service period and fiscal year at all
            if service_end < fy_start or service_start > fy_end:
                frappe.throw(
                    f"BRN service period ({service_start} to {service_end}) "
                    f"does not fall within fiscal year {fiscal_year} "
                    f"({fy_start} to {fy_end}). Please correct the Posting Date.",
                    title="Invalid Validity Period"
                )

            # Scenario 1 & 3: validity_start_date
            if service_start < fy_start:
                validity_start_date = fy_start
            else:
                validity_start_date = service_start

            # Scenario 2 & 4: validity_end_date
            if service_end > fy_end:
                validity_end_date = fy_end
            else:
                validity_end_date = service_end

            result["validity_start_date"] = validity_start_date
            result["validity_end_date"] = validity_end_date

    return result


def validate_fiscal_year_and_brn_dates(doc, method=None):
    if not frappe.db.get_single_value("JFS Settings", "validate_brn_service_dates_in_po_pi"):
        return

    if doc.doctype == "Purchase Order":
        date = doc.transaction_date
    elif doc.doctype == "Purchase Invoice":
        date = doc.posting_date
    else:
        return

    brn_data = _get_fiscal_year_and_validity(date, doc.brn)

    if brn_data:
        doc.custom_fiscal_year = brn_data.get("fiscal_year")
        if brn_data.get("validity_start_date"):
            doc.validity_start_date = brn_data.get("validity_start_date")
            doc.validity_end_date = brn_data.get("validity_end_date")


def validate_brn_dates(brn, transaction_date):
    start_date, expiry_date = frappe.db.get_value(
        "BRN", brn, ['service_start_date', 'expiry_date']
    )

    if not (start_date and expiry_date):
        return {"status": "valid"}

    transaction_date = getdate(transaction_date)

    if transaction_date < getdate(start_date):
        return {
            "status": "before_start",
            "start_date": str(start_date),
            "expiry_date": str(expiry_date)
        }

    if transaction_date > getdate(expiry_date):
        return {
            "status": "expired",
            "start_date": str(start_date),
            "expiry_date": str(expiry_date)
        }

    return {"status": "valid"}


def validate_item_rate_and_qty_with_brn(doc, method=None):
    if not doc.brn:
        return

    brn_items = frappe.get_all(
        "BRN Item",
        filters={"parent": doc.brn},
        fields=["item_code", "qty", "rate"]
    )
    brn_map = {d.item_code: d for d in brn_items}

    brn_link = get_link_to_form("BRN", doc.brn)

    for row in doc.items:
        if row.item_code not in brn_map:
            frappe.throw(
                _("Row {0}: Item {1} is not in {2}").format(row.idx, row.item_code, brn_link),
                title=_("Invalid Item"),
            )

        brn_item = brn_map[row.item_code]

        # ---- Qty validation (skip for Service) ----
        if doc.requisition_type != "Service":
            already_ordered_qty = frappe.db.sql(
                """
                SELECT COALESCE(SUM(TPOI.qty), 0)
                FROM `tabPurchase Order Item` AS TPOI
                JOIN `tabPurchase Order` AS TPO ON TPO.name = TPOI.parent
                WHERE TPO.docstatus < 2
                    AND TPO.brn = %s
                    AND TPOI.item_code = %s
                    AND TPO.name != %s
                """,
                (doc.brn, row.item_code, doc.name),
            )[0][0]

            if already_ordered_qty + row.qty > brn_item.qty:
                frappe.throw(
                    _("Row {0}: Qty {1} exceeds BRN balance. Available BRN Qty: {2} in {3}")
                    .format(row.idx, row.qty, brn_item.qty - already_ordered_qty, brn_link),
                    title=_("Qty Exceeded"),
                )
        if doc.requisition_type != "Service":
            if row.rate != brn_item.rate:
                frappe.throw(
                    _("Row {0}: Rate {1} must match BRN Rate {2} for Item {3} in {4}")
                    .format(row.idx, row.rate, brn_item.rate, row.item_code, brn_link),
                    title=_("Rate Mismatch"),
                )

        # ---- Amount validation (always) ----
        brn_amount = brn_item.qty * brn_item.rate

        already_ordered_amount = frappe.db.sql(
            """
            SELECT COALESCE(SUM(TPOI.qty * TPOI.rate), 0)
            FROM `tabPurchase Order Item` AS TPOI
            JOIN `tabPurchase Order` AS TPO ON TPO.name = TPOI.parent
            WHERE TPO.docstatus < 2
                AND TPO.brn = %s
                AND TPOI.item_code = %s
                AND TPO.name != %s
            """,
            (doc.brn, row.item_code, doc.name),
        )[0][0]

        current_row_amount = row.qty * row.rate

        if already_ordered_amount + current_row_amount > brn_amount:
            frappe.throw(
                _("Row {0}: Amount {1} exceeds BRN balance amount. Available BRN Amount: {2} in {3}")
                .format(
                    row.idx,
                    current_row_amount,
                    brn_amount - already_ordered_amount,
                    brn_link,
                ),
                title=_("Amount Exceeded"),
            )
