# Copyright (c) 2024, Nelson Mpanju and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, nowdate, cstr
from erpnext import get_company_currency
from erpnext.setup.utils import get_exchange_rate
from typing import Dict, List, Optional, Sequence, Union
from clearing.api.utils import (
    get_expense_account,
    get_cash_or_bank_account,
    get_clearing_receivable_account,
    get_journal_entry_party_summary,
    get_receivable_account,
    infer_party_from_journal_entry,
)


def _find_receivable_account_for_currency(customer: str, company: str, currency: str) -> Optional[str]:
    """Return a receivable account for the customer/company with the desired currency, if any."""
    if not (customer and company and currency):
        return None

    rows = frappe.db.sql(
        """
        select pa.account
        from `tabParty Account` pa
        join `tabAccount` a on a.name = pa.account
        where pa.parenttype = 'Customer'
          and pa.parent = %(customer)s
          and pa.company = %(company)s
          and a.account_currency = %(currency)s
          and a.is_group = 0
        limit 1
        """,
        {"customer": customer, "company": company, "currency": currency},
        as_dict=True,
    )
    if rows:
        return rows[0]["account"]

    # fallback: any receivable leaf for company with matching currency
    acc = frappe.db.get_value(
        "Account",
        {
            "company": company,
            "account_type": "Receivable",
            "is_group": 0,
            "account_currency": currency,
        },
        "name",
    )
    return acc


def create_or_update_journal_entry_for_clearance(doc, method=None):
    """
    Create a Journal Entry per clearance document and submit it.

    Args:
        doc: The clearance document being submitted
        method: The event method (on_submit)
    """
    if not getattr(doc, "paid_by_clearing_agent", None) or not getattr(
        doc, "total_charges", None
    ):
        return

    clearing_file = getattr(doc, "clearing_file", None)
    if not clearing_file:
        frappe.throw(_("Clearing File reference is missing"))

    # Prevent accidental duplicates if handler is invoked twice
    existing = frappe.get_all(
        "Journal Entry",
        filters={
            "clearing_file": clearing_file,
            "docstatus": 1,
            "user_remark": ["like", f"%{doc.doctype}: {doc.name}%"],
        },
        pluck="name",
    )
    if existing:
        return

    je = create_new_journal_entry_for_single_clearance(doc)
    je.save()
    je.submit()

    frappe.msgprint(
        _("Journal Entry {0} submitted for {1} {2}").format(
            je.name, doc.doctype, doc.name
        ),
        alert=True,
    )


