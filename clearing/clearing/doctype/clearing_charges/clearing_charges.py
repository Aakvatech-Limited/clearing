import numbers
import re
from typing import Dict, List, Optional, Sequence, Tuple, Union

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder import DocType
from frappe.utils import cint, flt, now, nowdate
from clearing.api.journal_entry import (
    get_disbursement_journal_entry_defaults as _get_disbursement_journal_entry_defaults,
    normalize_child_row_selection,
)
from clearing.api.utils import (
    get_cash_or_bank_account,
    get_clearing_receivable_account,
    get_expense_account,
)
from erpnext import get_company_currency

CLEARANCE_SOURCE_NAMES = {
    "TRA Clearance",
    "Port Clearance",
    "Shipping Line Clearance",
    "Physical Verification",
}


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


def _get_target_clearing_file_status(
    payment_status: Optional[str], docstatus: int, current_status: Optional[str]
) -> str:
    status = (payment_status or "").strip()
    current_status = (current_status or "").strip()

    payment_tracking_statuses = {
        "Delivered",
        "Charges Pending",
        "Payment Received",
        "Closed",
    }

    if current_status not in payment_tracking_statuses:
        return current_status or "Draft"

    if status == "Paid":
        return "Payment Received"
    if status == "Partially Paid":
        return "Charges Pending"
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
    def before_submit(self):
        if (self.status or "").strip() != "Paid":
            frappe.throw(
                _("You can only submit Clearing Charges when Payment Status is Paid.")
            )

    def before_save(self):
        self.set_currency()
        self.ensure_primary_service_row(create=True, populate_from_legacy=True)
        if self._should_prompt_for_invoice():
            frappe.msgprint(_("Please generate invoice before printing Debit Note"))
        self.sync_payment_status_from_invoice()
        self.fetch_total_charges()
        self.populate_disbursement_and_reimbursement_tables()
        self._compute_reimbursement_totals()

    def set_currency(self):
        """Keep currency in sync with the linked Clearing File / company."""
        if not self.clearing_file:
            return

        currency, company = frappe.db.get_value(
            "Clearing File", self.clearing_file, ["currency", "company"]
        ) or (None, None)

        if not currency and company:
            currency = get_company_currency(company)

        current_currency = getattr(self, "currency", None)
        if currency and current_currency != currency:
            self.currency = currency

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

        return None

    def _detach_invoice(self, invoice_name: Optional[str]):
        if not invoice_name:
            return

        for charge in getattr(self, "charges", []) or []:
            if getattr(charge, "invoice_reference", None) == invoice_name:
                charge.invoice_reference = None

        if getattr(self, "clearing_services", None):
            remaining_services = [
                row
                for row in self.clearing_services
                if getattr(row, "reference_number", None) != invoice_name
            ]
            if len(remaining_services) != len(self.clearing_services):
                self.set("clearing_services", remaining_services)

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
            "invoice": 0.0,
        }

        manual_total = 0.0
        non_invoice_total = 0.0

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
            elif not cint(getattr(charge, "is_invoice", 0)):
                manual_total += amount

            if not cint(getattr(charge, "is_invoice", 0)):
                non_invoice_total += amount

            if cint(getattr(charge, "is_invoice", 0)):
                totals["invoice"] += amount

        debit_note_total = (
            non_invoice_total
        )
        invoice_total = totals["invoice"]

        services_total = 0.0
        services_outstanding_total = 0.0
        for row in getattr(self, "clearing_services", []) or []:
            services_total += flt(getattr(row, "grand_total", 0))
            services_outstanding_total += flt(getattr(row, "outstanding_amount", 0))

        _set_numeric_if_changed(self, "tra_clearance_total", totals["tra"])
        _set_numeric_if_changed(self, "port_clearance_total", totals["port"])
        _set_numeric_if_changed(self, "shipment_clearance_total", totals["shipment"])
        _set_numeric_if_changed(self, "physical_clearance_total", totals["physical"])
        _set_numeric_if_changed(self, "total", debit_note_total)
        _set_numeric_if_changed(self, "transport_total", totals["transport"])
        _set_numeric_if_changed(self, "agency_fee", totals["agency_fee"])
        _set_numeric_if_changed(self, "total_debit", invoice_total)
        _set_numeric_if_changed(self, "total_sales_invoice", services_total)
        _set_numeric_if_changed(self, "outstanding_amount", services_outstanding_total)
        _set_numeric_if_changed(
            self, "total_clearing_charges", debit_note_total + services_total
        )
        _set_numeric_if_changed(
            self,
            "balance",
            services_outstanding_total + flt(getattr(self, "total_outstanding_amount", 0)),
        )

    def sync_payment_status_from_invoice(self):
        invoice_totals, any_invoice_submitted, has_invoice_rows = (
            self._gather_invoice_snapshot()
        )

        if not has_invoice_rows:
            totals = get_payment_progress_for_clearing_file(self.clearing_file)
            self.status = self._derive_status(
                invoice_totals, any_invoice_submitted, has_invoice_rows, totals
            )
            self._propagate_status_to_clearing_file()
            self.fetch_total_charges()
            return

        totals = get_payment_progress_for_clearing_file(self.clearing_file)
        self.status = self._derive_status(
            invoice_totals, any_invoice_submitted, has_invoice_rows, totals
        )
        self._propagate_status_to_clearing_file()
        self.fetch_total_charges()

    def populate_disbursement_and_reimbursement_tables(self) -> bool:
        modified = False
        if not self.clearing_file:
            modified |= self._sync_charge_disbursement_fields([])
            if self.reimbursement:
                self.reimbursement = []
                modified = True
            return modified

        # Populate disbursements
        je_list = frappe.get_all(
            "Journal Entry",
            filters={"clearing_file": self.clearing_file, "docstatus": ["<", 2]},
            fields=["name", "posting_date", "user_remark"],
            order_by="posting_date asc, name asc",
        )
        modified |= self._sync_charge_disbursement_fields(je_list)

        # Populate reimbursements (submitted PEs referencing submitted JEs)
        submitted_je_names = frappe.get_all(
            "Journal Entry",
            filters={"clearing_file": self.clearing_file, "docstatus": 1},
            pluck="name",
        )
        if not submitted_je_names:
            if self.reimbursement:
                self.reimbursement = []
                modified = True
            return modified

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

    def _sync_charge_disbursement_fields(self, journal_entries: List[Dict]) -> bool:
        charges = [
            row
            for row in (getattr(self, "charges", []) or [])
            if not cint(getattr(row, "is_invoice", 0))
        ]
        entries = list(journal_entries or [])
        if not charges:
            changed = False
            for row in (getattr(self, "charges", []) or []):
                if getattr(row, "disbursement", None) or getattr(row, "disbursed_date", None):
                    row.disbursement = None
                    row.disbursed_date = None
                    changed = True
            return changed

        charges.sort(key=lambda row: getattr(row, "idx", 0) or 0)
        changed = False
        buckets: Dict[str, List[Dict]] = {}
        unmatched: List[Dict] = []
        for entry in entries:
            entry_map = {
                "name": entry.get("name"),
                "posting_date": entry.get("posting_date"),
                "user_remark": entry.get("user_remark"),
            }
            inferred_type = self._extract_charge_type_from_remark(entry_map.get("user_remark"))
            if inferred_type:
                buckets.setdefault(inferred_type, []).append(entry_map)
            else:
                unmatched.append(entry_map)

        for row in charges:
            charge_type = getattr(row, "charge_type", None)
            entry = None
            if charge_type and buckets.get(charge_type):
                entry = buckets[charge_type].pop(0)
            elif unmatched:
                entry = unmatched.pop(0)

            new_je = entry.get("name") if entry else None
            new_date = entry.get("posting_date") if entry else None

            if (getattr(row, "disbursement", None) or None) != (new_je or None):
                row.disbursement = new_je
                changed = True

            if (getattr(row, "disbursed_date", None) or None) != (new_date or None):
                row.disbursed_date = new_date
                changed = True

        return changed

    @staticmethod
    def _extract_charge_type_from_remark(remark: Optional[str]) -> Optional[str]:
        if not remark:
            return None
        head = remark.split("|", 1)[0].strip()
        if not head:
            return None
        if ":" in head:
            head = head.split(":", 1)[0].strip()
        return head or None

    def _compute_status_from_invoice_and_reimbursements(
        self, invoice_status: str | None, totals: Dict | None
    ) -> str:
        invoice_totals, any_invoice_submitted, has_invoice_rows = (
            self._gather_invoice_snapshot()
        )

        totals = totals or get_payment_progress_for_clearing_file(self.clearing_file)
        return self._derive_status(
            invoice_totals, any_invoice_submitted, has_invoice_rows, totals
        )

    def _compute_reimbursement_totals(self):
        paid = 0.0
        for row in self.reimbursement:
            paid += flt(row.paid_amount or 0)

        totals = (
            get_payment_progress_for_clearing_file(self.clearing_file)
            if self.clearing_file
            else None
        )
        outstanding = flt((totals or {}).get("disb_outstanding", 0))

        self.total_paid_amount = paid
        self.total_outstanding_amount = outstanding

    def _gather_invoice_snapshot(self) -> Tuple[Dict[str, float], bool, bool]:
        invoice_totals = {"total": 0.0, "outstanding": 0.0, "paid": 0.0}
        any_invoice_submitted = False
        has_invoice_rows = False
        rows = getattr(self, "clearing_services", []) or []
        removal: List[str] = []

        for row in rows:
            invoice_name = getattr(row, "reference_number", None)
            if not invoice_name:
                continue
            has_invoice_rows = True
            inv = frappe.db.get_value(
                "Sales Invoice",
                invoice_name,
                [
                    "status",
                    "docstatus",
                    "posting_date",
                    "rounded_total",
                    "grand_total",
                    "base_rounded_total",
                    "base_grand_total",
                    "outstanding_amount",
                ],
                as_dict=True,
            )
            if not inv or inv.docstatus == 2:
                removal.append(invoice_name)
                continue

            grand_total = flt(
                inv.rounded_total
                or inv.grand_total
                or inv.base_rounded_total
                or inv.base_grand_total
                or 0
            )
            outstanding = flt(inv.outstanding_amount or 0)
            paid_amount = max(grand_total - outstanding, 0.0)

            invoice_totals["total"] += grand_total
            invoice_totals["outstanding"] += outstanding
            invoice_totals["paid"] += paid_amount

            if inv.docstatus == 1:
                any_invoice_submitted = True

            row.invoice_status = inv.status
            if inv.posting_date:
                row.reference_date = inv.posting_date
            _set_numeric_if_changed(row, "grand_total", grand_total)
            _set_numeric_if_changed(row, "outstanding_amount", outstanding)

            if self.name and not self.name.startswith("New "):
                linked = frappe.db.get_value(
                    "Sales Invoice", invoice_name, "clearing_charges"
                )
                if linked != self.name:
                    _update_fields_if_changed(
                        "Sales Invoice",
                        invoice_name,
                        {"clearing_charges": self.name},
                    )

        for invoice_name in removal:
            self._detach_invoice(invoice_name)

        return invoice_totals, any_invoice_submitted, has_invoice_rows

    def _derive_status(
        self,
        invoice_totals: Dict[str, float],
        any_invoice_submitted: bool,
        has_invoice_rows: bool,
        totals: Optional[Dict],
    ) -> str:
        invoice_outstanding = flt(invoice_totals.get("outstanding", 0))
        invoice_paid = flt(invoice_totals.get("paid", 0))
        invoice_total = flt(invoice_totals.get("total", 0))
        has_invoice_payments = invoice_paid > 0.000001

        disb_total = flt((totals or {}).get("disb_total", 0))
        disb_outstanding = flt((totals or {}).get("disb_outstanding", 0))
        disb_paid = flt((totals or {}).get("disb_paid", 0))
        has_disbursement_payments = disb_paid > 0.000001

        has_outstanding = (invoice_outstanding > 0) or (disb_outstanding > 0)
        has_any_payments = has_invoice_payments or has_disbursement_payments

        status = "Draft"

        if has_invoice_rows:
            if invoice_outstanding <= 0 and disb_outstanding <= 0 and (
                any_invoice_submitted or invoice_total > 0 or disb_total > 0
            ):
                status = "Paid"
            elif not any_invoice_submitted:
                if has_any_payments:
                    status = "Partially Paid" if has_outstanding else "Paid"
                else:
                    status = "Draft"
            else:
                if not has_any_payments:
                    status = "Pending Payment"
                elif has_outstanding:
                    status = "Partially Paid"
                else:
                    status = "Paid"
        else:
            if disb_outstanding <= 0:
                if disb_total > 0 or has_disbursement_payments:
                    status = "Paid"
                else:
                    status = "Draft"
            elif has_disbursement_payments:
                status = "Partially Paid"
            elif disb_total > 0:
                status = "Pending Payment"
            else:
                status = "Draft"

        return status

    def _propagate_status_to_clearing_file(self):
        if not self.clearing_file:
            return
        try:
            cf = frappe.get_doc("Clearing File", self.clearing_file)
            target_status = _get_target_clearing_file_status(
                self.status, cf.docstatus, cf.status
            )
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
        {
            "journal_entry": d.name,
            "posting_date": d.posting_date,
            "date": d.posting_date,
            "remark": d.user_remark,
            "charge_type": ClearingCharges._extract_charge_type_from_remark(d.user_remark),
        }
        for d in je_list
    ]


