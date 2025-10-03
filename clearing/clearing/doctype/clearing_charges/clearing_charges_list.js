frappe.listview_settings["Clearing Charges"] = {
  add_fields: ["status", "docstatus"],
  has_indicator_for_draft: true,
  get_indicator: function (doc) {
    const status_map = {
      "Clearing Charges Raised": "gray",
      "Pending Payment": "blue",
      "Partially Paid": "orange",
      Paid: "green",
      "On Hold": "red",
    };

    return [__(doc.status), status_map[doc.status], "status,=," + doc.status];
  }
};
