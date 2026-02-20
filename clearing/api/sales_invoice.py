import re
from typing import Dict, List, Optional

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, getdate, nowdate


def _coerce_name_list(values) -> List[str]:
    if values is None:
        return []

    if isinstance(values, str):
        try:
            parsed = frappe.parse_json(values)
            if isinstance(parsed, (list, tuple)):
                values = list(parsed)
            else:
                values = [values]
        except Exception:
            values = [values]

    names: List[str] = []
    seen = set()
    for value in values or []:
        name = cstr(value).strip()
        if not name or name in seen:
            continue
        names.append(name)
        seen.add(name)
    return names


def _resolve_company_and_customer(cc_doc) -> tuple[str, str]:
    company = None
    customer = cstr(cc_doc.consigee).strip() or None

    if cc_doc.clearing_file:
        cf_company, cf_customer = frappe.db.get_value(
            "Clearing File", cc_doc.clearing_file, ["company", "customer"]
        ) or (None, None)
        company = cf_company or company
        customer = customer or cf_customer

    company = company or frappe.defaults.get_user_default("Company")
    if not company:
        frappe.throw(_("Unable to determine Company for Sales Invoice draft."))
    if not customer:
        frappe.throw(_("Please set a Consignee before generating an invoice."))
    return company, customer


def _resolve_selected_charge_rows(cc_doc, charge_rows) -> List[object]:
    selected_names = _coerce_name_list(charge_rows)
    if not selected_names:
        frappe.throw(_("Please select at least one charge."))

    rows_by_name: Dict[str, object] = {
        cstr(row.name): row for row in (cc_doc.get("charges") or []) if cstr(row.name)
    }

    selected: List[object] = []
    missing: List[str] = []
    for row_name in selected_names:
        row = rows_by_name.get(row_name)
        if not row:
            missing.append(row_name)
            continue
        selected.append(row)

    if missing:
        frappe.throw(
            _("Some selected rows were not found on {0}: {1}").format(
                cc_doc.name, ", ".join(missing)
            )
        )

    valid: List[object] = []
    for row in selected:
        idx = row.get("idx") or "?"
        if cint(row.get("is_invoice")) != 1:
            frappe.throw(_("Row {0} is not marked as invoice charge.").format(idx))
        if cstr(row.get("invoice_reference")).strip():
            frappe.throw(
                _("Row {0} is already linked to Sales Invoice {1}.").format(
                    idx, row.get("invoice_reference")
                )
            )
        if not cstr(row.get("charge_type")).strip():
            frappe.throw(_("Row {0} is missing Charge Type (Item Code).").format(idx))
        if flt(row.get("amount") or 0) <= 0:
            frappe.throw(_("Row {0} must have amount greater than zero.").format(idx))
        valid.append(row)

    return valid


def _normalize_posting_date(posting_date: Optional[str]):
    if not posting_date:
        return nowdate()
    try:
        return getdate(posting_date)
    except Exception:
        frappe.throw(_("Invalid posting date: {0}").format(posting_date))


def _upsert_clearing_charge_row_marker(invoice, row_names: List[str]):
    names = [cstr(name).strip() for name in row_names if cstr(name).strip()]
    if not names:
        return

    marker = "[CCROW:{0}]".format(",".join(names))
    remarks = cstr(getattr(invoice, "remarks", "") or "")

    if "[CCROW:" in remarks:
        remarks = re.sub(r"\[CCROW:[^\]]*\]", marker, remarks).strip()
    else:
        remarks = "{0}\n{1}".format(remarks, marker).strip() if remarks else marker

    invoice.remarks = remarks


@frappe.whitelist()
def make_sales_invoice_draft(
    clearing_charges: str, charge_rows=None, posting_date: Optional[str] = None
):
    cc_name = cstr(clearing_charges).strip()
    if not cc_name:
        frappe.throw(_("Clearing Charges is required."))

    cc_doc = frappe.get_doc("Clearing Charges", cc_name)
    company, customer = _resolve_company_and_customer(cc_doc)
    selected_rows = _resolve_selected_charge_rows(cc_doc, charge_rows)
    selected_row_names = [cstr(row.get("name")).strip() for row in selected_rows]
    posting_date = _normalize_posting_date(posting_date)

    invoice = frappe.new_doc("Sales Invoice")
    invoice.company = company
    invoice.customer = customer
    invoice.posting_date = posting_date
    invoice.clearing_charges = cc_doc.name
    if cc_doc.currency:
        invoice.currency = cc_doc.currency
    if invoice.meta.has_field("ignore_pricing_rule"):
        invoice.ignore_pricing_rule = 1

    source_rows: List[Dict[str, object]] = []
    for src in selected_rows:
        qty = flt(src.get("quantity") or 1)
        if qty <= 0:
            qty = 1
        item_code = cstr(src.get("charge_type")).strip()
        invoice.append(
            "items",
            {"item_code": item_code, "qty": qty},
        )
        source_rows.append(
            {
                "item_code": item_code,
                "qty": qty,
                "amount": flt(src.get("amount") or 0),
            }
        )

    # Populate mandatory item defaults (item_name, uom, income_account, etc.)
    invoice.run_method("set_missing_values")

    # Lock values from charge rows so price-list logic does not override them.
    # Use row order (append order) instead of child row name, because unsaved rows
    # can have empty/duplicate names before insert.
    invoice_rows = list(invoice.get("items") or [])
    for idx, src in enumerate(source_rows):
        if idx >= len(invoice_rows):
            break
        row = invoice_rows[idx]
        qty = flt(src.get("qty") or 1)
        if qty <= 0:
            qty = 1
        amount = flt(src.get("amount") or 0)
        rate = amount / qty if qty else amount

        row.qty = qty
        row.rate = rate
        row.price_list_rate = rate
        row.discount_percentage = 0
        row.discount_amount = 0
        row.amount = amount

    _upsert_clearing_charge_row_marker(invoice, selected_row_names)
    invoice.run_method("calculate_taxes_and_totals")
    return invoice.as_dict(no_nulls=True)
