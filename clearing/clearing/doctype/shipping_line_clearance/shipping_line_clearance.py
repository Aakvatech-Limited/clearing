# Copyright (c) 2024, Nelson Mpanju and contributors
# For license information, please see license.txt

import re
from typing import Optional, Sequence, Union

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, flt, cint
from clearing.clearing.doctype.port_clearance.port_clearance import ensure_all_documents_attached
from clearing.api.journal_entry import (
    create_child_table_journal_entries,
    normalize_child_row_selection,
)
from erpnext import get_company_currency

class ShippingLineClearance(Document):
    def validate(self):
        # Prevent creation if Mode of Transport is Air
        if frappe.db.get_value("Clearing File", self.clearing_file, "mode_of_transport") == "Air":
            frappe.throw(
                _("Shipping Line Clearance cannot be created for Air transport"),
                title=_("Invalid Mode of Transport")
            )

    def before_save(self):
        """Before saving the document, check if invoice is paid and update the status."""
        self.set_currency()
        self._set_child_currencies()
        self._update_container_info()
        self.set_total_charges()
        self.set_paid_by_total()
        self.set_total_paid()

        if self.invoice_paid:
            # If the invoice is paid, automatically set the status to 'Payment Completed'
            self.status = "Payment Completed"
        else:
            # Reset the status if invoice is not paid
            self.status = "Payment Pending"

        # Check if Delivery Order is attached and validate the Delivery Order Expire Date
        self.check_delivery_order()

    def before_submit(self):
        """Ensure that all required documents are attached and invoice is paid before submission."""
        # This function will check all required documents
        ensure_all_documents_attached(self, "Shipment_clearance_document")

        # Validate payment status before submission
        self.validate_payment_status()
        self.ensure_invoice_received()

    def validate_payment_status(self):
        """Ensure payment status is 'Payment Completed' before submission."""
        if self.status != "Payment Completed":
            frappe.throw(_("You cannot complete Shipment Clearance unless the payment status is 'Payment Completed'."))

    def check_delivery_order(self):
        """Check if Delivery Order is attached and make sure Delivery Order Expire Date is set."""
        for row in self.document:
            if row.document_name == "Delivery Order":
                if not self.delivery_order_expire_date:
                    frappe.throw(_("Please set the Delivery Order Expire Date before saving."))

    def ensure_invoice_received(self):
        if not cint(self.invoice_received):
            frappe.throw(_("Invoice Received must be checked before submitting Shipping Line Clearance."))

    def set_total_charges(self):
        """Aggregate child table amounts into the parent total."""
        total = sum((row.amount or 0) for row in self.get("shipping_charges", []))
        self.total_charges = flt(total, self.precision("total_charges"))

    def set_paid_by_total(self):
        """Keep the paid-by field in sync with child charge rows."""
        total = sum((row.amount or 0) for row in self.get("charge", []))
        self.paid_by = flt(total, self.precision("paid_by"))

    def set_total_paid(self):
        """Compute total paid by summing total charges and paid-by."""
        total = (self.total_charges or 0) + (self.paid_by or 0)
        self.total_paid = flt(total, self.precision("total_paid"))

    def on_update(self):
        """After saving Shipping Line Clearance, move Clearing File to 'On Process' if it is 'Pre-Lodged'."""
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

        for table_field in ("shipping_charges", "charge"):
            for row in self.get(table_field, []):
                if hasattr(row, "currency") and row.currency != getattr(self, "currency", None):
                    row.currency = self.currency

    def _update_container_info(self):
        """Populate container-related fields from the linked Clearing File cargo details."""
        if not self.clearing_file:
            return

        data = get_cargo_container_data(self.clearing_file)
        if data.get("container_no") is not None:
            self.container_no = data.get("container_no")
        if data.get("port_of_loading") is not None:
            self.port_of_loading = data.get("port_of_loading")
        if data.get("port_of_discharge") is not None:
            self.port_of_discharge = data.get("port_of_discharge")


@frappe.whitelist()
def get_cargo_container_data(clearing_file: str | None):
    """Return aggregated container numbers, ports, and basic cargo attributes for a Clearing File."""
    if not clearing_file:
        return {}

    cargo_rows = frappe.get_all(
        "Cargo",
        filters={
            "parent": clearing_file,
            "parenttype": "Clearing File",
            "parentfield": "cargo_details",
        },
        fields=["container_number", "port_of_loading", "port_of_discharge", "package_type", "weight", "volume"],
        order_by="idx asc",
    )

    container_numbers = []
    ports = []
    discharge_ports = []

    package_types = []
    weights = []
    volumes = []

    for row in cargo_rows:
        raw_container = cstr(row.get("container_number")).strip()
        if raw_container:
            container_numbers.extend([
                code
                for code in (
                    segment.strip() for segment in re.split(r"[\s,;]+", raw_container)
                )
                if code
            ])

        raw_port = cstr(row.get("port_of_loading")).strip()
        if raw_port:
            ports.append(raw_port)

        raw_discharge_port = cstr(row.get("port_of_discharge")).strip()
        if raw_discharge_port:
            discharge_ports.append(raw_discharge_port)

        raw_pkg = cstr(row.get("package_type")).strip()
        if raw_pkg:
            package_types.append(raw_pkg)

        weights.append(flt(row.get("weight") or 0))
        volumes.append(flt(row.get("volume") or 0))

    container_numbers = _dedupe_preserve_order(container_numbers)
    ports = _dedupe_preserve_order(ports)
    discharge_ports = _dedupe_preserve_order(discharge_ports)

    package_types = _dedupe_preserve_order([p for p in package_types if p])
    total_weight = sum(weights) if weights else 0
    total_volume = sum(volumes) if volumes else 0

    return {
        "container_no": ", ".join(container_numbers),
        "port_of_loading": ", ".join(ports),
        "port_of_discharge": ", ".join(discharge_ports),
        "package_type": ", ".join(package_types),
        "weight": total_weight,
        "volume": total_volume,
    }


def _dedupe_preserve_order(items):
    seen = set()
    ordered = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


@frappe.whitelist()
def make_journal_entries(
    name: str,
    charges: Union[str, Sequence[str], None] = None,
    posting_date: Optional[str] = None,
):
    if not name:
        frappe.throw(_("Shipping Line Clearance is required."))

    doc = frappe.get_doc("Shipping Line Clearance", name)
    selected = normalize_child_row_selection(charges)
    if not selected:
        frappe.throw(_("Please select at least one charge."))

    return create_child_table_journal_entries(
        doc,
        table_field="shipping_charges",
        selected_names=selected,
        posting_date=posting_date,
        label_field="item",
        journal_field="journal_entry",
        disbursed_date_field="disbursed_date",
    )
