frappe.listview_settings["Clearing File"] = {
  add_fields: ["status", "tansad_no", "reference_no"],
  get_indicator: function (doc) {
    const status_map = {
      Open: "orange",
      "Pre-Lodged": "green",
      "On Process": "blue",
      Cleared: "green",
      Delivered: "green",
      "Bills Paid": "red",
    };
    return [__(doc.status), status_map[doc.status], "status,=," + doc.status];
  },
  filters: [
    {
      fieldname: "status",
      label: __("Status"),
      fieldtype: "Select",
      options: "Open\nPre-Lodged\nOn Process\nCleared\nDelivered\nBills Paid",
      default: "Open",
    },
    // Add TANSAD No filter
    {
      fieldname: "tansad_no",
      label: __("TANSAD No"),
      fieldtype: "Data",
    },
    // Add Reference No filter
    {
      fieldname: "reference_no",
      label: __("Reference No"),
      fieldtype: "Data",
    },
  ],
};
