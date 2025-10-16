import numbers
import re
from typing import Dict, List, Optional, Tuple

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder import DocType
from frappe.utils import flt, now


def _update_fields_if_changed(doctype: str, docname: str, values: Dict[str, object]) -> bool:
    if not values:
        return False

    fieldnames = [field for field, value in values.items() if value is not None]
    if not fieldnames:
        return False

    current = frappe.db.get_value(doctype, docname, fieldnames, as_dict=True)
    if current is None:
        return False

    changed = {
        field: value
        for field, value in values.items()
        if value is not None and current.get(field) != value
    }

    if not changed:
        return False

    dt = DocType(doctype)
    query = frappe.qb.update(dt)
    for field, value in changed.items():
        query = query.set(dt[field], value)
    query = query.where(dt.name == docname)
    query.run()
    return True


def _get_target_clearing_file_status(payment_status: Optional[str], docstatus: int) -> str:
    status = (payment_status or "").strip()
    if status == "Paid":
        return "Closed" if docstatus == 1 else "Payment Received"
    return "Charges Pending"


def _set_numeric_if_changed(
    doc: Document, fieldname: str, value: object, *, tolerance: float = 1e-9
) -> bool:
    current = getattr(doc, fieldname, None)
    is_numeric = isinstance(value, numbers.Number) or isinstance(current, numbers.Number)

    if not is_numeric:
        if current == value:
            return False
        setattr(doc, fieldname, value)
        return True

    target = flt(value or 0)
    if current is None:
        setattr(doc, fieldname, target)
        return True

    current_value = flt(current or 0)
    if abs(current_value - target) <= tolerance:
        return False

    setattr(doc, fieldname, target)
    return True


