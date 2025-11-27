from typing import Optional, Sequence, Union

import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import flt
from clearing.clearing.doctype.port_clearance.port_clearance import ensure_all_documents_attached
from clearing.api.journal_entry import (
    create_child_table_journal_entries,
    normalize_child_row_selection,
)
from erpnext import get_company_currency


class TRAClearance(Document):
    def before_save(self):  
        """Before saving the document, check if invoice is paid and update the status."""
        self.set_currency()
        self._set_child_currencies()
        self.set_total_charges()
        self.set_paid_by_total()
        self.set_total_paid()

        if self.invoice_paid:
            # If the invoice is paid, automatically set the status to 'Payment Completed'
            self.status = "Payment Completed"
        else:
            # Reset the status if invoice is not paid (you can customize this logic)
            self.status = "Payment Pending"

    def set_total_charges(self):
        """Aggregate child table amounts into the parent total."""
        total = sum((row.amount or 0) for row in self.get("tra_charges", []))
        self.total_charges = flt(total, self.precision("total_charges"))

    def set_paid_by_total(self):
        """Keep the paid-by field in sync with child charge rows."""
        total = sum((row.amount or 0) for row in self.get("charge", []))
        self.paid_by = flt(total, self.precision("paid_by"))

    def set_total_paid(self):
        """Compute total paid by summing total charges and paid-by."""
        total = (self.total_charges or 0) + (self.paid_by or 0)
        self.total_paid = flt(total, self.precision("total_paid"))

        
    def before_submit(self):
        # Ensure all required documents are attached before submission
        ensure_all_documents_attached(self, "tra_clearance_document")
        
        # Validate that the invoice is paid and status is set correctly
        self.validate_payment_status()
    
    def validate_payment_status(self):
        """Ensure payment status is marked as 'Payment Completed' before submission."""
        if self.status != "Payment Completed":
            frappe.throw(_("You cannot Complete TRA Clearance unless the Payment Completed."))

    def on_update(self):
        """After saving TRA Clearance, move Clearing File to 'On Process' if it is 'Pre-Lodged'."""
        if not self.clearing_file:
            return
        cf_status = frappe.db.get_value("Clearing File", self.clearing_file, "status")
        if cf_status == "Pre-Lodged":
            frappe.db.set_value("Clearing File", self.clearing_file, "status", "On Process")

    def set_currency(self):
        """Sync currency with Clearing File / company currency."""
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

    def _set_child_currencies(self):
        """Default child table currency to parent currency when empty."""
        if not self.currency:
            self.set_currency()

        for table_field in ("tra_charges", "charge"):
            for row in self.get(table_field, []):
                if hasattr(row, "currency") and row.currency != getattr(self, "currency", None):
                    row.currency = self.currency


@frappe.whitelist()
def make_journal_entries(
    name: str,
    charges: Union[str, Sequence[str], None] = None,
    posting_date: Optional[str] = None,
):
    if not name:
        frappe.throw(_("TRA Clearance is required."))

    doc = frappe.get_doc("TRA Clearance", name)
    selected = normalize_child_row_selection(charges)
    if not selected:
        frappe.throw(_("Please select at least one charge."))

    return create_child_table_journal_entries(
        doc,
        table_field="tra_charges",
        selected_names=selected,
        posting_date=posting_date,
        label_field="item",
        journal_field="journal_entry",
        disbursed_date_field="disbursed_date",
    )
