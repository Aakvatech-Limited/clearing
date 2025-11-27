# Copyright (c) 2024, Nelson Mpanju and contributors
# For license information, please see license.txt

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

class PhysicalVerification(Document):
    def validate(self):
        # Enforce process order: require TRA Clearance first
        if self.clearing_file and not frappe.db.exists(
            "TRA Clearance", {"clearing_file": self.clearing_file}
        ):
            frappe.throw(
                _(
                    "Create a TRA Clearance for this Clearing File before proceeding to Physical Verification."
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

        # Check release order date and update verification status accordingly
        if self.release_order_date:
            self.verification_status = "Completed"
        else:
            self.verification_status = "Pending"

    def before_submit(self):
        """Ensure all required documents are attached and verification is completed before submission."""
        # Check if all required documents are attached
        ensure_all_documents_attached(self, "physical_verification_document")

        # Ensure verification is marked as completed
        if self.verification_status != "Completed":
            frappe.throw(_("You can't submit unless verification is completed."))


    def validate_status(self):
        """Ensure both payment and verification statuses are completed before submission."""
        if self.status != "Payment Completed":
            frappe.throw(_("You cannot complete Physical Verification unless the payment status is 'Payment Completed'."))

        if self.verification_status != "Completed":
            frappe.throw(_("You cannot complete Physical Verification unless the verification status is 'Completed'."))

    def set_total_charges(self):
        """Aggregate child table amounts into the parent total."""
        total = sum((row.amount or 0) for row in self.get("physical_charges", []))
        self.total_charges = flt(total, self.precision("total_charges"))

    def set_paid_by_total(self):
        """Keep the paid-by field in sync with child charge rows."""
        total = sum((row.amount or 0) for row in self.get("charge", []))
        self.paid_by = flt(total, self.precision("paid_by"))

    def set_total_paid(self):
        """Compute total paid by summing total charges and paid-by."""
        total = (self.total_charges or 0) + (self.paid_by or 0)
        self.total_paid = flt(total, self.precision("total_paid"))

    def before_update_after_submit(self):
        """Keep verification_location synced from Clearing File when submitted.

        - Always refresh `verification_location` from linked Clearing File's `cargo_location`.
        - Permit update-after-submit only when the change is limited to this field.
        """
        # Sync from source if available
        if self.clearing_file:
            cargo_loc = frappe.db.get_value("Clearing File", self.clearing_file, "cargo_location")
            if cargo_loc is not None:
                self.verification_location = cargo_loc

        # Only allow this field to change after submit
        allowed_fields = {"verification_location"}

        changed = []
        before = self.get_doc_before_save()
        if before:
            for df in self.meta.get("fields"):
                fn = getattr(df, "fieldname", None)
                if not fn:
                    continue
                # compare current vs previous
                if self.has_value_changed(fn):
                    changed.append(fn)

        if changed and set(changed).issubset(allowed_fields):
            self.flags.ignore_validate_update_after_submit = True

    def on_update_after_submit(self):
        # Placeholder for any post-save actions if needed later
        pass

    def on_update(self):
        """After saving Physical Verification, move Clearing File to 'On Process' if it is 'Pre-Lodged'."""
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

        for table_field in ("physical_charges", "charge"):
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
        frappe.throw(_("Physical Verification is required."))

    doc = frappe.get_doc("Physical Verification", name)
    selected = normalize_child_row_selection(charges)
    if not selected:
        frappe.throw(_("Please select at least one charge."))

    return create_child_table_journal_entries(
        doc,
        table_field="physical_charges",
        selected_names=selected,
        posting_date=posting_date,
        label_field="item",
        journal_field="journal_entry",
        disbursed_date_field="disbursed_date",
    )