class ClearingCharges(Document):
    def onload(self):
        # Ensure at least one clearing service row exists so UI logic can display invoice data
        self.ensure_primary_service_row(create=True, populate_from_legacy=True)

    def before_submit(self):
        if (self.status or "").strip() != "Paid":
            frappe.throw(
                _("You can only submit Clearing Charges when Payment Status is Paid.")
            )

    def before_save(self):
        self.ensure_primary_service_row(create=True, populate_from_legacy=True)
        if self._should_prompt_for_invoice():
            frappe.msgprint(_("Please generate invoice before printing Debit Note"))
        self.fetch_total_charges()
        self.sync_payment_status_from_invoice()
        self.populate_disbursement_and_reimbursement_tables()
        self._compute_reimbursement_totals()

    def get_primary_service_row(self):
        for row in getattr(self, "clearing_services", []):
            if getattr(row, "reference_number", None):
                return row
        table = getattr(self, "clearing_services", [])
        return table[0] if table else None

    def ensure_primary_service_row(
        self, *, create: bool = True, populate_from_legacy: bool = False
    ):
        row = self.get_primary_service_row()
        if row or not create:
            return row

        legacy = None
        if populate_from_legacy and self.name and not self.is_new():
            if frappe.db.has_column("Clearing Charges", "reference_number"):
                legacy = frappe.db.get_value(
                    "Clearing Charges",
                    self.name,
                    ["reference_number", "reference_date", "invoice_status"],
                    as_dict=True,
                )

        values = legacy or {}

        if self.docstatus == 0:
            row = self.append("clearing_services", {})
            row.reference_number = values.get("reference_number")
            row.reference_date = values.get("reference_date")
            row.invoice_status = values.get("invoice_status")
            return row

        if self.name:
            existing = frappe.db.get_all(
                "Clearing Services",
                filters={"parent": self.name},
                fields=["name"],
                limit_page_length=1,
            )
            if existing:
                child_doc = frappe.get_doc("Clearing Services", existing[0].name)
            else:
                child_doc = frappe.get_doc(
                    {
                        "doctype": "Clearing Services",
                        "parent": self.name,
                        "parenttype": "Clearing Charges",
                        "parentfield": "clearing_services",
                        "reference_number": values.get("reference_number"),
                        "reference_date": values.get("reference_date"),
                        "invoice_status": values.get("invoice_status"),
                    }
                )
                child_doc.insert(ignore_permissions=True)
            # Add to in-memory document for UI consumption if not already present
            already_linked = any(
                getattr(row, "name", None) == child_doc.name
                for row in getattr(self, "clearing_services", [])
            )
            if not already_linked:
                self.append("clearing_services", child_doc)
            return child_doc

        return None

    def _should_prompt_for_invoice(self) -> bool:
        cache = frappe.cache()
        cache_key = None
        if self.name and not self.is_new():
            cache_key = f"cc_invoice_warning::{frappe.session.user}::{self.name}"

        # Once an invoice exists, no warning is needed; also clear any stored flag
        if self.get_primary_invoice_number():
            if cache_key:
                cache.delete_value(cache_key)
            return False

        # Avoid spamming within the same request/instance
        if getattr(self, "_invoice_warning_shown", False):
            return False

        self._invoice_warning_shown = True

        if not self.name or self.is_new():
            # Unsaved documents rely on the per-instance flag above
            return True

        if cache.get_value(cache_key):
            return False

        cache.set_value(cache_key, now(), expires_in_sec=12 * 60 * 60)
        return True

    def get_primary_invoice_number(self) -> Optional[str]:
        row = self.get_primary_service_row()
        if row and getattr(row, "reference_number", None):
            return row.reference_number
        return None

    def fetch_total_charges(self):
        totals = {
            "tra": 0.0,
            "port": 0.0,
            "shipment": 0.0,
            "physical": 0.0,
            "transport": 0.0,
            "agency_fee": 0.0,
            "debit": 0.0,
        }
        for charge in self.charges:
            amount = flt(charge.amount or 0)
            charge_type = charge.charge_type
            if charge_type == "TRA Clearance":
                totals["tra"] += amount
            elif charge_type == "Port Clearance":
                totals["port"] += amount
            elif charge_type == "Shipping Line Clearance":
                totals["shipment"] += amount
            elif charge_type == "Physical Verification":
                totals["physical"] += amount
            elif charge_type == "Transport":
                totals["transport"] += amount
            elif charge_type == "Clearing Agency Fee":
                totals["agency_fee"] += amount
            if charge.is_invoice:
                totals["debit"] += amount

        debit_note_total = (
            totals["tra"] + totals["shipment"] + totals["physical"] + totals["port"]
        )
        invoice_total = totals["debit"]

        _set_numeric_if_changed(self, "tra_clearance_total", totals["tra"])
        _set_numeric_if_changed(self, "port_clearance_total", totals["port"])
        _set_numeric_if_changed(self, "shipment_clearance_total", totals["shipment"])
        _set_numeric_if_changed(self, "physical_clearance_total", totals["physical"])
        _set_numeric_if_changed(self, "total", debit_note_total)
        _set_numeric_if_changed(self, "transport_total", totals["transport"])
        _set_numeric_if_changed(self, "agency_fee", totals["agency_fee"])
        _set_numeric_if_changed(self, "total_debit", invoice_total)
        _set_numeric_if_changed(self, "total_clearing_charges", debit_note_total + invoice_total)

    def sync_payment_status_from_invoice(self):
        primary_row = self.ensure_primary_service_row(
            create=True, populate_from_legacy=True
        )
        primary_invoice = (
            getattr(primary_row, "reference_number", None) if primary_row else None
        )

        if not primary_invoice:
            self.status = "Draft"
            self._propagate_status_to_clearing_file()
            return

        inv = frappe.db.get_value(
            "Sales Invoice",
            primary_invoice,
            ["status", "docstatus", "posting_date"],
            as_dict=True,
        )
        if not inv:
            return

        # Keep primary row in sync with invoice state
        if primary_row:
            primary_row.invoice_status = inv.status
            if inv.posting_date:
                primary_row.reference_date = inv.posting_date

        # Update any additional rows in the table
        for row in getattr(self, "clearing_services", []):
            if not row or row == primary_row:
                continue
            if not getattr(row, "reference_number", None):
                continue
            extra_inv = frappe.db.get_value(
                "Sales Invoice",
                row.reference_number,
                ["status", "posting_date"],
                as_dict=True,
            )
            if extra_inv:
                row.invoice_status = extra_inv.status
                if extra_inv.posting_date:
                    row.reference_date = extra_inv.posting_date

        totals = get_payment_progress_for_clearing_file(
            self.clearing_file, primary_invoice
        )
        self.status = self._compute_status_from_invoice_and_reimbursements(
            inv.status, totals
        )
        self._propagate_status_to_clearing_file()

        if self.name and not self.name.startswith("New "):
            linked = frappe.db.get_value(
                "Sales Invoice", primary_invoice, "clearing_charges"
            )
            if linked != self.name:
                _update_fields_if_changed(
                    "Sales Invoice",
                    primary_invoice,
                    {"clearing_charges": self.name},
                )

    def populate_disbursement_and_reimbursement_tables(self) -> bool:
        modified = False
        if not self.clearing_file:
            if self.disbursement:
                self.disbursement = []
                modified = True
            if self.reimbursement:
                self.reimbursement = []
                modified = True
            return modified

        # Populate disbursements
        je_list = frappe.get_all(
            "Journal Entry",
            filters={"clearing_file": self.clearing_file, "docstatus": ["<", 2]},
            fields=["name"],
            order_by="posting_date asc, name asc",
        )
        current_disb = {
            row.journal_entry for row in self.disbursement if row.journal_entry
        }
        target_disb = {d.name for d in je_list}
        if current_disb != target_disb:
            self.disbursement = []
            for d in je_list:
                self.append("disbursement", {"journal_entry": d.name})
            modified = True

        # Populate reimbursements (submitted PEs referencing submitted JEs)
        submitted_je_names = frappe.get_all(
            "Journal Entry",
            filters={"clearing_file": self.clearing_file, "docstatus": 1},
            pluck="name",
        )
        if not submitted_je_names:
            self.reimbursement = []
            return

        pe_parents = frappe.get_all(
            "Payment Entry Reference",
            filters={
                "reference_doctype": "Journal Entry",
                "reference_name": ["in", submitted_je_names],
            },
            pluck="parent",
            distinct=True,
        )
        submitted_pe = [
            pe
            for pe in pe_parents
            if frappe.db.get_value("Payment Entry", pe, "docstatus") == 1
        ]
        current_reimb = {
            row.payment_entry for row in self.reimbursement if row.payment_entry
        }
        target_reimb = set(submitted_pe)
        if current_reimb != target_reimb:
            self.reimbursement = []
            for pe_name in submitted_pe:
                self.append("reimbursement", {"payment_entry": pe_name})
            modified = True

        return modified

    def _compute_status_from_invoice_and_reimbursements(
        self, invoice_status: str | None, totals: Dict | None
    ) -> str:
        status_key = (invoice_status or "").strip().lower()
        if not self.get_primary_invoice_number() or status_key in ("", "draft"):
            return "Draft"

        disb_total = flt((totals or {}).get("disb_total", 0))
        disb_out = flt((totals or {}).get("disb_outstanding", 0))
        disb_paid = max(disb_total - disb_out, 0)

        all_reimbursements_paid = disb_total > 0 and disb_out <= 0
        any_reimbursement_paid = disb_paid > 0
        has_disbursement_rows = any(
            bool(getattr(row, "journal_entry", None))
            for row in getattr(self, "disbursement", []) or []
        )

        if status_key == "paid":
            if has_disbursement_rows:
                return "Paid" if all_reimbursements_paid else "Partially Paid"
            return "Paid" if all_reimbursements_paid or disb_total == 0 else "Partially Paid"

        if status_key in ("partially paid", "partly paid") or any_reimbursement_paid:
            return "Partially Paid"

        if status_key in ("unpaid", "overdue", "submitted"):
            return "Pending Payment"

        return "Pending Payment"

    def _compute_reimbursement_totals(self):
        paid = outstanding = 0.0
        for row in self.reimbursement:
            paid += flt(row.paid_amount or 0)
            outstanding += flt(row.outstanding_amount or 0)
        self.total_paid_amount = paid
        self.total_outstanding_amount = outstanding

    def _propagate_status_to_clearing_file(self):
        if not self.clearing_file:
            return
        try:
            cf = frappe.get_doc("Clearing File", self.clearing_file)
            target_status = _get_target_clearing_file_status(self.status, cf.docstatus)
            _update_fields_if_changed("Clearing File", cf.name, {"status": target_status})
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"Clearing File update failed for {self.clearing_file}",
            )


