# Copyright (c) 2024, Nelson Mpanju and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from clearing.clearing.doctype.port_clearance.port_clearance import ensure_all_documents_attached

class ShippingLineClearance(Document):
    def validate(self):
        # Prevent creation if Mode of Transport is Air
        if frappe.db.get_value("Clearing File", self.clearing_file, "mode_of_transport") == "Air":
            frappe.throw(
                _("Shipping Line Clearance cannot be created for Air transport"),
                title=_("Invalid Mode of Transport")
            )

        # Enforce process order: require TRA Clearance to exist first
        if self.clearing_file and not frappe.db.exists(
            "TRA Clearance", {"clearing_file": self.clearing_file}
        ):
            frappe.throw(
                _(
                    "Create a TRA Clearance for this Clearing File before proceeding to Shipping Line Clearance."
                ),
                title=_("Order Enforcement")
            )

    def before_save(self):
        """Before saving the document, check if invoice is paid and update the status."""
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

    def on_update(self):
        """After saving Shipping Line Clearance, move Clearing File to 'On Process' if it is 'Pre-Lodged'."""
        if not self.clearing_file:
            return
        cf_status = frappe.db.get_value("Clearing File", self.clearing_file, "status")
        if cf_status == "Pre-Lodged":
            frappe.db.set_value("Clearing File", self.clearing_file, "status", "On Process")
