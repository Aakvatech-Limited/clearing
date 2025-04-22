frappe.listview_settings["Physical Verification"] = {
  add_fields: ["status", "docstatus"],
  has_indicator_for_draft: 1,
  get_indicator: function (doc) {
    const status_map = {
      "Payment Completed": "green",
      "Payment Pending": "darkgrey",
    };

    return [__(doc.status), status_map[doc.status], "status,=," + doc.status];
  },
};