@frappe.whitelist()
def get_disbursement_journal_entries(clearing_file: str) -> List[Dict]:
    if not clearing_file:
        return []
    je_list = frappe.get_all(
        "Journal Entry",
        filters={"clearing_file": clearing_file, "docstatus": ["<", 2]},
        fields=["name", "posting_date", "user_remark"],
        order_by="posting_date asc, name asc",
    )
    return [
        {"journal_entry": d.name, "date": d.posting_date, "remark": d.user_remark}
        for d in je_list
    ]


@frappe.whitelist()
def get_reimbursement_payments_for_journal_entries(clearing_file: str) -> List[Dict]:
    if not clearing_file:
        return []

    # Get submitted JEs and precompute per-JE summaries
    submitted_je_names = frappe.get_all(
        "Journal Entry",
        filters={"clearing_file": clearing_file, "docstatus": 1},
        pluck="name",
    )
    if not submitted_je_names:
        return []

    je_summaries = {}
    for je_name in submitted_je_names:
        je = frappe.get_doc("Journal Entry", je_name)
        party = frappe.db.get_value("Clearing File", clearing_file, "customer")
        party_total = 0.0
        for row in je.accounts:
            if row.party_type == "Customer" and row.party == party:
                party_total += flt(row.debit_in_account_currency or row.debit or 0)
                break
        paid = _get_total_paid_against_journal_entry(je_name)
        outstanding = max(party_total - paid, 0.0)
        je_summaries[je_name] = {
            "total": party_total,
            "paid": paid,
            "outstanding": outstanding,
        }

    # Get submitted PEs referencing these JEs, with paid per PE
    pe_data = frappe.get_all(
        "Payment Entry Reference",
        filters={
            "reference_doctype": "Journal Entry",
            "reference_name": ["in", submitted_je_names],
        },
        fields=["parent", "reference_name", "allocated_amount"],
    )
    pe_paid = {}
    for ref in pe_data:
        pe = ref.parent
        if pe not in pe_paid:
            pe_paid[pe] = {"paid": 0.0, "jes": set()}
        pe_paid[pe]["paid"] += flt(ref.allocated_amount or 0)
        pe_paid[pe]["jes"].add(ref.reference_name)

    # Filter submitted PEs and compute group outstanding
    data = []
    for pe, info in pe_paid.items():
        if frappe.db.get_value("Payment Entry", pe, "docstatus") != 1:
            continue
        jes = info["jes"]
        group_outstanding = sum(je_summaries[je]["outstanding"] for je in jes)
        party_name = frappe.db.get_value("Payment Entry", pe, "party_name")
        date = frappe.db.get_value("Payment Entry", pe, "posting_date")
        data.append(
            {
                "payment_entry": pe,
                "party": party_name,
                "date": date,
                "paid_amount": info["paid"],
                "outstanding_amount": group_outstanding,
            }
        )
    return data