def create_new_journal_entry_for_single_clearance(doc):
    """
    Build a Journal Entry (Debit Note) for a single clearance document.

    Debit: single receivable party account (from Clearing Settings)
    Credit: Cash/Bank account (from Clearing Settings)
    """
    clearing_file = doc.clearing_file
    clearing_file_doc = frappe.get_doc("Clearing File", clearing_file)

    if not clearing_file_doc.customer:
        frappe.throw(
            _("Customer is not set in Clearing File {0}").format(clearing_file)
        )

    je = frappe.new_doc("Journal Entry")
    je.posting_date = nowdate()
    je.company = clearing_file_doc.company or frappe.defaults.get_user_default(
        "Company"
    )
    je.clearing_file = clearing_file
    je.voucher_type = "Debit Note"
    je.user_remark = _("{0}: {1} | Clearing File {2}").format(
        doc.doctype, doc.name, clearing_file
    )

    company = je.company
    customer = clearing_file_doc.customer
    doc_currency = getattr(clearing_file_doc, "currency", None) or getattr(doc, "currency", None)

    # Accounts
    party_account = get_clearing_receivable_account(company, currency=doc_currency)
    party_account_currency = (
        frappe.get_cached_value("Account", party_account, "account_currency")
        if party_account
        else None
    )

    if doc_currency and party_account_currency != doc_currency:
        candidate = _find_receivable_account_for_currency(customer, company, doc_currency)
        if candidate:
            party_account = candidate
            party_account_currency = doc_currency
        else:
            frappe.throw(
                _(
                    "Receivable account currency ({0}) does not match document currency ({1}). "
                    "Please set a customer receivable account in currency {1} in Clearing Settings or Party Account."
                ).format(party_account_currency or _("Unknown"), doc_currency)
            )

    if not party_account:
        party_account = get_expense_account(doc.doctype, company, currency=doc_currency)
        party_account_currency = (
            frappe.get_cached_value("Account", party_account, "account_currency")
            if party_account
            else None
        )

    bank_account = get_cash_or_bank_account(company)
    bank_account_currency = (
        frappe.get_cached_value("Account", bank_account, "account_currency")
        if bank_account
        else None
    )

    company_currency = get_company_currency(company) if company else None
    if doc_currency:
        je.multi_currency = 1
    elif company_currency and (
        (party_account_currency and party_account_currency != company_currency)
        or (bank_account_currency and bank_account_currency != company_currency)
    ):
        je.multi_currency = 1

    party_exchange_rate = 1
    bank_exchange_rate = 1
    if company_currency:
        if party_account_currency and party_account_currency != company_currency:
            party_exchange_rate = get_exchange_rate(party_account_currency, company_currency, je.posting_date)
        if bank_account_currency and bank_account_currency != company_currency:
            bank_exchange_rate = get_exchange_rate(bank_account_currency, company_currency, je.posting_date)

    amount = flt(doc.total_charges)
    amount_in_bank_currency = amount
    if doc_currency and bank_account_currency and bank_account_currency != doc_currency:
        amount_in_bank_currency = flt(
            amount * get_exchange_rate(doc_currency, bank_account_currency, je.posting_date)
        )

    je.append(
        "accounts",
        {
            "account": party_account,
            "party_type": "Customer",
            "party": customer,
            "debit_in_account_currency": amount,
            "exchange_rate": party_exchange_rate,
            "credit_in_account_currency": 0,
            "user_remark": _("{0}: {1}").format(doc.doctype, doc.name),
        },
    )

    je.append(
        "accounts",
        {
            "account": bank_account,
            "debit_in_account_currency": 0,
            "credit_in_account_currency": amount_in_bank_currency,
            "exchange_rate": bank_exchange_rate,
        },
    )

    return je


def cancel_journal_entry_on_clearance_cancel(doc, method=None):
    """
    Update or cancel the journal entry when a clearance document is cancelled.

    Args:
        doc: The clearance document being cancelled
        method: The event method (on_cancel)
    """
    # Only process if paid by clearing agent
    if not doc.paid_by_clearing_agent or not doc.total_charges:
        return

    clearing_file = doc.clearing_file
    if not clearing_file:
        return

    # Find the journal entry created for this specific clearance (using remark tag)
    candidates = frappe.get_all(
        "Journal Entry",
        filters={
            "clearing_file": clearing_file,
            "docstatus": ["<", 2],
            "user_remark": ["like", f"%{doc.doctype}: {doc.name}%"],
        },
        pluck="name",
    )
    if not candidates:
        return

    for je_name in candidates:
        je = frappe.get_doc("Journal Entry", je_name)
        if je.docstatus == 1:
            je.cancel()
            frappe.msgprint(
                _("Journal Entry {0} has been cancelled").format(je.name), alert=True
            )
        else:
            je.delete()
            frappe.msgprint(
                _("Journal Entry {0} has been deleted").format(je.name), alert=True
            )


@frappe.whitelist()
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


