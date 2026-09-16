import re
from datetime import datetime

import frappe
from frappe import _


@frappe.whitelist()
def create_brn(supplier_quotation):
    """
    Create a BRN record from a Supplier Quotation.
    """
    supplier_quotation = frappe.get_doc("Supplier Quotation", supplier_quotation)
    existing_brn_name = frappe.db.exists("BRN", {"quotation_requisition_id": supplier_quotation.custom_requisition_no})

    if not existing_brn_name:
        brn = frappe.get_doc({
            "doctype": "BRN",
            "company": supplier_quotation.company,
            "transaction_date": supplier_quotation.transaction_date,
            "duration_of_service_months": supplier_quotation.duration_of_service_months,
            "service_start_date": supplier_quotation.service_start_date,
            "is_new_vendor": supplier_quotation.is_new_vendor,
            "quotation_requisition_id": supplier_quotation.custom_requisition_no,
            "is_existing_vendor": supplier_quotation.is_existing_vendor,
            "existing_vendor": supplier_quotation.supplier,
            "msa_agreement": supplier_quotation.msa_agreement,
            "new_vendor": supplier_quotation.new_vendor,
            "supplier_quotation": supplier_quotation.name,
            "single":1,
        })

        brn.append("comparision", {
            "is_new_vendor": supplier_quotation.is_new_vendor,
            "is_existing_vendor": supplier_quotation.is_existing_vendor,
            "vendor_name": supplier_quotation.new_vendor if supplier_quotation.new_vendor else supplier_quotation.supplier_name,
            "existing_vendor": supplier_quotation.supplier,
            "preferred": 1 if supplier_quotation.workflow_state == "Selected" else 0,
        })

        brn.insert(ignore_mandatory=True)
        frappe.db.set_value("Supplier Quotation", supplier_quotation.name, "custom_brn", brn.name, update_modified=False)
        return {"name": brn.name, "is_new": True}

    brn = frappe.get_doc("BRN", existing_brn_name)
    if brn.docstatus == 0:
        if brn.single == 1:
            brn.single = 0
        brn.multi = 1
        brn.append("comparision", {
            "is_new_vendor": supplier_quotation.is_new_vendor,
            "is_existing_vendor": supplier_quotation.is_existing_vendor,
            "vendor_name": supplier_quotation.new_vendor if supplier_quotation.new_vendor else supplier_quotation.supplier_name,
            "existing_vendor": supplier_quotation.supplier,
            "preferred": 1 if supplier_quotation.workflow_state == "Selected" else 0,
        })
    brn.flags.ignore_mandatory = True
    brn.save()
    frappe.db.set_value("Supplier Quotation", supplier_quotation.name, "custom_brn", brn.name, update_modified=False)
    return {"name": brn.name, "is_new": False}




import frappe

# =====================================================================
# CREATE SUPPLIER QUOTATION
# =====================================================================

@frappe.whitelist()
def create_supplier_quotation_from_file(file_id):
    """One BRN can propose several vendors in its comparison table
    (existing + new). We create one Supplier Quotation per vendor row,
    not just the preferred one, so every proposal is captured."""
    try:
        data = extract_supplier_quotation_pdf(file_id)

        frappe.log_error(
            title="SQ Extraction Debug",
            message=frappe.as_json(data)
        )

        vendors = data.get("vendors") or []
        if not vendors:
            frappe.throw(
                "No vendors could be extracted from the PDF. "
                "Run debug_raw_tables to inspect the extracted table layout."
            )

        results = []
        for vendor in vendors:
            results.append(_create_quotation_for_vendor(data, vendor, file_id))

        frappe.db.commit()

        return {
            "status": "success",
            "quotations": results,
            "extracted_data": data,
        }

    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            frappe.get_traceback(),
            "Supplier Quotation PDF Import"
        )
        frappe.throw(
            "Unable to create Supplier Quotation. Please check the Error Log for details."
        )