def _get_total_paid_against_journal_entry(je_name: str) -> float:
    pe_refs = frappe.get_all(
        "Payment Entry Reference",
        filters={"reference_doctype": "Journal Entry", "reference_name": je_name},
        fields=["parent", "allocated_amount"],
    )
    total = 0.0
    for ref in pe_refs:
        if frappe.db.get_value("Payment Entry", ref.parent, "docstatus") == 1:
            total += flt(ref.allocated_amount or 0)
    return total


@frappe.whitelist()
def get_disbursement_journal_entries_detailed(clearing_file: str) -> List[Dict]:
    if not clearing_file:
        return []

    totals = get_payment_progress_for_clearing_file(clearing_file)
    if not totals or totals["disb_total"] == 0:
        return []

    submitted_je_names = frappe.get_all(
        "Journal Entry",
        filters={"clearing_file": clearing_file, "docstatus": 1},
        pluck="name",
    )
    results = []
    for je_name in submitted_je_names:
        je = frappe.get_doc("Journal Entry", je_name)
        clearance_type = None
        if je.user_remark:
            head = je.user_remark.split("|")[0].strip()
            if ":" in head:
                clearance_type = head.split(":", 1)[0].strip()
        _, _, outstanding = _summarise_party_payment_for_journal_entry(je)
        if outstanding > 0:
            results.append(
                {
                    "journal_entry": je.name,
                    "clearance_type": clearance_type,
                    "amount": totals["disb_total"],  # Aggregate; per-JE if needed
                    "outstanding": outstanding,
                    "date": je.posting_date,
                }
            )
    return results


