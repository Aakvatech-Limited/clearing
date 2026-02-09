from typing import Dict, List, Optional, Tuple

import frappe
from frappe import _
from frappe.utils import cstr, flt, nowdate

from clearing.api.utils import get_cash_or_bank_account, get_journal_entry_party_summary


def _normalize_optional_amount(value) -> Optional[float]:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    try:
        number = flt(value)
    except Exception:
        frappe.throw(_("Unable to parse the amount value."))
    return number


def _coerce_reference_list(values) -> List[str]:
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

    result: List[str] = []
    seen = set()
    for entry in values or []:
        name = cstr(entry).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


def _find_party_account_for_entries(
    journal_entries: List[object],
    party_type: Optional[str],
    party: Optional[str],
    payment_type: str,
) -> Optional[str]:
    if not journal_entries or not party_type or not party:
        return None

    candidate_accounts = []
    for je in journal_entries:
        for row in getattr(je, "accounts", []) or []:
            if row.get("party_type") != party_type or row.get("party") != party:
                continue
            debit = flt(row.get("debit_in_account_currency") or row.get("debit") or 0)
            credit = flt(row.get("credit_in_account_currency") or row.get("credit") or 0)
            if payment_type == "Receive" and debit > 0:
                candidate_accounts.append(row.get("account"))
            elif payment_type == "Pay" and credit > 0:
                candidate_accounts.append(row.get("account"))

    if not candidate_accounts:
        return None

    counts = {}
    for acc in candidate_accounts:
        if acc:
            counts[acc] = counts.get(acc, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda x: x[1])[0]


def _get_outstanding_clearing_service_invoice_refs(
    clearing_charges: Optional[str],
    *,
    party_type: Optional[str],
    party: Optional[str],
    party_account_currency: Optional[str],
    company: Optional[str],
    selected_invoice_names: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, object]], List[str]]:
    if not clearing_charges or party_type != "Customer" or not party:
        return [], []

    cc = frappe.get_doc("Clearing Charges", clearing_charges)
    invoice_names: List[str] = []
    seen = set()
    for row in cc.get("clearing_services") or []:
        invoice_name = cstr(getattr(row, "reference_number", "")).strip()
        if not invoice_name or invoice_name in seen:
            continue
        seen.add(invoice_name)
        invoice_names.append(invoice_name)

    if selected_invoice_names:
        selected_set = {
            cstr(name).strip() for name in selected_invoice_names if cstr(name).strip()
        }
        invoice_names = [name for name in invoice_names if name in selected_set]

    if not invoice_names:
        return [], []

    from erpnext.accounts.doctype.payment_entry.payment_entry import get_reference_details

    party_currency = party_account_currency or (
        frappe.get_cached_value("Company", company, "default_currency")
        if company
        else None
    )

    refs: List[Dict[str, object]] = []
    for invoice_name in invoice_names:
        inv = frappe.db.get_value(
            "Sales Invoice",
            invoice_name,
            ["docstatus", "company", "customer", "due_date"],
            as_dict=True,
        )
        if not inv or int(inv.docstatus or 0) != 1:
            continue
        if company and inv.company and inv.company != company:
            continue
        if inv.customer and inv.customer != party:
            continue
        if not party_currency:
            continue

        ref = get_reference_details(
            reference_doctype="Sales Invoice",
            reference_name=invoice_name,
            party_account_currency=party_currency,
            party_type=party_type,
            party=party,
        )
        if not ref:
            continue

        outstanding = flt(ref.get("outstanding_amount", 0))
        if outstanding <= 0:
            continue

        refs.append(
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": invoice_name,
                "due_date": ref.get("due_date") or inv.due_date,
                "total_amount": flt(ref.get("total_amount") or outstanding),
                "outstanding_amount": outstanding,
            }
        )

    return refs, invoice_names


