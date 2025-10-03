import frappe
from frappe.query_builder import DocType, Order


def execute(filters=None):
    filters = filters or {}

    TRAClearance = DocType("TRA Clearance")
    ClearingFile = DocType("Clearing File")
    Cargo = DocType("Cargo")

    query = (
        frappe.qb.from_(TRAClearance)
        .left_join(ClearingFile)
        .on(ClearingFile.name == TRAClearance.clearing_file)
        .left_join(Cargo)
        .on(Cargo.parent == ClearingFile.name)
        .select(
            TRAClearance.name.as_("tra_clearance"),
            ClearingFile.name.as_("clearing_file"),
            TRAClearance.posting_date.as_("date"),
            TRAClearance.customer.as_("consignee"),
            ClearingFile.tancis_lodging_date.as_("tancis_date"),
            ClearingFile.awbbl_no.as_("awbbl_no"),
            ClearingFile.declaration_type.as_("declaration_type"),
            Cargo.cargo_description.as_("cargo_description"),
            TRAClearance.total_charges.as_("tra_charges"),
            TRAClearance.paid_by_clearing_agent.as_("paid_on_behalf"),
            TRAClearance.invoice_paid.as_("duties_paid"),
            TRAClearance.status.as_("status"),
            TRAClearance.notes.as_("notes"),
        )
        .where(TRAClearance.docstatus < 2)
        .orderby(TRAClearance.posting_date, order=Order.desc)
    )

    # Apply filters
    if filters.get("from_date") and filters.get("to_date"):
        query = query.where(
            (TRAClearance.posting_date >= filters["from_date"])
            & (TRAClearance.posting_date <= filters["to_date"])
        )

    if filters.get("consignee"):
        query = query.where(TRAClearance.customer == filters["consignee"])

    if filters.get("status"):
        query = query.where(TRAClearance.status == filters["status"])

    if filters.get("clearing_file"):
        query = query.where(ClearingFile.name == filters["clearing_file"])

    if filters.get("declaration_type"):
        query = query.where(ClearingFile.declaration_type == filters["declaration_type"])

    data = query.run(as_dict=True)

    columns = [
        {
            "label": "TRA Clearance",
            "fieldname": "tra_clearance",
            "fieldtype": "Link",
            "options": "TRA Clearance",
            "width": 150,
        },
        {"label": "Date", "fieldname": "date", "fieldtype": "Date", "width": 110},
        {
            "label": "Clearing File",
            "fieldname": "clearing_file",
            "fieldtype": "Link",
            "options": "Clearing File",
            "width": 150,
            "hidden": 1,
        },
        {
            "label": "Consignee",
            "fieldname": "consignee",
            "fieldtype": "Link",
            "options": "Customer",
            "width": 250,
        },
        {
            "label": "TANCIS Date",
            "fieldname": "tancis_date",
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "label": "AWB/BL No",
            "fieldname": "awbbl_no",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": "Entry Type",
            "fieldname": "declaration_type",
            "fieldtype": "Select",
            "width": 150,
            "hidden": 1,
        },
        {
            "label": "Cargo Description",
            "fieldname": "cargo_description",
            "fieldtype": "Data",
            "width": 250,
        },
        {
            "label": "TRA Charges",
            "fieldname": "tra_charges",
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "label": "Paid on Behalf",
            "fieldname": "paid_on_behalf",
            "fieldtype": "Check",
            "width": 100,
        },
        {
            "label": "Duties Paid",
            "fieldname": "duties_paid",
            "fieldtype": "Check",
            "width": 100,
        },
        {"label": "Status", "fieldname": "status", "fieldtype": "Select", "width": 150},
        {"label": "Notes", "fieldname": "notes", "fieldtype": "Text", "width": 150},
    ]

    return columns, data
