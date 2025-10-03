import frappe
from frappe.model.document import Document
from frappe import _


class ClearingCharges(Document):
    def before_save(self):
        if not self.reference_number:
            frappe.msgprint(_("Please generate invoice before printing Debit Note"))
        self.fetch_total_charges()
        self.sync_payment_status_from_invoice()

    def fetch_total_charges(self):
        tra_total = 0
        port_total = 0
        shipment_total = 0
        physical_total = 0
        transport_total = 0
        agency_fee_total = 0
        total_debit = 0

        for charge in self.charges:
            amount = float(charge.amount or 0)

            if charge.charge_type == "TRA Clearance":
                tra_total += amount
            elif charge.charge_type == "Port Clearance":
                port_total += amount
            elif charge.charge_type == "Shipping Line Clearance":
                shipment_total += amount
            elif charge.charge_type == "Physical Verification":
                physical_total += amount
            elif charge.charge_type == "Transport":
                transport_total += amount
            elif charge.charge_type == "Clearing Agency Fee":
                agency_fee_total += amount

            if charge.is_invoice:
                total_debit += amount

        self.tra_clearance_total = tra_total
        self.port_clearance_total = port_total
        self.shipment_clearance_total = shipment_total
        self.physical_clearance_total = physical_total
        self.total = tra_total + shipment_total + physical_total + port_total
        self.transport_total = transport_total
        self.agency_fee = agency_fee_total
        self.total_debit = total_debit
        self.total_clearing_charges = self.total + self.total_debit

    def sync_payment_status_from_invoice(self):
        """Align payment status with the linked Sales Invoice status."""
        if not self.reference_number:
            return

        invoice_status = frappe.db.get_value(
            "Sales Invoice", self.reference_number, "status"
        )
        if not invoice_status:
            return

        self.invoice_status = invoice_status
        target_status = map_invoice_status_to_payment_status(invoice_status)

        if target_status and self.status != target_status:
            self.status = target_status

        # Ensure the Sales Invoice keeps a back-reference to this document
        if self.name and not self.name.startswith("New "):
            linked_clearing = frappe.db.get_value(
                "Sales Invoice", self.reference_number, "clearing_charges"
            )
            if linked_clearing != self.name:
                frappe.db.set_value(
                    "Sales Invoice", self.reference_number, "clearing_charges", self.name
                )


def map_invoice_status_to_payment_status(invoice_status: str | None) -> str | None:
    status = (invoice_status or "").strip().lower()

    if status in {"unpaid", "overdue"}:
        return "Pending Payment"
    if status == "partially paid":
        return "Partially Paid"
    if status == "paid":
        return "Paid"
    if status == "cancelled":
        return "Clearing Charges Raised"

    return None


def handle_invoice_status_change(invoice, event=None):
    """Push Sales Invoice status changes down to linked Clearing Charges."""
    if not invoice:
        return

    if isinstance(invoice, str):
        invoice = frappe.get_doc("Sales Invoice", invoice)

    clearing_charge_names = frappe.get_all(
        "Clearing Charges",
        filters={"reference_number": invoice.name},
        pluck="name",
    )

    if not clearing_charge_names:
        return

    current_invoice_status = frappe.db.get_value(
        "Sales Invoice", invoice.name, "status"
    ) or invoice.status
    target_status = map_invoice_status_to_payment_status(current_invoice_status)

    update_values = {"invoice_status": current_invoice_status}
    if target_status:
        update_values["status"] = target_status

    for clearing_charge_name in clearing_charge_names:
        frappe.db.set_value("Clearing Charges", clearing_charge_name, update_values)

    # Backfill the link on the Sales Invoice if missing
    if (
        getattr(invoice, "clearing_charges", None) in (None, "")
        and clearing_charge_names
    ):
        frappe.db.set_value(
            "Sales Invoice", invoice.name, "clearing_charges", clearing_charge_names[0]
        )
