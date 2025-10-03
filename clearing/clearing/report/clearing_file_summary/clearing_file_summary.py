import frappe
from frappe.query_builder import DocType, Order


def execute(filters=None):
    filters = filters or {}

    ClearingFile = DocType("Clearing File")
    Cargo = DocType("Cargo")

    query = (
        frappe.qb.from_(ClearingFile)
        .left_join(Cargo)
        .on(Cargo.parent == ClearingFile.name)
        .select(
            ClearingFile.name.as_("file"),
            ClearingFile.posting_date.as_("date"),
            ClearingFile.customer.as_("consignee"),
            ClearingFile.mode_of_transport.as_("mode_of_transport"),
            ClearingFile.awbbl_no.as_("bl_awb_no"),
            ClearingFile.arrival_date.as_("eta"),
            ClearingFile.cargo_description.as_("cargo_description"),
            ClearingFile.cargo_country_of_origin.as_("origin"),
            ClearingFile.tancis_lodging_date.as_("tancis_date"),
            ClearingFile.declaration_type.as_("entry_type"),
            ClearingFile.cl_plan.as_("cl_plan"),
            Cargo.package_type.as_("cargo_type"),
            Cargo.quantity_of_container.as_("container_quantity"),
            Cargo.number_of_packages.as_("packages"),
            Cargo.value.as_("cif_value"),
            Cargo.currency.as_("currency"),
        )
        .orderby(ClearingFile.posting_date, order=Order.desc)
    )

    # Apply filters
    if filters.get("from_date") and filters.get("to_date"):
        query = query.where(
            (ClearingFile.posting_date >= filters["from_date"])
            & (ClearingFile.posting_date <= filters["to_date"])
        )

    if filters.get("status") and filters["status"] != "All":
        query = query.where(ClearingFile.status == filters["status"])

    if filters.get("customer"):
        query = query.where(ClearingFile.customer == filters["customer"])

    if filters.get("clearing_file"):
        query = query.where(ClearingFile.name == filters["clearing_file"])

    if filters.get("mode_of_transport"):
        query = query.where(
            ClearingFile.mode_of_transport == filters["mode_of_transport"]
        )

    if filters.get("declaration_type"):
        query = query.where(Cargo.package_type == filters["declaration_type"])

    if filters.get("cl_plan"):
        query = query.where(Cargo.package_type == filters["cl_plan"])

    data = query.run(as_dict=True)

    columns = [
        {
            "label": "File",
            "fieldname": "file",
            "fieldtype": "Link",
            "options": "Clearing File",
            "width": 150,
            "hidden": 1,
        },
        {"label": "Date", "fieldname": "date", "fieldtype": "Date", "width": 180},
        {
            "label": "Consignee",
            "fieldname": "consignee",
            "fieldtype": "Link",
            "options": "Customer",
            "width": 250,
        },
        {
            "label": "Transportation Type",
            "fieldname": "mode_of_transport",
            "fieldtype": "Link",
            "options": "Mode of Transport",
            "width": 120,
            "hidden": 1,
        },
        {
            "label": "BL/AWB No",
            "fieldname": "bl_awb_no",
            "fieldtype": "Data",
            "width": 120,
        },
        {"label": "ETA", "fieldname": "eta", "fieldtype": "Date", "width": 160},
        {
            "label": "Cargo Description",
            "fieldname": "cargo_description",
            "fieldtype": "Data",
            "width": 250,
        },
        {"label": "Origin", "fieldname": "origin", "fieldtype": "Data", "width": 120},
        {
            "label": "TANSAD",
            "fieldname": "tansad_no",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": "Entry Type",
            "fieldname": "declaration_type",
            "fieldtype": "Select",
            "width": 100,
            "hidden": 1,
        },
        {"label": "CL Plan", "fieldname": "cl_plan", "fieldtype": "Data", "width": 100, "hidden": 1},
        {
            "label": "Cargo Type",
            "fieldname": "cargo_type",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": "CNTR",
            "fieldname": "container_quantity",
            "fieldtype": "Data",
            "width": 130,
        },
        {
            "label": "PKGs",
            "fieldname": "packages",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": "CIF Value",
            "fieldname": "cif_value",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": "Currency",
            "fieldname": "currency",
            "fieldtype": "Data",
            "width": 100,
        },
    ]

    return columns, data