@frappe.whitelist()
def make_payment_entry_from_references(
    journal_entries=None,
    total_amount: Optional[float] = None,
    clearing_charges: Optional[str] = None,
    sales_invoices=None,
):
    names = _coerce_reference_list(journal_entries)
    selected_invoice_names = _coerce_reference_list(sales_invoices)
    clearing_charges = cstr(clearing_charges).strip() or None

    if not names and not selected_invoice_names and not clearing_charges:
        frappe.throw(_("Please select at least one Journal Entry or Sales Invoice."))

    total_amount = _normalize_optional_amount(total_amount)

    cc_company = None
    cc_customer = None
    if clearing_charges:
        cc_doc = frappe.get_doc("Clearing Charges", clearing_charges)
        if not cc_doc.clearing_file:
            frappe.throw(
                _("Clearing Charges {0} is missing a Clearing File.").format(
                    clearing_charges
                )
            )
        cc_company, cc_customer = frappe.db.get_value(
            "Clearing File", cc_doc.clearing_file, ["company", "customer"]
        ) or (None, None)
        if not cc_customer:
            frappe.throw(
                _("Customer is not set on Clearing File {0}.").format(
                    cc_doc.clearing_file
                )
            )

    docs = [frappe.get_doc("Journal Entry", name) for name in names]
    for je in docs:
        if je.docstatus != 1:
            frappe.throw(
                _(
                    "Only submitted Journal Entry can be used to create a Payment Entry (found {0})."
                ).format(je.name)
            )

    base_company = None
    party_type = None
    party = None
    summaries = []
    if docs:
        base_company = docs[0].company
        if any(je.company != base_company for je in docs):
            frappe.throw(_("Selected Journal Entries must belong to the same company."))

        base_summary = get_journal_entry_party_summary(docs[0])
        party_type = base_summary.party_type
        party = base_summary.party
        if not party_type or not party:
            frappe.throw(
                _(
                    "Journal Entry {0} is missing party information. Cannot prepare Payment Entry."
                ).format(docs[0].name)
            )

        for je in docs:
            summary = get_journal_entry_party_summary(
                je, party_type=party_type, party=party
            )
            if summary.party_type != party_type or summary.party != party:
                frappe.throw(
                    _("Journal Entry {0} has a different party from the others.").format(
                        je.name
                    )
                )
            outstanding = flt(summary.outstanding or 0)
            if outstanding <= 0:
                continue
            summaries.append((je, summary))

    if not base_company:
        base_company = cc_company
    if not party_type:
        party_type = "Customer" if cc_customer else None
    if not party:
        party = cc_customer

    if not base_company:
        frappe.throw(_("Unable to determine company for Payment Entry."))
    if not party_type or not party:
        frappe.throw(_("Unable to determine party for Payment Entry."))

    if cc_company and base_company != cc_company:
        frappe.throw(
            _(
                "Selected Journal Entries belong to company {0}, but Clearing Charges belongs to company {1}."
            ).format(base_company, cc_company)
        )
    if cc_customer and party_type == "Customer" and party != cc_customer:
        frappe.throw(
            _(
                "Selected Journal Entries belong to customer {0}, but Clearing Charges belongs to customer {1}."
            ).format(party, cc_customer)
        )

    payment_type = (
        "Receive"
        if party_type == "Customer"
        else ("Pay" if party_type == "Supplier" else "Receive")
    )

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = payment_type
    pe.company = base_company
    pe.posting_date = nowdate()

    marker_value = ", ".join(names) if names else clearing_charges
    note = _(f"[CFJE:{marker_value}] Clearing payment for {party_type or ''} {party or ''}")
    try:
        meta = frappe.get_meta("Payment Entry")
    except Exception:
        meta = None
    try:
        if meta and meta.has_field("custom_remarks"):
            pe.custom_remarks = note
    except Exception:
        pass
    pe.remarks = note

    pe.party_type = party_type
    pe.party = party

    party_details = None
    if party_type and party:
        from erpnext.accounts.doctype.payment_entry.payment_entry import get_party_details

        party_details = get_party_details(
            company=pe.company,
            party_type=party_type,
            party=party,
            date=pe.posting_date,
            cost_center=None,
        )

    preferred_party_account = _find_party_account_for_entries(
        docs, party_type, party, payment_type
    )
    if preferred_party_account:
        if payment_type == "Receive":
            pe.paid_from = preferred_party_account
            pe.paid_from_account_currency = frappe.get_cached_value(
                "Account", preferred_party_account, "account_currency"
            )
        else:
            pe.paid_to = preferred_party_account
            pe.paid_to_account_currency = frappe.get_cached_value(
                "Account", preferred_party_account, "account_currency"
            )
    elif party_details:
        if payment_type == "Receive":
            pe.paid_from = party_details.get("party_account")
            pe.paid_from_account_currency = party_details.get("party_account_currency")
            pe.paid_from_account_balance = party_details.get("account_balance")
        else:
            pe.paid_to = party_details.get("party_account")
            pe.paid_to_account_currency = party_details.get("party_account_currency")
            pe.paid_to_account_balance = party_details.get("account_balance")

    try:
        bank_gl = get_cash_or_bank_account(pe.company)
        if payment_type == "Receive":
            if not pe.paid_to:
                pe.paid_to = bank_gl
                pe.paid_to_account_currency = frappe.get_cached_value(
                    "Account", bank_gl, "account_currency"
                )
        else:
            if not pe.paid_from:
                pe.paid_from = bank_gl
                pe.paid_from_account_currency = frappe.get_cached_value(
                    "Account", bank_gl, "account_currency"
                )
    except Exception:
        pass

    if party_details:
        pe.party_balance = party_details.get("party_balance")
        pe.party_name = party_details.get("party_name")
        if party_details.get("party_bank_account"):
            pe.party_bank_account = party_details.get("party_bank_account")
        if party_details.get("bank_account"):
            pe.bank_account = party_details.get("bank_account")

    party_account_currency = (
        pe.paid_from_account_currency
        if payment_type == "Receive"
        else pe.paid_to_account_currency
    )
    if not party_account_currency and party_details:
        party_account_currency = party_details.get("party_account_currency")
    if not party_account_currency:
        party_account_currency = frappe.get_cached_value(
            "Company", pe.company, "default_currency"
        )

    invoice_refs, invoice_candidates = _get_outstanding_clearing_service_invoice_refs(
        clearing_charges,
        party_type=party_type,
        party=party,
        party_account_currency=party_account_currency,
        company=pe.company,
        selected_invoice_names=selected_invoice_names,
    )
    if not summaries and not invoice_refs:
        if names:
            frappe.throw(_("The selected Journal Entries have no outstanding balance."))
        frappe.throw(
            _("No outstanding Sales Invoices were found in Clearing Services for this document.")
        )

    pe.set("references", [])
    remaining = flt(total_amount) if total_amount else None
    total_allocated = 0.0
    consumed = set()
    for je, summary in summaries:
        outstanding = flt(summary.outstanding or 0)
        if outstanding <= 0:
            continue
        if remaining is not None and remaining <= 0:
            break
        allocated = outstanding
        if remaining is not None:
            allocated = min(outstanding, remaining)
            remaining -= allocated
        if allocated <= 0:
            continue
        pe.append(
            "references",
            {
                "reference_doctype": "Journal Entry",
                "reference_name": je.name,
                "due_date": getattr(je, "posting_date", None),
                "total_amount": flt(summary.total or 0),
                "outstanding_amount": outstanding,
                "allocated_amount": allocated,
            },
        )
        total_allocated += allocated
        consumed.add(je.name)

    consumed_invoices = set()
    for ref in invoice_refs:
        outstanding = flt(ref.get("outstanding_amount", 0))
        if outstanding <= 0:
            continue
        if remaining is not None and remaining <= 0:
            break
        allocated = outstanding
        if remaining is not None:
            allocated = min(outstanding, remaining)
            remaining -= allocated
        if allocated <= 0:
            continue
        pe.append(
            "references",
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": ref.get("reference_name"),
                "due_date": ref.get("due_date"),
                "total_amount": flt(ref.get("total_amount") or outstanding),
                "outstanding_amount": outstanding,
                "allocated_amount": allocated,
            },
        )
        total_allocated += allocated
        consumed_invoices.add(cstr(ref.get("reference_name")))

    if total_allocated <= 0:
        frappe.throw(
            _(
                "Unable to allocate any amount against the selected Journal Entries or Clearing Service invoices."
            )
        )

    if remaining is not None and remaining > 0 and total_allocated < flt(total_amount):
        total_allocated = flt(total_amount) - remaining

    if payment_type == "Receive":
        pe.paid_amount = total_allocated
        pe.received_amount = total_allocated
    else:
        pe.received_amount = total_allocated
        pe.paid_amount = total_allocated

    pe.flags.ignore_get_outstanding = True
    pe.flags.ignore_validate_update_after_submit = True
    pe.flags.dont_validate_allocated = True
    pe.flags.clearing_je_marker = names

    skipped = [name for name in names if name not in consumed]
    if skipped:
        frappe.msgprint(
            _(
                "Some Journal Entries were skipped because they have no outstanding balance or no amount was allocated: {0}"
            ).format(", ".join(skipped)),
            alert=True,
        )

    if clearing_charges:
        skipped_invoices = [
            invoice_name
            for invoice_name in invoice_candidates
            if invoice_name not in consumed_invoices
        ]
        if skipped_invoices:
            frappe.msgprint(
                _(
                    "Some Clearing Service invoices were skipped because they have no outstanding balance or no amount was allocated: {0}"
                ).format(", ".join(skipped_invoices)),
                alert=True,
            )

    return pe


@frappe.whitelist()
def make_payment_entry_from_journal_entries(
    journal_entries=None,
    total_amount: Optional[float] = None,
    clearing_charges: Optional[str] = None,
    sales_invoices=None,
):
    return make_payment_entry_from_references(
        journal_entries=journal_entries,
        total_amount=total_amount,
        clearing_charges=clearing_charges,
        sales_invoices=sales_invoices,
    )