def _summarise_party_payment_for_journal_entry(je) -> Tuple[float, float, float]:
    party = frappe.db.get_value(
        "Clearing File", getattr(je, "clearing_file", ""), "customer"
    )
    total = 0.0
    for row in je.accounts:
        if row.party_type == "Customer" and row.party == party:
            total += flt(row.debit_in_account_currency or row.debit or 0)
            break
    if total <= 0:
        return 0.0, 0.0, 0.0
    paid = _get_total_paid_against_journal_entry(je.name)
    outstanding = max(total - paid, 0.0)
    return total, paid, outstanding


def get_payment_progress_for_clearing_file(
    clearing_file: str, sales_invoice: Optional[str] = None
) -> Optional[Dict]:
    if not clearing_file:
        return None

    submitted_je_names = frappe.get_all(
        "Journal Entry",
        filters={"clearing_file": clearing_file, "docstatus": 1},
        pluck="name",
    )
    disb_total = disb_outstanding = 0.0
    for je_name in submitted_je_names:
        je = frappe.get_doc("Journal Entry", je_name)
        _, _, outstanding = _summarise_party_payment_for_journal_entry(je)
        party_total, _, _ = _summarise_party_payment_for_journal_entry(je)
        if party_total > 0:
            disb_total += party_total
            disb_outstanding += outstanding

    inv_total = inv_outstanding = 0.0
    if sales_invoice:
        inv = frappe.get_doc("Sales Invoice", sales_invoice)
        inv_total = flt(
            inv.rounded_total
            or inv.grand_total
            or inv.base_rounded_total
            or inv.base_grand_total
            or 0
        )
        inv_outstanding = flt(inv.outstanding_amount or 0)

    return {
        "disb_total": disb_total,
        "disb_outstanding": disb_outstanding,
        "disb_paid": max(disb_total - disb_outstanding, 0.0),
        "inv_total": inv_total,
        "inv_outstanding": inv_outstanding,
        "inv_paid": max(inv_total - inv_outstanding, 0.0),
    }


@frappe.whitelist()
def compute_clearing_charges_status(name: str) -> Dict:
    if not name:
        return {"status": None}
    cc = frappe.get_doc("Clearing Charges", name)
    primary_row = cc.ensure_primary_service_row(create=True, populate_from_legacy=True)
    inv_name = primary_row.reference_number if primary_row and primary_row.reference_number else None
    inv_status = (
        frappe.db.get_value("Sales Invoice", inv_name, "status") if inv_name else None
    )
    totals = get_payment_progress_for_clearing_file(cc.clearing_file, inv_name)
    status = cc._compute_status_from_invoice_and_reimbursements(inv_status, totals)
    return {"status": status}