def make_payment_entry_from_journal_entry(
    journal_entry: str,
    party_account: Optional[str] = None,
    allocated_amount: Optional[float] = None,
):
    from erpnext.accounts.doctype.payment_entry.payment_entry import get_party_details

    allocated_amount = _normalize_optional_amount(allocated_amount)

    je = frappe.get_doc("Journal Entry", journal_entry)
    if je.docstatus != 1:
        frappe.throw(
            _("Only submitted Journal Entry can be used to create a Payment Entry")
        )

    summary = get_journal_entry_party_summary(je)

    party_type: Optional[str] = summary.party_type
    party: Optional[str] = summary.party
    if not party_type or not party:
        # Fallback: allow manual completion
        frappe.msgprint(
            _(
                "No party found on Journal Entry {0}. Opening Payment Entry without party/reference."
            ).format(je.name),
            alert=True,
        )
        party_row = None
    else:
        # Locate representative row to pick account
        party_row = None
        for row in je.accounts:
            if row.get("party_type") == party_type and row.get("party") == party:
                party_row = row
                break
    payment_type = (
        "Receive"
        if party_type == "Customer"
        else ("Pay" if party_type == "Supplier" else "Receive")
    )

    # Build Payment Entry
    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = payment_type
    pe.company = je.company
    pe.posting_date = nowdate()

    # Add a marker so the client script can clamp references to this JE only
    note = _(f"[CFJE:{je.name}] Clearing payment for {party_type or ''} {party or ''}")
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

    # Set party normally - client script will handle filtering references
    if party_type and party:
        pe.party_type = party_type
        pe.party = party

    # Determine the party account used on the JE (to satisfy Payment Entry validation)
    je_party_account: Optional[str] = party_account or None
    # Prefer a row with matching party that has the correct sign
    if not je_party_account:
        for row in je.accounts:
            if row.get("party_type") == party_type and row.get("party") == party:
                if payment_type == "Receive" and (
                    row.get("debit_in_account_currency") or row.get("debit")
                ):
                    if (
                        float(
                            row.get("debit_in_account_currency")
                            or row.get("debit")
                            or 0
                        )
                        > 0
                    ):
                        je_party_account = row.get("account")
                        break
                if payment_type == "Pay" and (
                    row.get("credit_in_account_currency") or row.get("credit")
                ):
                    if (
                        float(
                            row.get("credit_in_account_currency")
                            or row.get("credit")
                            or 0
                        )
                        > 0
                    ):
                        je_party_account = row.get("account")
                        break
    # Fallback to any party row account
    if not je_party_account and party_row:
        je_party_account = party_row.get("account")

    # If still missing, fallback to default party account details
    party_details = None
    if party_type and party:
        party_details = get_party_details(
            company=je.company,
            party_type=party_type,
            party=party,
            date=pe.posting_date,
            cost_center=None,
        )

    if je_party_account:
        if payment_type == "Receive":
            pe.paid_from = je_party_account
            pe.paid_from_account_currency = frappe.get_cached_value(
                "Account", je_party_account, "account_currency"
            )
        else:
            pe.paid_to = je_party_account
            pe.paid_to_account_currency = frappe.get_cached_value(
                "Account", je_party_account, "account_currency"
            )
    elif party_details:
        # Fallback to default party account
        if payment_type == "Receive":
            pe.paid_from = party_details.get("party_account")
            pe.paid_from_account_currency = party_details.get("party_account_currency")
            pe.paid_from_account_balance = party_details.get("account_balance")
        else:
            pe.paid_to = party_details.get("party_account")
            pe.paid_to_account_currency = party_details.get("party_account_currency")
            pe.paid_to_account_balance = party_details.get("account_balance")

    # Set the bank/cash side from Clearing Settings to ensure both sides are present
    try:
        bank_gl = get_cash_or_bank_account(je.company)
        if payment_type == "Receive":
            if not pe.paid_to:
                pe.paid_to = bank_gl
                # Ensure mandatory currency fields are populated
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

    # Carry over useful party info
    if party_details:
        pe.party_balance = party_details.get("party_balance")
        pe.party_name = party_details.get("party_name")
        if party_details.get("party_bank_account"):
            pe.party_bank_account = party_details.get("party_bank_account")
        if party_details.get("bank_account"):
            pe.bank_account = party_details.get("bank_account")

    # Reference details for Journal Entry to prefill amounts
    party_account_currency = None
    if je_party_account:
        party_account_currency = frappe.get_cached_value(
            "Account", je_party_account, "account_currency"
        )
    elif party_details:
        party_account_currency = party_details.get("party_account_currency")
    elif party_row:
        party_account_currency = party_row.get("account_currency")
    else:
        party_account_currency = frappe.get_cached_value(
            "Company", je.company, "default_currency"
        )

    allocated = 0
    # Only add the selected Journal Entry as the single reference
    pe.set("references", [])
    total_amount = summary.total
    outstanding = summary.outstanding

    if party_type and party:
        if allocated_amount is not None:
            allocated = min(outstanding, flt(allocated_amount))
        else:
            allocated = outstanding
        pe.append(
            "references",
            {
                "reference_doctype": "Journal Entry",
                "reference_name": je.name,
                "due_date": getattr(je, "posting_date", None),
                "total_amount": total_amount,
                "outstanding_amount": outstanding,
                "allocated_amount": allocated,
            },
        )
    else:
        frappe.msgprint(
            _(
                "Journal Entry {0} has no party on its accounts. Opening Payment Entry without a reference."
            ).format(je.name),
            alert=True,
        )

    # Prefill amounts to speed up usage; UI will recompute as needed
    if payment_type == "Receive":
        pe.paid_amount = allocated
        pe.received_amount = allocated
    else:
        pe.received_amount = allocated
        pe.paid_amount = allocated

    # Set flags to prevent ERPNext from auto-fetching outstanding documents
    pe.flags.ignore_get_outstanding = True
    pe.flags.ignore_validate_update_after_submit = True
    pe.flags.dont_validate_allocated = (
        True  # New: Allow manual header edits without ref validation
    )
    pe.flags.clearing_je_marker = je.name  # Store the selected JE name

    return pe