def _create_quotation_for_vendor(data, vendor, file_id):
    """Builds and submits a single Supplier Quotation for one comparison
    table row. `data` holds the fields shared across every quotation
    created from this BRN (company, cost_center, dates, ...); `vendor`
    holds this row's own name/description/qty/rate/amount/onboarded flag."""

    onboarded_flag = (vendor.get("onboarded") or "").upper()
    is_existing_vendor = 1 if onboarded_flag.startswith("Y") else 0
    is_new_vendor = 0 if is_existing_vendor else 1

    supplier_name = vendor.get("name", "")
    supplier_code = ""
    new_vendor = ""

    if is_existing_vendor and supplier_name:
        supplier_code = _resolve_supplier(supplier_name)
    else:
        new_vendor = supplier_name

    # "Qty/Users" and "Periodicity (Months)" both live in the same
    # qty_period cell, in one of two wordings depending on the PDF
    # template - see _parse_qty_and_duration for both formats handled.
    qty, raw_uom, duration_months = _parse_qty_and_duration(vendor.get("qty_period", ""))

    # ------------------------------------------------------------------
    # Get Company Billing Address
    # ------------------------------------------------------------------
    billing_address = frappe.db.get_value(
        "Dynamic Link",
        {
            "link_doctype": "Company",
            "link_name": data.get("company"),
            "parenttype": "Address",
        },
        "parent",
    )

    # ------------------------------------------------------------------
    # Create Supplier Quotation
    # ------------------------------------------------------------------
    doc = frappe.get_doc({
        "doctype": "Supplier Quotation",

        "company": data.get("company"),
        "billing_address": billing_address,

        # Existing Vendor
        "supplier": supplier_code if is_existing_vendor else "",
        "supplier_name": supplier_name if is_existing_vendor else "",

        # Vendor Flags
        "is_existing_vendor": is_existing_vendor,
        "is_new_vendor": is_new_vendor,

        # Vendor Details
        "existing_vendor": supplier_code if is_existing_vendor else "",
        "new_vendor": new_vendor,

        # Other Fields
        "transaction_date": data.get("transaction_date"),
        "valid_till": data.get("valid_till"),
        "cost_center": data.get("cost_center"),
        "currency": data.get("currency"),
        "duration_of_service_months": duration_months,
        "service_start_date": data.get("service_start_date") or frappe.utils.today(),
        "msa_agreement": data.get("msa_agreement"),
        "custom_vendor_email": data.get("vendor_email"),

        # GST
        "gst_category": "Unregistered" if is_new_vendor else "",
    })

    description = vendor.get("description", "")

    # BRN items don't carry a real item_code - route them all to one
    # shared placeholder Item rather than guessing/creating a new Item
    # per free-text description.
    item_code = _get_or_create_placeholder_item()

    doc.append("items", {
        "item_code": item_code,
        "description": description,
        "hsn_sac": "",
        "qty": qty,
        "uom": PLACEHOLDER_ITEM_UOM,
        "rate": _to_float(vendor.get("rate")),
        "amount": _to_float(vendor.get("amount")),
    })

    # ignore_mandatory=True per requirement - BRN does not carry every
    # mandatory field (e.g. item_code), so validation is relaxed here.
    doc.insert(ignore_permissions=True, ignore_mandatory=True)

    # ------------------------------------------------------------------
    # Attach Uploaded PDF (same source file, shared across every
    # quotation created from it)
    # ------------------------------------------------------------------
    _attach_pdf_to_doc(file_id, doc)

    # ignore_mandatory has to be set again for submit, insert() does not
    # carry the flag forward into the submit validation cycle.
    doc.flags.ignore_mandatory = True
    doc.submit()

    return {
        "name": doc.name,
        "supplier_name": supplier_name,
        "is_existing_vendor": is_existing_vendor,
        "is_new_vendor": is_new_vendor,
        "docstatus": "Draft",
    }