@frappe.whitelist()
def sync_clearing_charges_status(name: str) -> Dict:
    if not name:
        return {"status": None}

    cc = frappe.get_doc("Clearing Charges", name)
    primary_row = cc.ensure_primary_service_row(create=True, populate_from_legacy=True)
    inv_name = primary_row.reference_number if primary_row and primary_row.reference_number else None
    inv_status = (
        frappe.db.get_value("Sales Invoice", inv_name, "status") if inv_name else None
    )
    totals = get_payment_progress_for_clearing_file(cc.clearing_file, inv_name)
    new_status = cc._compute_status_from_invoice_and_reimbursements(inv_status, totals)

    updates = {"status": new_status}
    if totals:
        updates["total_paid_amount"] = flt(totals.get("disb_paid", 0))
        updates["total_outstanding_amount"] = flt(totals.get("disb_outstanding", 0))

    def _apply_if_changed(doc, field, value):
        if value is None:
            return False
        current = doc.get(field)
        if current == value:
            return False
        doc.set(field, value)
        return True

    if cc.docstatus == 0:
        # Refresh tables
        dirty = bool(cc.populate_disbursement_and_reimbursement_tables())
        # Use getter for detailed reimbursements if needed
        reimb_rows = get_reimbursement_payments_for_journal_entries(cc.clearing_file)
        current_reimb = [
            (r.payment_entry, flt(r.paid_amount), flt(r.outstanding_amount))
            for r in cc.reimbursement
        ]
        target_reimb = [
            (r["payment_entry"], flt(r["paid_amount"]), flt(r["outstanding_amount"]))
            for r in reimb_rows
        ]
        if current_reimb != target_reimb:
            cc.reimbursement = []
            for row in reimb_rows:
                child = cc.append("reimbursement", {})
                child.payment_entry = row["payment_entry"]
                child.party = row.get("party")
                child.date = row["date"]
                child.paid_amount = row["paid_amount"]
                child.outstanding_amount = row["outstanding_amount"]

        dirty = bool(dirty)
        for field, value in updates.items():
            dirty |= _apply_if_changed(cc, field, value)

        if primary_row and inv_status is not None:
            dirty |= _apply_if_changed(primary_row, "invoice_status", inv_status)
            if inv_name:
                inv_posting_date = frappe.db.get_value(
                    "Sales Invoice", inv_name, "posting_date"
                )
                if inv_posting_date:
                    dirty |= _apply_if_changed(primary_row, "reference_date", inv_posting_date)

        if dirty:
            cc.save(ignore_permissions=True)
    else:
        parent_updates = {
            field: value for field, value in updates.items() if value is not None
        }
        _update_fields_if_changed("Clearing Charges", name, parent_updates)
        if primary_row and inv_status is not None and inv_name:
            inv_posting_date = frappe.db.get_value(
                "Sales Invoice", inv_name, "posting_date"
            )
            child_updates = {
                "invoice_status": inv_status,
                "reference_date": inv_posting_date,
            }
            _update_fields_if_changed(primary_row.doctype, primary_row.name, child_updates)

    _propagate_status_to_clearing_file_name(cc.clearing_file, new_status)
    return {"status": new_status, "invoice_status": inv_status, "totals": totals}


@frappe.whitelist()
def make_payment_entry_for_clearing_file(clearing_file: str):
    if not clearing_file:
        frappe.throw(_("Clearing File is required"))

    je_names = frappe.get_all(
        "Journal Entry",
        filters={"clearing_file": clearing_file, "docstatus": 1},
        pluck="name",
    )
    if not je_names:
        frappe.throw(_("No submitted Journal Entries found for this Clearing File"))

    cf = frappe.get_doc("Clearing File", clearing_file)
    company = cf.company or frappe.defaults.get_user_default("Company")
    if not cf.customer:
        frappe.throw(
            _("Customer is not set on Clearing File {0}").format(clearing_file)
        )

    from erpnext.accounts.doctype.payment_entry.payment_entry import (
        get_party_details,
        get_reference_details,
    )
    from clearing.api.utils import (
        get_clearing_receivable_account,
        get_cash_or_bank_account,
    )

    party_type, party = "Customer", cf.customer
    payment_type = "Receive"
    party_account = get_clearing_receivable_account(company)
    if not party_account:
        frappe.throw(_("Please configure a Receivable Account in Clearing Settings"))
    bank_account = get_cash_or_bank_account(company)

    pe = frappe.new_doc("Payment Entry")
    pe.update(
        {
            "payment_type": payment_type,
            "company": company,
            "posting_date": frappe.utils.nowdate(),
            "party_type": party_type,
            "party": party,
            "paid_from": party_account,
            "paid_from_account_currency": frappe.get_cached_value(
                "Account", party_account, "account_currency"
            ),
            "paid_to": bank_account,
            "paid_to_account_currency": frappe.get_cached_value(
                "Account", bank_account, "account_currency"
            ),
        }
    )

    party_details = get_party_details(
        company=company, party_type=party_type, party=party, date=pe.posting_date
    )
    if party_details:
        pe.party_balance = party_details.get("party_balance")
        pe.party_name = party_details.get("party_name")

    total_allocate = 0.0
    party_account_currency = pe.paid_from_account_currency
    for je_name in je_names:
        ref = get_reference_details(
            reference_doctype="Journal Entry",
            reference_name=je_name,
            party_account_currency=party_account_currency,
            party_type=party_type,
            party=party,
        )
        if not ref:
            continue
        outstanding = flt(ref.get("outstanding_amount", 0))
        if outstanding <= 0:
            continue
        pe.append(
            "references",
            {
                "reference_doctype": "Journal Entry",
                "reference_name": je_name,
                "due_date": None,
                "total_amount": ref.get("total_amount") or outstanding,
                "outstanding_amount": outstanding,
                "allocated_amount": outstanding,
            },
        )
        total_allocate += outstanding

    if total_allocate <= 0:
        frappe.throw(
            _("No outstanding amounts found in the Clearing File’s Journal Entries")
        )

    pe.paid_amount = pe.received_amount = total_allocate
    pe.flags.ignore_get_outstanding = True
    pe.flags.ignore_validate_update_after_submit = True
    return pe