def normalize_child_row_selection(raw: Union[str, Sequence[str], None]) -> List[str]:
    """Normalise the multi-check payload coming from the client side."""
    if raw is None:
        return []

    if isinstance(raw, str):
        try:
            parsed = frappe.parse_json(raw)
        except Exception:
            frappe.throw(_("Unable to parse the selected charges list."))
        else:
            if isinstance(parsed, (list, tuple, set)):
                values = list(parsed)
            elif parsed in (None, ""):
                values = []
            else:
                values = [parsed]
    elif isinstance(raw, (list, tuple, set)):
        values = list(raw)
    else:
        frappe.throw(_("Invalid charges payload."))

    cleaned: List[str] = []
    for entry in values:
        if isinstance(entry, str):
            name = entry.strip()
        elif isinstance(entry, dict):
            name = cstr(entry.get("name") or entry.get("value") or "").strip()
        else:
            name = cstr(entry).strip()
        if name:
            cleaned.append(name)

    unique: List[str] = []
    seen = set()
    for name in cleaned:
        if name in seen:
            continue
        seen.add(name)
        unique.append(name)
    return unique


def get_disbursement_journal_entry_defaults(clearing_file: str) -> Dict[str, object]:
    if not clearing_file:
        frappe.throw(_("Clearing File is required"))

    cf = frappe.get_doc("Clearing File", clearing_file)
    doc_currency = getattr(cf, "currency", None)

    company = cf.company or frappe.defaults.get_user_default("Company")
    if not company:
        frappe.throw(_("Company is not set on Clearing File {0}").format(clearing_file))

    customer = cf.customer
    if not customer:
        frappe.throw(_("Customer is not set on Clearing File {0}").format(clearing_file))

    party_account = get_clearing_receivable_account(company, currency=doc_currency)
    party_account_currency = (
        frappe.get_cached_value("Account", party_account, "account_currency")
        if party_account
        else None
    )
    if doc_currency and party_account_currency != doc_currency:
        candidate = _find_receivable_account_for_currency(customer, company, doc_currency)
        if candidate:
            party_account = candidate
            party_account_currency = doc_currency
        else:
            frappe.throw(
                _(
                    "Receivable account currency ({0}) does not match document currency ({1}). "
                    "Please set a receivable account in currency {1} for this customer/company."
                ).format(party_account_currency or _("Unknown"), doc_currency)
            )

    if not party_account:
        party_account = get_expense_account("Clearing Charges", company, currency=doc_currency)
        party_account_currency = (
            frappe.get_cached_value("Account", party_account, "account_currency")
            if party_account
            else None
        )

    bank_account = get_cash_or_bank_account(company)

    bank_account_currency = None
    if bank_account:
        bank_account_currency = frappe.get_cached_value("Account", bank_account, "account_currency")

    return {
        "company": company,
        "currency": doc_currency,
        "voucher_type": "Debit Note",
        "party_type": "Customer",
        "party": customer,
        "party_account": party_account,
        "party_account_currency": party_account_currency,
        "bank_account": bank_account,
        "bank_account_currency": bank_account_currency,
    }