def _attach_pdf_to_doc(file_id, doc):
    """Attaches the uploaded BRN to a Supplier Quotation. Since several
    quotations can come from the same upload, the first quotation gets
    the original File record re-pointed to it; every quotation after
    that gets its own File record pointing at the same physical file,
    since one File can only be attached to one document at a time."""
    if not file_id:
        return

    try:
        source_file = frappe.get_doc("File", file_id)
    except frappe.DoesNotExistError:
        frappe.log_error(
            title="Supplier Quotation Attachment",
            message=f"File not found: {file_id}"
        )
        return

    if not source_file.attached_to_name:
        source_file.attached_to_doctype = "Supplier Quotation"
        source_file.attached_to_name = doc.name
        source_file.save(ignore_permissions=True)
    else:
        copy_file = frappe.get_doc({
            "doctype": "File",
            "file_name": source_file.file_name,
            "file_url": source_file.file_url,
            "is_private": source_file.is_private,
            "attached_to_doctype": "Supplier Quotation",
            "attached_to_name": doc.name,
        })
        copy_file.insert(ignore_permissions=True)


# =====================================================================
# EXTRACTION
# =====================================================================

@frappe.whitelist()
def extract_supplier_quotation_pdf(file_id):
    try:
        if not frappe.db.exists("File", file_id):
            frappe.throw("Invalid File")

        file_doc = frappe.get_doc("File", file_id)
        file_path = file_doc.get_full_path()

        if not file_path.lower().endswith(".pdf"):
            frappe.throw("Only PDF files are allowed.")

        tables = _extract_tables(file_path)
        return _parse_brn_data(tables)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Supplier Quotation PDF Extraction")
        frappe.throw("Unable to extract PDF. Check Error Log for details.")


@frappe.whitelist()
def debug_raw_text(file_id):
    """Kept for backward compatibility / quick sanity checks."""
    file_doc = frappe.get_doc("File", file_id)
    file_path = file_doc.get_full_path()
    return {"raw_text": _extract_text(file_path)}


@frappe.whitelist()
def debug_raw_tables(file_id):
    """The BRN layout is table-driven, so this is the more useful debug
    endpoint now - it shows exactly what pdfplumber's table detector sees."""
    file_doc = frappe.get_doc("File", file_id)
    file_path = file_doc.get_full_path()
    return {"tables": _extract_tables(file_path)}


def _extract_text(file_path):
    import pdfplumber

    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text += (page.extract_text(layout=True) or "") + "\n"

    return text


def _extract_tables(file_path):
    """Business Requisition Notes are laid out as bordered tables, and
    pdfplumber's table detector reconstructs them far more reliably than
    regexing the wrapped, column-jumbled layout=True text does."""
    import pdfplumber

    all_tables = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                all_tables.append(table)

    return all_tables


# =====================================================================
# PARSING - Business Requisition Note (BRN) layout
# =====================================================================