def handle_invoice_status_change(invoice, event=None):
    if not invoice:
        return
    if isinstance(invoice, str):
        invoice = frappe.get_doc("Sales Invoice", invoice)

    cc_names = frappe.get_all(
        "Clearing Services",
        filters={"reference_number": invoice.name},
        pluck="parent",
        distinct=True,
    )
    if not cc_names:
        return

    current_status = invoice.status
    for cc_name in cc_names:
        cc = frappe.get_doc("Clearing Charges", cc_name)
        cc.ensure_primary_service_row(create=True, populate_from_legacy=True)
        totals = get_payment_progress_for_clearing_file(cc.clearing_file, invoice.name)
        new_status = cc._compute_status_from_invoice_and_reimbursements(
            current_status, totals
        )
        _update_fields_if_changed("Clearing Charges", cc_name, {"status": new_status})
        service_names = frappe.db.get_all(
            "Clearing Services",
            filters={"parent": cc_name, "reference_number": invoice.name},
            pluck="name",
        )
        child_updates = {
            "invoice_status": current_status,
            "reference_date": invoice.posting_date,
        }
        for service_name in service_names:
            _update_fields_if_changed("Clearing Services", service_name, child_updates)
        _propagate_status_to_clearing_file_name(cc.clearing_file, new_status)

    if not invoice.clearing_charges and cc_names:
        _update_fields_if_changed(
            "Sales Invoice", invoice.name, {"clearing_charges": cc_names[0]}
        )


def _propagate_status_to_clearing_file_name(cf_name: str, status: str):
    if not cf_name:
        return
    try:
        cf = frappe.get_doc("Clearing File", cf_name)
        target_status = _get_target_clearing_file_status(status, cf.docstatus)
        _update_fields_if_changed("Clearing File", cf.name, {"status": target_status})
    except Exception:
        pass


def _update_cc_for_clearing_file(cf_name: str):
    if not cf_name:
        return
    cc_names = frappe.get_all(
        "Clearing Charges", filters={"clearing_file": cf_name}, pluck="name"
    )
    for cc_name in cc_names:
        cc = frappe.get_doc("Clearing Charges", cc_name)
        cc.ensure_primary_service_row(create=True, populate_from_legacy=True)
        primary_invoice = cc.get_primary_invoice_number()
        inv_status = (
            frappe.db.get_value("Sales Invoice", primary_invoice, "status")
            if primary_invoice
            else None
        )
        totals = get_payment_progress_for_clearing_file(cf_name, primary_invoice)
        new_status = cc._compute_status_from_invoice_and_reimbursements(
            inv_status, totals
        )
        _update_fields_if_changed("Clearing Charges", cc_name, {"status": new_status})
        if primary_invoice and inv_status is not None:
            inv_posting_date = frappe.db.get_value(
                "Sales Invoice", primary_invoice, "posting_date"
            )
            service_names = frappe.db.get_all(
                "Clearing Services",
                filters={"parent": cc_name, "reference_number": primary_invoice},
                pluck="name",
            )
            child_updates = {
                "invoice_status": inv_status,
                "reference_date": inv_posting_date,
            }
            for service_name in service_names:
                _update_fields_if_changed("Clearing Services", service_name, child_updates)
        _propagate_status_to_clearing_file_name(cf_name, new_status)


