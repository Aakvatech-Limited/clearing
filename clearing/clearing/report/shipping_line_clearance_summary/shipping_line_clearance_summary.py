import frappe
from frappe.query_builder import DocType, Order


def execute(filters=None):
    filters = filters or {}

    ShippingLineClearance = DocType("Shipping Line Clearance")
    ClearingFile = DocType("Clearing File")
    Cargo = DocType("Cargo")

    query = (
        frappe.qb.from_(ShippingLineClearance)
        .left_join(ClearingFile)
        .on(ClearingFile.name == ShippingLineClearance.clearing_file)
        .left_join(Cargo)
        .on(Cargo.parent == ClearingFile.name)
        .select(
            ShippingLineClearance.name.as_("shipping_line_doc"),
            ShippingLineClearance.posting_date.as_("date"),
            ShippingLineClearance.consignee.as_("consignee"),
            ShippingLineClearance.delivery_order_expire_date.as_("do_expire_date"),
            ShippingLineClearance.isuue_date.as_("do_issued"),
            ClearingFile.awbbl_no.as_("bl_no"),
            ClearingFile.name.as_("clearing_file"),  # ✅ Added column
            Cargo.container_number.as_("container_no"),
            ShippingLineClearance.total_charges.as_("charges"),
            ShippingLineClearance.paid_by_clearing_agent.as_("paid_on_behalf"),
            ShippingLineClearance.invoice_paid.as_("duties_paid"),
            ShippingLineClearance.status.as_("status"),
        )
        .orderby(ShippingLineClearance.posting_date, order=Order.desc)
    )

    # Apply filters
    if filters.get("from_date") and filters.get("to_date"):
        query = query.where(
            (ShippingLineClearance.posting_date >= filters["from_date"])
            & (ShippingLineClearance.posting_date <= filters["to_date"])
        )

    if filters.get("consignee"):
        query = query.where(ShippingLineClearance.consignee == filters["consignee"])

    if filters.get("status"):
        query = query.where(ShippingLineClearance.status == filters["status"])

    if filters.get("clearing_file"):
        query = query.where(ClearingFile.name == filters["clearing_file"])

    data = query.run(as_dict=True)

    columns = [
        {
            "label": "Shipping Line Doc",
            "fieldname": "shipping_line_doc",
            "fieldtype": "Link",
            "options": "Shipping Line Clearance",
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
            "label": "D.O Expire Date",
            "fieldname": "do_expire_date",
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "label": "D.O Issued",
            "fieldname": "do_issued",
            "fieldtype": "Date",
            "width": 100,
        },
        {"label": "BL No", "fieldname": "bl_no", "fieldtype": "Data", "width": 150},
        {
            "label": "Clearing File",
            "fieldname": "clearing_file",
            "fieldtype": "Link",
            "options": "Clearing File",
            "width": 150,
        },  # ✅ Added column
        {
            "label": "Container No",
            "fieldname": "container_no",
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
            "width": 80,
        },
        {
            "label": "Duties Paid",
            "fieldname": "duties_paid",
            "fieldtype": "Check",
            "width": 80,
        },
        {"label": "Status", "fieldname": "status", "fieldtype": "Select", "width": 150},
    ]

    return columns, data