def _parse_brn_data(tables):
    data = {
        "company": "",
        "cost_center": "",
        "currency": "",
        "transaction_date": "",
        "valid_till": "",
        "duration_of_service_months": "",
        "service_start_date": "",
        "msa_agreement": "",
        "gstin": "",
        "vendor_email": "",
        "preferred_supplier": "",  # informational only, no longer used to filter
        "vendors": [],
    }

    # ------------------------------------------------------------------
    # 1. Preferred Supplier (with reason) - kept for reference/debug only.
    # We now create a Supplier Quotation for every vendor row, not just
    # this one.
    # ------------------------------------------------------------------
    preferred_supplier_full = _value_after_marker(tables, "Preferred Supplier")
    data["preferred_supplier"] = (
        preferred_supplier_full.split(" - ")[0].strip()
        if preferred_supplier_full else ""
    )

    # ------------------------------------------------------------------
    # 2. Comparison Vendor Costing table -> one entry per proposed vendor
    # ------------------------------------------------------------------
    comparison_table = _find_table(tables, ["Proposed Vendors", "Onboarded"])
    data["vendors"] = _parse_comparison_table(comparison_table)

    # ------------------------------------------------------------------
    # 3. Header block. Two templates are in use:
    #   - Newer "Proposal" layout: a single row with "Proposal From" /
    #     "Proposal To" / "Proposal No. ... Date ... Valid Till Date" -
    #     entity_name, gstin, transaction_date and valid_till all come
    #     straight from here.
    #   - Older BRN layout: a "To Be Filled by Business Users" table with
    #     an "Entity Name" row; transaction_date/valid_till aren't in the
    #     PDF at all there, so they default to today.
    # ------------------------------------------------------------------
    proposal_header = _parse_proposal_header(tables)

    if proposal_header["entity_name"] or proposal_header["transaction_date"] or proposal_header["valid_till"]:
        entity_name = proposal_header["entity_name"]
        data["gstin"] = proposal_header["gstin"]
        data["vendor_email"] = proposal_header["vendor_email"]
        data["transaction_date"] = proposal_header["transaction_date"] or frappe.utils.today()
        data["valid_till"] = proposal_header["valid_till"] or frappe.utils.today()
    else:
        business_table = _find_table(tables, ["Particulars", "Details"])
        business_fields = _parse_business_table(business_table)
        entity_name = _lookup_field(business_fields, "Entity Name")
        data["transaction_date"] = frappe.utils.today()
        data["valid_till"] = frappe.utils.today()

    data["company"] = _resolve_company(entity_name)

    # cost_center is not read from the PDF - it's always "Main - {company abbr}"
    data["cost_center"] = _default_cost_center(data["company"])

    # ------------------------------------------------------------------
    # 4. Fixed / derived fields per business rule - common to every
    # quotation created from this BRN
    # ------------------------------------------------------------------
    data["service_start_date"] = str(frappe.utils.get_first_day(frappe.utils.today()))
    # duration_of_service_months is no longer a shared default - each
    # vendor row can quote its own periodicity, so it's parsed per-vendor
    # in _create_quotation_for_vendor via _parse_qty_and_duration().

    return data


def _parse_proposal_header(tables):
    """Newer 'Proposal' PDF layout ships one 3-column header row, e.g.:
    ['Proposal From\\nName: ...\\n...\\nGSTIN : 27AAAFC0662N1ZF\\n...',
     'Proposal To\\nEntity Name : Jio Financial Services\\nLimited\\nAddress : ...',
     'Proposal\\nNo. : 0987\\nDate : 09/07/2026\\nValid Till Date :10/07/2026']

    Returns empty strings for anything not found, so the caller can fall
    back to the older BRN "To Be Filled by Business Users" table instead.
    """
    result = {"entity_name": "", "gstin": "", "vendor_email": "", "transaction_date": "", "valid_till": ""}

    header_table = _find_table(tables, ["Proposal From", "Proposal To"])
    if not header_table or not header_table[0]:
        return result

    row = header_table[0]
    from_cell = (row[0] or "") if len(row) > 0 else ""
    to_cell = (row[1] or "") if len(row) > 1 else ""
    meta_cell = (row[2] or "") if len(row) > 2 else ""

    gstin_match = re.search(r"GSTIN\s*:\s*([A-Z0-9]+)", from_cell)
    if gstin_match:
        result["gstin"] = gstin_match.group(1).strip()

    entity_match = re.search(r"Entity Name\s*:\s*(.*?)\n\s*Address", to_cell, re.S)
    if entity_match:
        result["entity_name"] = _clean(entity_match.group(1))

    email_match = re.search(r"Vendor Email\s*:\s*(\S+@\S+)", to_cell)
    if email_match:
        result["vendor_email"] = email_match.group(1).strip()

    # "Date :" also occurs inside "Valid Till Date :" further down the same
    # cell, but re.search finds the leftmost match, and the proposal Date
    # line always comes first - so this reliably grabs the proposal date,
    # not the valid-till one.
    date_match = re.search(r"\bDate\s*:\s*(\d{2}/\d{2}/\d{4})", meta_cell)
    if date_match:
        result["transaction_date"] = _to_frappe_date(date_match.group(1), "%d/%m/%Y")

    valid_match = re.search(r"Valid Till Date\s*:\s*(\d{2}/\d{2}/\d{4})", meta_cell)
    if valid_match:
        result["valid_till"] = _to_frappe_date(valid_match.group(1), "%d/%m/%Y")

    return result