@frappe.whitelist()
def get_reimbursement_payments_for_journal_entries(clearing_file: str) -> Dict[str, object]:
    if not clearing_file:
        return {"rows": [], "je_outstanding_total": 0.0}

    # Get submitted JEs and precompute per-JE summaries
    submitted_je_names = frappe.get_all(
        "Journal Entry",
        filters={"clearing_file": clearing_file, "docstatus": 1},
        pluck="name",
    )
    if not submitted_je_names:
        return {"rows": [], "je_outstanding_total": 0.0}

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
    total_je_outstanding = flt(
        sum(summary["outstanding"] for summary in je_summaries.values())
    )

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
                "paid_amount": flt(info["paid"]),
                "outstanding_amount": flt(group_outstanding),
            }
        )
    return {"rows": data, "je_outstanding_total": total_je_outstanding}


@frappe.whitelist()
def get_disbursement_journal_entry_defaults(clearing_file: str) -> Dict[str, object]:
    return _get_disbursement_journal_entry_defaults(clearing_file)


@frappe.whitelist()
def make_disbursement_journal_entries(
    clearing_charges: str,
    charges: Union[str, Sequence[str], None] = None,
    posting_date: Optional[str] = None,
) -> List[Dict[str, str]]:
    if not clearing_charges:
        frappe.throw(_("Clearing Charges is required"))

    charges_list = normalize_child_row_selection(charges)
    if not charges_list:
        frappe.throw(_("Please select at least one charge."))

    doc = frappe.get_doc("Clearing Charges", clearing_charges)
    if doc.docstatus == 2:
        frappe.throw(_("Cannot create Journal Entries for a cancelled document."))

    if not doc.clearing_file:
        frappe.throw(_("Please set a Clearing File before creating a Journal Entry."))

    defaults = get_disbursement_journal_entry_defaults(doc.clearing_file)
    party_account = defaults.get("party_account")
    bank_account = defaults.get("bank_account")
    if not party_account or not bank_account:
        frappe.throw(_("Please configure the Receivable and Cash/Bank accounts in Clearing Settings."))

    posting_date = posting_date or nowdate()
    company = defaults.get("company")
    if not company:
        frappe.throw(_("Company is not set on Clearing File {0}").format(doc.clearing_file))
    voucher_type = defaults.get("voucher_type") or "Debit Note"
    party_type = defaults.get("party_type")
    party = defaults.get("party")
    party_account_currency = defaults.get("party_account_currency")
    bank_account_currency = defaults.get("bank_account_currency")

    selected = {name for name in charges_list if isinstance(name, str) and name.strip()}
    if not selected:
        frappe.throw(_("No valid charges were selected."))

    created: List[Dict[str, str]] = []
    require_save = doc.docstatus == 0

    for charge in doc.get("charges", []):
        if charge.name not in selected:
            continue

        if cint(getattr(charge, "is_invoice", 0)) == 1:
            continue

        if (getattr(charge, "charge_type", "") or "").strip() in CLEARANCE_SOURCE_NAMES:
            continue

        if getattr(charge, "disbursement", None):
            continue

        amount = flt(getattr(charge, "amount", 0))
        if amount <= 0:
            continue

        header_remark, account_remark = _build_disbursement_remarks(doc, charge)

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = voucher_type
        je.posting_date = posting_date
        je.clearing_file = doc.clearing_file
        if company:
            je.company = company
        if header_remark:
            je.user_remark = header_remark
            je.remark = header_remark

        reference_allowed = {
            "Sales Invoice",
            "Purchase Invoice",
            "Journal Entry",
            "Sales Order",
            "Purchase Order",
            "Expense Claim",
            "Asset",
            "Loan",
            "Payroll Entry",
            "Employee Advance",
            "Exchange Rate Revaluation",
            "Invoice Discounting",
            "Fees",
            "Full and Final Statement",
            "Payment Entry",
        }

        reference_type = doc.doctype if doc.doctype in reference_allowed else None

        debit_row = {
            "account": party_account,
            "debit_in_account_currency": amount,
            "credit_in_account_currency": 0,
        }
        if party_account_currency:
            debit_row["account_currency"] = party_account_currency
        if party_type:
            debit_row["party_type"] = party_type
        if party:
            debit_row["party"] = party
        if account_remark:
            debit_row["user_remark"] = account_remark
        if reference_type:
            debit_row["reference_type"] = reference_type
            debit_row["reference_name"] = doc.name

        credit_row = {
            "account": bank_account,
            "debit_in_account_currency": 0,
            "credit_in_account_currency": amount,
        }
        if bank_account_currency:
            credit_row["account_currency"] = bank_account_currency
        if account_remark:
            credit_row["user_remark"] = account_remark
        if reference_type:
            credit_row["reference_type"] = reference_type
            credit_row["reference_name"] = doc.name

        je.set("accounts", [])
        je.append("accounts", debit_row)
        je.append("accounts", credit_row)
        je.insert()
        je.submit()

        charge.disbursement = je.name
        charge.disbursed_date = posting_date
        if doc.docstatus == 0:
            require_save = True
        elif getattr(charge, "doctype", None) and getattr(charge, "name", None):
            frappe.db.set_value(
                charge.doctype,
                charge.name,
                {"disbursement": je.name, "disbursed_date": posting_date},
            )

        created.append({"charge": charge.name, "journal_entry": je.name})

    if require_save and created:
        doc.save(ignore_permissions=True)

    return created