def handle_payment_entry_status_change(payment_entry, event=None):
    if not payment_entry:
        return
    try:
        if isinstance(payment_entry, str):
            payment_entry = frappe.get_doc("Payment Entry", payment_entry)
    except Exception:
        return

    # Update via Sales Invoice refs
    si_names = frappe.get_all(
        "Payment Entry Reference",
        filters={"parent": payment_entry.name, "reference_doctype": "Sales Invoice"},
        pluck="reference_name",
    )
    for si in si_names:
        handle_invoice_status_change(si)

    # Update via JE refs
    je_names = frappe.get_all(
        "Payment Entry Reference",
        filters={"parent": payment_entry.name, "reference_doctype": "Journal Entry"},
        pluck="reference_name",
    )
    if je_names:
        cf_data = frappe.get_all(
            "Journal Entry",
            filters={"name": ["in", je_names]},
            fields=["clearing_file"],
            distinct=True,
        )
        for row in cf_data:
            if row.clearing_file:
                _update_cc_for_clearing_file(row.clearing_file)


def clamp_payment_entry_references(payment_entry, method=None):
    if not payment_entry:
        return
    try:
        if isinstance(payment_entry, str):
            payment_entry = frappe.get_doc("Payment Entry", payment_entry)
    except Exception:
        return

    marker_text = payment_entry.custom_remarks or payment_entry.remarks
    if not marker_text:
        return
    m = re.search(r"\[CFJE:([^\]]+)\]", str(marker_text))
    if not m:
        return
    je_target = m.group(1).strip()
    if not je_target:
        return

    try:
        frappe.get_doc("Journal Entry", je_target)
    except Exception:
        return

    refs = payment_entry.references or []
    keep_rows = [
        r
        for r in refs
        if r.reference_doctype == "Journal Entry" and r.reference_name == je_target
    ]

    from erpnext.accounts.doctype.payment_entry.payment_entry import (
        get_reference_details,
    )

    party_type = payment_entry.party_type
    party = payment_entry.party
    party_account_currency = (
        payment_entry.paid_from_account_currency
        if payment_entry.payment_type == "Receive"
        else payment_entry.paid_to_account_currency
    )

    if not keep_rows:
        total_amount = outstanding = 0.0
        if party_type and party and party_account_currency:
            ref = get_reference_details(
                reference_doctype="Journal Entry",
                reference_name=je_target,
                party_account_currency=party_account_currency,
                party_type=party_type,
                party=party,
            )
            if ref:
                total_amount = flt(ref.get("total_amount", 0))
                outstanding = flt(ref.get("outstanding_amount", 0))
        allocated = outstanding or flt(
            getattr(payment_entry, "received_amount", 0)
            or getattr(payment_entry, "paid_amount", 0)
        )
        payment_entry.set("references", [])
        row = payment_entry.append("references", {})
        row.reference_doctype = "Journal Entry"
        row.reference_name = je_target
        row.total_amount = total_amount
        row.outstanding_amount = outstanding
        row.allocated_amount = allocated
        if payment_entry.payment_type == "Receive":
            payment_entry.paid_amount = payment_entry.received_amount = allocated
        else:
            payment_entry.received_amount = payment_entry.paid_amount = allocated
        return

    # Keep only first matching ref
    keep = keep_rows[0]
    payment_entry.set("references", [])
    nr = payment_entry.append("references", {})
    for k in (
        "reference_doctype",
        "reference_name",
        "due_date",
        "total_amount",
        "outstanding_amount",
        "allocated_amount",
    ):
        if k in keep:
            nr.set(k, keep[k])
    alloc = flt(keep.allocated_amount or 0)
    if payment_entry.payment_type == "Receive":
        payment_entry.paid_amount = payment_entry.received_amount = alloc
    else:
        payment_entry.received_amount = payment_entry.paid_amount = alloc
