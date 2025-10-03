import frappe
from frappe.query_builder import DocType, Case, Order, functions as fn


def execute(filters=None):
    filters = filters or {}

    PhysicalVerification = DocType("Physical Verification")
    ClearingFile = DocType("Clearing File")
    Cargo = DocType("Cargo")

    # Base query
    query = (
        frappe.qb.from_(PhysicalVerification)
        .left_join(ClearingFile)
        .on(ClearingFile.name == PhysicalVerification.clearing_file)
        .left_join(Cargo)
        .on(Cargo.parent == ClearingFile.name)
        .select(
            PhysicalVerification.name.as_("physical_verification"),
            PhysicalVerification.posting_date.as_("date"),
            PhysicalVerification.consignee.as_("consignee"),
            PhysicalVerification.release_order_date.as_("release_order_date"),
            ClearingFile.name.as_("clearing_file"),
            ClearingFile.awbbl_no.as_("awbbl_no"),
            Cargo.cargo_description.as_("cargo_description"),
            fn.Concat(
                PhysicalVerification.staff_name,
                " | ",
                PhysicalVerification.verification_location,
            ).as_("staff_verification_location"),
            (
                Case()
                .when(PhysicalVerification.release_order_date.isnotnull(), "Completed")
                .else_("Pending")
            ).as_("verification_status"),
            PhysicalVerification.release_order_date.as_("ro_date"),
            PhysicalVerification.total_charges.as_("charges"),
            PhysicalVerification.status.as_("status"),
        )
        .orderby(PhysicalVerification.posting_date, order=Order.desc)
    )

    # Apply filters
    if filters.get("from_date") and filters.get("to_date"):
        query = query.where(
            (PhysicalVerification.posting_date >= filters["from_date"])
            & (PhysicalVerification.posting_date <= filters["to_date"])
        )

    if filters.get("consignee"):
        query = query.where(PhysicalVerification.consignee == filters["consignee"])

    if filters.get("verification_status"):
        if filters["verification_status"] == "Completed":
            query = query.where(PhysicalVerification.release_order_date.isnotnull())
        elif filters["verification_status"] == "Pending":
            query = query.where(PhysicalVerification.release_order_date.isnull())

    if filters.get("clearing_file"):
        query = query.where(ClearingFile.name == filters["clearing_file"])

    data = query.run(as_dict=True)

    # Columns
    columns = [
        {
            "label": "Physical Verification",
            "fieldname": "physical_verification",
            "fieldtype": "Link",
            "options": "Physical Verification",
            "width": 120,
        },
        {"label": "Date", "fieldname": "date", "fieldtype": "Date", "width": 120},
        {
            "label": "Consignee",
            "fieldname": "consignee",
            "fieldtype": "Link",
            "options": "Customer",
            "width": 250,
        },
        {
            "label": "Release Order Date",
            "fieldname": "release_order_date",
            "fieldtype": "Date",
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
            "label": "AWB/BL No",
            "fieldname": "awbbl_no",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": "Cargo Description",
            "fieldname": "cargo_description",
            "fieldtype": "Data",
            "width": 250,
        },
        {
            "label": "Staff & Verification Location",
            "fieldname": "staff_verification_location",
            "fieldtype": "Data",
            "width": 250,
        },
        {
            "label": "Verification Status",
            "fieldname": "verification_status",
            "fieldtype": "Select",
            "options": "\nCompleted\nPending",
            "width": 120,
        },
        {
            "label": "R.O Date",
            "fieldname": "ro_date",
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "label": "Charges",
            "fieldname": "charges",
            "fieldtype": "Currency",
            "width": 150,
        },
        {"label": "Status", "fieldname": "status", "fieldtype": "Select", "width": 150},
    ]

    return columns, data
