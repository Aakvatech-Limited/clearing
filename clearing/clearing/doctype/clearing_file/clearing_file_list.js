frappe.listview_settings["Clearing File"] = {
  add_fields: ["tansad_no", "reference_no", "awbbl_no"],
  has_indicator_for_draft: true,
  get_indicator: function (doc) {
    const status_map = {
      Open: "orange",
      "Pre-Lodged": "blue",
      "On Process": "blue",
      Cleared: "gray",
      Delivered: "green",
      "Bills Paid": "gray",
      Cancelled: "red",
    };

    return [__(doc.status), status_map[doc.status], "status,=," + doc.status];
  }
};
