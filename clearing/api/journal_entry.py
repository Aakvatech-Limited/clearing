# Copyright (c) 2024, Nelson Mpanju and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, nowdate
from typing import Optional
from clearing.api.utils import (
    get_expense_account,
    get_cash_or_bank_account,
    get_clearing_receivable_account,
    get_journal_entry_party_summary,
    get_receivable_account,
    infer_party_from_journal_entry,
)


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

    # Backfill payment date into the clearance document (allow_on_submit field)
    try:
        if frappe.db.has_column(doc.doctype, "paid_from"):
            frappe.db.set_value(doc.doctype, doc.name, "paid_from", je.posting_date)
    except Exception:
        # Non-fatal if field doesn't exist on a particular clearance doctype
        pass


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

    # Accounts
    party_account = get_clearing_receivable_account(company) or get_expense_account(
        doc.doctype, company
    )
    bank_account = get_cash_or_bank_account(company)

    amount = flt(doc.total_charges)

    je.append(
        "accounts",
        {
            "account": party_account,
            "party_type": "Customer",
            "party": customer,
            "debit_in_account_currency": amount,
            "credit_in_account_currency": 0,
            "user_remark": _("{0}: {1}").format(doc.doctype, doc.name),
        },
    )

    je.append(
        "accounts",
        {
            "account": bank_account,
            "debit_in_account_currency": 0,
            "credit_in_account_currency": amount,
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
def make_payment_entry_from_journal_entry(
    journal_entry: str,
    party_account: Optional[str] = None,
    allocated_amount: Optional[float] = None,
):
    from erpnext.accounts.doctype.payment_entry.payment_entry import get_party_details

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
