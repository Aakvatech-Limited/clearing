# Copyright (c) 2024, Nelson Mpanju and contributors
# For license information, please see license.txt

from typing import Optional, Sequence, Union

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt
from clearing.api.journal_entry import (
    create_child_table_journal_entries,
    normalize_child_row_selection,
)
from erpnext import get_company_currency

class PortClearance(Document):
    def validate(self):
        # Enforce process order: require TRA Clearance first
        if self.clearing_file and not frappe.db.exists(
            "TRA Clearance", {"clearing_file": self.clearing_file}
        ):
            frappe.throw(
                _(
                    "Create a TRA Clearance for this Clearing File before proceeding to Port Clearance."
                )
            )
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
            # Reset the status if invoice is not paid
            self.status = "Payment Pending"


    def set_total_charges(self):
        """Aggregate child table amounts into the parent total."""
        total = sum((row.amount or 0) for row in self.get("port_charges", []))
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
        """Ensure all required documents are attached and verification is completed before submission."""
        # Ensure that payment is completed before submission
        if self.status != "Payment Completed":
            frappe.throw(_("You can't submit unless the payment status is 'Payment Completed'."))


        # Check if all required documents are attached
        ensure_all_documents_attached(self, "port_clearance_document")

    def on_update(self):
        """After saving Port Clearance, move Clearing File to 'On Process' if it is 'Pre-Lodged'."""
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

        for table_field in ("port_charges", "charge"):
            for row in self.get(table_field, []):
                if hasattr(row, "currency") and row.currency != getattr(self, "currency", None):
                    row.currency = self.currency

def ensure_all_documents_attached(self, type):
    """Ensure all required documents for the current mode of transport are attached."""
    # Fetch required documents for the given mode of transport
    required_docs = frappe.db.get_all(
        "Mode of Transport Detail",
        filters={
            "parentfield": type,
            'parent': frappe.db.get_value('Clearing File', self.clearing_file, 'mode_of_transport')
        },
        fields=['clearing_document_type']
    )

    # Convert list of dictionaries into a simple list of document names
    required_doc_names = [doc['clearing_document_type'] for doc in required_docs]

    # Check if each required document is present in the Clearing File's child table 'documents'
    missing_docs = []
    for doc_name in required_doc_names:
        exists = any(doc.document_name == doc_name for doc in self.document)
        if not exists:
            missing_docs.append(doc_name)

    # If documents are missing, prevent submission and show an error
    if missing_docs:
        missing_docs_str = ', '.join(missing_docs)
        frappe.throw(
            _('The following required documents are missing and must be attached before submission: {0}')
            .format(missing_docs_str), frappe.ValidationError
        )

@frappe.whitelist()
def make_journal_entries(
    name: str,
    charges: Union[str, Sequence[str], None] = None,
    posting_date: Optional[str] = None,
):
    if not name:
        frappe.throw(_("Port Clearance is required."))

    doc = frappe.get_doc("Port Clearance", name)
    selected = normalize_child_row_selection(charges)
    if not selected:
        frappe.throw(_("Please select at least one charge."))

    return create_child_table_journal_entries(
        doc,
        table_field="port_charges",
        selected_names=selected,
        posting_date=posting_date,
        label_field="item",
        journal_field="journal_entry",
        disbursed_date_field="disbursed_date",
    )