def create_child_table_journal_entries(
    doc,
    *,
    table_field: str,
    selected_names: Sequence[str],
    posting_date: Optional[str] = None,
    label_field: str = "item",
    journal_field: str = "journal_entry",
    disbursed_date_field: str = "disbursed_date",
) -> List[Dict[str, str]]:
    """Create Journal Entries for arbitrary child-table charge rows."""
    if not doc:
        frappe.throw(_("Document is required"))

    if doc.docstatus == 2:
        frappe.throw(_("Cannot create Journal Entries for a cancelled document."))

    clearing_file = getattr(doc, "clearing_file", None)
    if not clearing_file:
        frappe.throw(_("Please set a Clearing File before creating a Journal Entry."))

    selected = {name for name in selected_names if isinstance(name, str) and name.strip()}
    if not selected:
        frappe.throw(_("Please select at least one charge."))

    defaults = get_disbursement_journal_entry_defaults(clearing_file)
    party_account = defaults.get("party_account")
    bank_account = defaults.get("bank_account")
    if not party_account or not bank_account:
        frappe.throw(_("Please configure the Receivable and Cash/Bank accounts in Clearing Settings."))

    posting_date = posting_date or nowdate()
    company = defaults.get("company")
    company_currency = get_company_currency(company) if company else None
    voucher_type = defaults.get("voucher_type") or "Debit Note"
    party_type = defaults.get("party_type")
    party = defaults.get("party")
    party_account_currency = defaults.get("party_account_currency")
    bank_account_currency = defaults.get("bank_account_currency")
    doc_currency = defaults.get("currency") or getattr(doc, "currency", None)

    rows = list(doc.get(table_field) or [])
    if not rows:
        frappe.throw(_("No charge rows were found on this document."))

    if doc_currency and party_account_currency and party_account_currency != doc_currency:
        frappe.throw(
            _(
                "Receivable account currency ({0}) does not match document currency ({1}). "
                "Please set a receivable account in currency {1} for this customer/company."
            ).format(party_account_currency, doc_currency)
        )

    created: List[Dict[str, str]] = []
    require_save = doc.docstatus == 0

    for row in rows:
        row_name = getattr(row, "name", None)
        if not row_name or row_name not in selected:
            continue

        if getattr(row, journal_field, None):
            continue

        amount = flt(getattr(row, "amount", 0))
        if amount <= 0:
            continue

        header_remark, account_remark = _build_stage_disbursement_remarks(
            doc, row, label_field
        )

        amount_in_bank_currency = amount
        if doc_currency and bank_account_currency and bank_account_currency != doc_currency:
            amount_in_bank_currency = flt(
                amount * get_exchange_rate(doc_currency, bank_account_currency, posting_date)
            )

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = voucher_type
        je.posting_date = posting_date
        je.clearing_file = clearing_file
        if company:
            je.company = company
        if doc_currency:
            je.multi_currency = 1
        elif company_currency and (
            (party_account_currency and party_account_currency != company_currency)
            or (bank_account_currency and bank_account_currency != company_currency)
        ):
            je.multi_currency = 1
        if header_remark:
            je.user_remark = header_remark
            je.remark = header_remark

        party_exchange_rate = 1
        bank_exchange_rate = 1
        if company_currency:
            if party_account_currency and party_account_currency != company_currency:
                party_exchange_rate = get_exchange_rate(
                    party_account_currency, company_currency, posting_date
                )
            if bank_account_currency and bank_account_currency != company_currency:
                bank_exchange_rate = get_exchange_rate(
                    bank_account_currency, company_currency, posting_date
                )

        debit_row = {
            "account": party_account,
            "party_type": party_type,
            "party": party,
            "debit_in_account_currency": amount,
            "exchange_rate": party_exchange_rate,
            "user_remark": account_remark,
        }
        if party_account_currency:
            debit_row["account_currency"] = party_account_currency

        credit_row = {
            "account": bank_account,
            "credit_in_account_currency": amount_in_bank_currency,
            "exchange_rate": bank_exchange_rate,
        }
        if bank_account_currency:
            credit_row["account_currency"] = bank_account_currency
        if account_remark:
            credit_row["user_remark"] = account_remark

        je.set("accounts", [])
        je.append("accounts", debit_row)
        je.append("accounts", credit_row)
        je.insert()
        je.submit()

        if journal_field:
            setattr(row, journal_field, je.name)
        if disbursed_date_field:
            setattr(row, disbursed_date_field, posting_date)

        if doc.docstatus == 0:
            require_save = True
        else:
            updates = {}
            if journal_field:
                updates[journal_field] = je.name
            if disbursed_date_field:
                updates[disbursed_date_field] = posting_date
            if updates and getattr(row, "doctype", None) and getattr(row, "name", None):
                frappe.db.set_value(row.doctype, row.name, updates, update_modified=False)

        created.append({"charge": row_name, "journal_entry": je.name})

    if require_save and created:
        doc.save(ignore_permissions=True)

    return created