def _parse_comparison_table(table):
    """table rows look like:
    ['1', 'Canon Business\\nSolutions India Pvt\\nLtd',
     'Managed Print Service\\n- MFP Lease +\\nMaintenance',
     '12 units / 12\\nmonths', None, '18,500', '22,20,000', 'Y']
    """
    rows = []
    if not table:
        return rows

    for row in table:
        if not row or not row[0]:
            continue
        sno = row[0].strip()
        if not sno.isdigit():
            continue

        row = row + [None] * (8 - len(row))  # pad defensively

        # The comparison table is returned by pdfplumber as one block that
        # also includes its section-number row (e.g. "3  Comparison Vendor
        # Costing ...") and the related-party row, both of which start with
        # a digit too. Real vendor rows always carry a rate and an amount -
        # skip anything that doesn't.
        if row[5] is None or row[6] is None:
            continue

        rows.append({
            "sno": sno,
            "name": _clean(row[1]),
            "description": _clean(row[2]),
            "qty_period": _clean(row[3]),
            "rate": row[5],
            "amount": row[6],
            "onboarded": _clean(row[7]).upper(),
        })

    return rows


def _parse_business_table(table):
    fields = {}
    if not table:
        return fields

    for row in table:
        if not row or len(row) < 2:
            continue
        label = _clean(row[-2])
        value = _clean(row[-1])
        if label and value:
            fields[label] = value

    return fields


def _lookup_field(fields_dict, keyword):
    for key, value in fields_dict.items():
        if keyword.lower() in key.lower():
            return value
    return ""


def _find_table(tables, must_contain):
    """Returns the first table whose flattened text contains every string
    in must_contain (case-sensitive substring match)."""
    for table in tables:
        joined = " ".join(
            cell for row in table if row for cell in row if cell
        )
        if all(marker in joined for marker in must_contain):
            return table
    return None


def _value_after_marker(tables, marker):
    """Finds the row containing `marker` and returns the very next row's
    text - matches the '<label row> / <value row>' pattern the BRN uses
    for its free-text sections (Preferred Supplier, ...)."""
    for table in tables:
        for i, row in enumerate(table):
            joined = " ".join(c for c in row if c) if row else ""
            if marker in joined and i + 1 < len(table):
                nxt = table[i + 1]
                return _clean(" ".join(c for c in nxt if c))
    return ""


def _parse_qty_and_duration(qty_period_text):
    """The comparison table's qty_period cell has been seen in two
    wordings:
      - Old:  "12 units / 12 months"
      - New:  "Qty/Users:-12\\nPeriodicity\\n(Months) – 12"
    Returns (qty, uom_word, duration_of_service_months). uom_word is ""
    when the text doesn't spell out a unit (the new format doesn't).
    """
    text = qty_period_text or ""
    qty = 0.0
    uom_word = ""
    duration = None

    # New format: explicit "Qty/Users" and "Periodicity (Months)" labels
    qty_match = re.search(r"Qty\s*/?\s*Users?\s*:?-?\s*(\d+(?:\.\d+)?)", text, re.I)
    duration_match = re.search(
        r"Periodicity.*?\(?\s*Months?\s*\)?\s*[-–:]?\s*(\d+(?:\.\d+)?)",
        text, re.I | re.S,
    )

    if qty_match:
        qty = float(qty_match.group(1))
    if duration_match:
        duration = float(duration_match.group(1))

    if not qty_match:
        # Old format fallback: "12 units / 12 months" - first number+word
        # pair is the qty/uom.
        m = re.search(r"([\d.]+)\s*([A-Za-z]+)", text)
        if m:
            qty = float(m.group(1))
            uom_word = m.group(2)

    if duration is None:
        # Old format fallback: any "<number> month(s)" in the text.
        m2 = re.search(r"(\d+(?:\.\d+)?)\s*months?", text, re.I)
        if m2:
            duration = float(m2.group(1))

    if duration is None:
        duration = 1  # last-resort default when nothing at all is found

    duration = int(duration) if float(duration).is_integer() else duration

    return qty, uom_word, duration


