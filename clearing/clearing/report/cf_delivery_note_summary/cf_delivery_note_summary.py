import frappe
from frappe.query_builder import DocType, Order


def execute(filters=None):
    filters = filters or {}

    DeliveryNote = DocType("CF Delivery Note")
    ClearingFile = DocType("Clearing File")
    Cargo = DocType("Cargo")
    ShippingLineClearance = DocType("Shipping Line Clearance")

    query = (
        frappe.qb.from_(DeliveryNote)
        .left_join(ClearingFile)
        .on(ClearingFile.name == DeliveryNote.clearing_file)
        .left_join(Cargo)
        .on(Cargo.parent == ClearingFile.name)
        .left_join(ShippingLineClearance)
        .on(ShippingLineClearance.clearing_file == ClearingFile.name)
        .select(
            DeliveryNote.posting_date.as_("date"),
            DeliveryNote.consignee.as_("consignee"),
            Cargo.cargo_description.as_("cargo_description"),
            DeliveryNote.loading_date.as_("loading_date"),
            DeliveryNote.delivery_date.as_("delivery_date"),
            DeliveryNote.delivery_location.as_("delivery_location"),
            DeliveryNote.has_container_interchange.as_("has_container_interchange"),
            DeliveryNote.return_date.as_("return_date"),  # Optional column if you want to show the linked clearing file
        )
        .orderby(DeliveryNote.posting_date, order=Order.desc)
    )

    # Apply filters
    if filters.get("from_date") and filters.get("to_date"):
        query = query.where(
            (DeliveryNote.posting_date >= filters["from_date"])
            & (DeliveryNote.posting_date <= filters["to_date"])
        )

    if filters.get("consignee"):
        query = query.where(DeliveryNote.consignee == filters["consignee"])

    if filters.get("delivery_id"):
        query = query.where(DeliveryNote.consignee == filters["delivery_id"])

    if filters.get("clearing_file"):
        query = query.where(ClearingFile.name == filters["clearing_file"])

    if filters.get("has_container_interchange"):
        query = query.where(DeliveryNote.has_container_interchange == filters["has_container_interchange"])

    data = query.run(as_dict=True)

    columns = [
        {
            "label": "Delivery ID",
            "fieldname": "delivery_id",
            "fieldtype": "Link",
            "options": "CF Delivery Note",
            "width": 150,
            "hidden": 1,
        },
        {"label": "Date", "fieldname": "date", "fieldtype": "Date", "width": 150},
        {
            "label": "Consignee",
            "fieldname": "consignee",
            "fieldtype": "Link",
            "options": "Customer",
            "width": 250,
        },
        {
            "label": "Cargo Description",
            "fieldname": "cargo_description",
            "fieldtype": "Data",
            "width": 250,
        },
        {
            "label": "Loading Date",
            "fieldname": "loading_date",
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "label": "Delivery Date",
            "fieldname": "delivery_date",
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "label": "Delivery Location",
            "fieldname": "delivery_location",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": "Has Container Interchange",
            "fieldname": "has_container_interchange",
            "fieldtype": "Check",
            "width": 120,
        },
        {
            "label": "Return Date",
            "fieldname": "return_date",
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "label": "Clearing File",
            "fieldname": "clearing_file",
            "fieldtype": "Link",
            "options": "Clearing File",
            "width": 150,
            "hidden": 1,
        },  # optional
    ]

    return columns, data
