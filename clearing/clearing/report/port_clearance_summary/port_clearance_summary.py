import frappe
from frappe.query_builder import DocType, Order


def execute(filters=None):
    filters = filters or {}

    PortClearance = DocType("Port Clearance")
    ClearingFile = DocType("Clearing File")
    Cargo = DocType("Cargo")

    query = (
        frappe.qb.from_(PortClearance)
        .left_join(ClearingFile)
        .on(ClearingFile.name == PortClearance.clearing_file)
        .left_join(Cargo)
        .on(Cargo.parent == ClearingFile.name)
        .select(
            PortClearance.name.as_("port_file"),
            PortClearance.consignee.as_("consignee"),
            ClearingFile.tancis_lodging_date.as_("tancis_date"),
            ClearingFile.awbbl_no.as_("awbbl_no"),
            ClearingFile.name.as_("clearing_file"),
            ClearingFile.cargo_location.as_("icd"),
            ClearingFile.declaration_type.as_("entry_type"),
            Cargo.package_type.as_("package_type"),
            PortClearance.total_charges.as_("charges"),
            PortClearance.paid_by_clearing_agent.as_("paid_on_behalf"),
            PortClearance.invoice_paid.as_("duties_paid"),
            PortClearance.status.as_("status"),
        )
        .where(PortClearance.docstatus < 2)
        .orderby(PortClearance.creation, order=Order.desc)
    )

    # Apply filters
    if filters.get("from_date") and filters.get("to_date"):
        query = query.where(
            (ClearingFile.tancis_lodging_date >= filters["from_date"])
            & (ClearingFile.tancis_lodging_date <= filters["to_date"])
        )

    if filters.get("consignee"):
        query = query.where(PortClearance.consignee == filters["consignee"])

    if filters.get("status"):
        query = query.where(PortClearance.status == filters["status"])

    if filters.get("clearing_file"):
        query = query.where(ClearingFile.name == filters["clearing_file"])

    data = query.run(as_dict=True)

    columns = [
        {
            "label": "Port File",
            "fieldname": "port_file",
            "fieldtype": "Link",
            "options": "Port Clearance",
            "width": 130,
        },
        {
            "label": "Consignee",
            "fieldname": "consignee",
            "fieldtype": "Link",
            "options": "Customer",
            "width": 200,
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
            "label": "Clearing File",
            "fieldname": "clearing_file",
            "fieldtype": "Link",
            "options": "Clearing File",
            "width": 150,
        },
        {
            "label": "ICD",
            "fieldname": "icd",
            "fieldtype": "Link",
            "options": "Container Location",
            "width": 120,
        },
        {
            "label": "Entry Type",
            "fieldname": "entry_type",
            "fieldtype": "Select",
            "width": 150,
        },
        {
            "label": "Package Type",
            "fieldname": "package_type",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": "Charges",
            "fieldname": "charges",
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
    ]

    return columns, data