def _build_disbursement_remarks(doc, charge) -> Tuple[str, str]:
    doc_label = getattr(doc, "doctype", "Clearing Charges")
    doc_name = (getattr(doc, "name", "") or "").strip()
    clearing_file = (getattr(doc, "clearing_file", "") or "").strip()
    charge_type = (getattr(charge, "charge_type", "") or "").strip()

    account_parts: List[str] = []
    if doc_name:
        account_parts.append(f"{doc_label}: {doc_name}")
    if clearing_file:
        account_parts.append(f"Clearing File {clearing_file}")
    account_remark = " | ".join(account_parts)

    header_parts: List[str] = []
    if charge_type:
        header_parts.append(charge_type)
    if account_remark:
        header_parts.append(account_remark)
    header_remark = " | ".join(header_parts)

    return header_remark, account_remark


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
        item_label, clearance_label, clearance_type = _describe_journal_entry_for_payment(je)
        _, _, outstanding = _summarise_party_payment_for_journal_entry(je)
        if outstanding > 0:
            results.append(
                {
                    "journal_entry": je.name,
                    "clearance_type": clearance_type,
                    "clearance_label": clearance_label,
                    "item_label": item_label,
                    "amount": totals["disb_total"],  # Aggregate; per-JE if needed
                    "outstanding": outstanding,
                    "date": je.posting_date,
                }
            )
    return results


def _describe_journal_entry_for_payment(je) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    remark = (getattr(je, "user_remark", "") or "").strip()
    if not remark:
        return None, None, None

    parts = [part.strip() for part in remark.split("|") if part.strip()]
    item_label = parts[0] if parts else None

    clearance_label = None
    for part in parts[1:]:
        if ":" in part:
            clearance_label = part
            break
    if not clearance_label and len(parts) > 1:
        clearance_label = parts[1]

    clearance_type = None
    target = clearance_label or item_label
    if target and ":" in target:
        clearance_type = target.split(":", 1)[0].strip()
    elif clearance_label:
        clearance_type = clearance_label

    return item_label, clearance_label, clearance_type


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
        reimbursement_payload = get_reimbursement_payments_for_journal_entries(
            cc.clearing_file
        )
        reimb_rows = reimbursement_payload.get("rows", [])
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

    party_type, party = "Customer", cf.customer
    payment_type = "Receive"
    party_account = get_clearing_receivable_account(company, currency=getattr(cf, "currency", None))
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
        target_status = _get_target_clearing_file_status(status, cf.docstatus, cf.status)
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