def _build_stage_disbursement_remarks(doc, row, label_field: Optional[str]) -> tuple[str, str]:
    doc_label = getattr(doc, "doctype", "Clearance")
    doc_name = (getattr(doc, "name", "") or "").strip()
    clearing_file = (getattr(doc, "clearing_file", "") or "").strip()
    label_value = ""
    if label_field:
        label_value = (getattr(row, label_field, "") or "").strip()

    account_parts: List[str] = []
    if doc_name:
        account_parts.append(f"{doc_label}: {doc_name}")
    if clearing_file:
        account_parts.append(f"Clearing File {clearing_file}")
    account_remark = " | ".join(account_parts)

    header_parts: List[str] = []
    if label_value:
        header_parts.append(label_value)
    if account_remark:
        header_parts.append(account_remark)
    header_remark = " | ".join(header_parts)

    return header_remark, account_remark


def _coerce_journal_entry_list(journal_entries) -> List[str]:
    if journal_entries is None:
        return []

    if isinstance(journal_entries, str):
        try:
            parsed = frappe.parse_json(journal_entries)
            if isinstance(parsed, (list, tuple)):
                journal_entries = list(parsed)
            else:
                journal_entries = [journal_entries]
        except Exception:
            journal_entries = [journal_entries]

    result: List[str] = []
    seen = set()
    for entry in journal_entries or []:
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

    # Prefer the account that appears most frequently
    counts = {}
    for acc in candidate_accounts:
        if acc:
            counts[acc] = counts.get(acc, 0) + 1
    if not counts:
        return None
    preferred = max(counts.items(), key=lambda x: x[1])[0]
    return preferred


@frappe.whitelist()
def make_payment_entry_from_journal_entries(
    journal_entries,
    total_amount: Optional[float] = None,
):
    names = _coerce_journal_entry_list(journal_entries)
    if not names:
        frappe.throw(_("Please select at least one Journal Entry."))

    total_amount = _normalize_optional_amount(total_amount)

    if len(names) == 1:
        return make_payment_entry_from_journal_entry(
            names[0],
            allocated_amount=total_amount,
        )

    docs = [frappe.get_doc("Journal Entry", name) for name in names]
    for je in docs:
        if je.docstatus != 1:
            frappe.throw(
                _("Only submitted Journal Entry can be used to create a Payment Entry (found {0}).").format(
                    je.name
                )
            )

    base_company = docs[0].company
    if any(je.company != base_company for je in docs):
        frappe.throw(_("Selected Journal Entries must belong to the same company."))

    base_summary = get_journal_entry_party_summary(docs[0])
    party_type = base_summary.party_type
    party = base_summary.party
    if not party_type or not party:
        frappe.throw(
            _("Journal Entry {0} is missing party information. Cannot prepare Payment Entry.").format(
                docs[0].name
            )
        )

    summaries = []
    total_outstanding = 0.0
    for je in docs:
        summary = get_journal_entry_party_summary(je, party_type=party_type, party=party)
        if summary.party_type != party_type or summary.party != party:
            frappe.throw(
                _("Journal Entry {0} has a different party from the others.").format(je.name)
            )
        outstanding = flt(summary.outstanding or 0)
        if outstanding <= 0:
            continue
        summaries.append((je, summary))
        total_outstanding += outstanding

    if not summaries:
        frappe.throw(_("The selected Journal Entries have no outstanding balance."))

    payment_type = (
        "Receive"
        if party_type == "Customer"
        else ("Pay" if party_type == "Supplier" else "Receive")
    )

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = payment_type
    pe.company = base_company
    pe.posting_date = nowdate()

    joined_names = ", ".join(names)
    note = _(f"[CFJE:{joined_names}] Clearing payment for {party_type or ''} {party or ''}")
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

    preferred_party_account = _find_party_account_for_entries(docs, party_type, party, payment_type)
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

    if total_allocated <= 0:
        frappe.throw(_("Unable to allocate any amount against the selected Journal Entries."))

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

    if remaining is not None and remaining < 0:
        remaining = 0.0

    # Inform the user if some selected entries were skipped due to zero outstanding or allocation limits
    skipped = [name for name in names if name not in consumed]
    if skipped:
        frappe.msgprint(
            _("Some Journal Entries were skipped because they have no outstanding balance or no amount was allocated: {0}").format(
                ", ".join(skipped)
            ),
            alert=True,
        )

    return pe