def _clean(value):
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _to_float(value):
    if value in (None, ""):
        return 0.0
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return 0.0


def _to_frappe_date(date_str, fmt):
    try:
        return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
    except Exception:
        return None


def _resolve_company(entity_name):
    if not entity_name:
        return entity_name
    if frappe.db.exists("Company", entity_name):
        return entity_name
    match = frappe.db.get_value("Company", {"company_name": entity_name}, "name")
    return match or entity_name


def _resolve_supplier(supplier_name):
    return frappe.db.get_value("Supplier", {"supplier_name": supplier_name}, "name") or ""


def _default_cost_center(company):
    """Every Company in Frappe auto-creates a default "Main - {abbr}" cost
    center, so we build it from the company's abbreviation instead of
    reading anything off the PDF."""
    if not company:
        return ""
    abbr = frappe.db.get_value("Company", company, "abbr")
    if not abbr:
        return ""
    return f"Main - {abbr}"


# Common BRN wording -> a UOM that's actually likely to exist in the system.
# "units"/"user"/"license" etc are how business users phrase quantities in
# the PDF, but they usually aren't real UOM records - extend this as needed.
_UOM_ALIASES = {
    "unit": "Nos",
    "units": "Nos",
    "user": "Nos",
    "users": "Nos",
    "license": "Nos",
    "licenses": "Nos",
}


def _normalize_uom(raw_uom):
    if not raw_uom:
        return "Nos"

    key = raw_uom.strip().lower()
    candidate = _UOM_ALIASES.get(key, raw_uom.strip().title())

    if frappe.db.exists("UOM", candidate):
        return candidate
    if frappe.db.exists("UOM", "Nos"):
        return "Nos"
    return candidate  # let Frappe's own validation surface the missing UOM


PLACEHOLDER_ITEM_NAME = "Item Customize as per Description"
PLACEHOLDER_ITEM_UOM = "EA"
PLACEHOLDER_ITEM_DESCRIPTION = (
    "standard item supplier quotation to be updated by user in brn as per description provided"
)


def _get_or_create_placeholder_item():
    """Whenever a BRN item has no real item_code, everything routes to this
    one shared placeholder Item rather than guessing/creating a new Item
    per free-text description - business users then update the row with
    the correct real Item afterwards."""
    existing = frappe.db.get_value("Item", {"item_name": PLACEHOLDER_ITEM_NAME}, "name")
    if existing:
        return existing

    item_group = "Services" if frappe.db.exists("Item Group", "Services") \
        else (frappe.db.get_value("Item Group", {}, "name") or "All Item Groups")

    item = frappe.get_doc({
        "doctype": "Item",
        "item_code": PLACEHOLDER_ITEM_NAME,
        "item_name": PLACEHOLDER_ITEM_NAME,
        "description": PLACEHOLDER_ITEM_DESCRIPTION,
        "item_group": item_group,
        "stock_uom": PLACEHOLDER_ITEM_UOM,
        "is_stock_item": 0,
        "gst_hsn_code":"00000000"
    })
    item.insert(ignore_permissions=True, ignore_mandatory=True)
    return item.name
