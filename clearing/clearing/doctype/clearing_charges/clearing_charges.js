// Copyright (c) 2024, Nelson Mpanju and contributors
// For license information, please see license.txt
frappe.ui.form.on("Clearing Charges", {
  refresh: function (frm) {
    // Calculate totals when form loads
    calculate_totals(frm);
  },
  
  clearing_file: function (frm) {
    // Clear the child table before fetching new data
    frm.clear_table("charges");
    
    // Add default Transport and Clearing Agency Fee items with is_invoice checked
    let transport_row = frm.add_child("charges");
    transport_row.charge_type = "Transport";
    transport_row.amount = 0;
    transport_row.is_invoice = 1;
    
    let agency_fee_row = frm.add_child("charges");
    agency_fee_row.charge_type = "Clearing Agency Fee";
    agency_fee_row.amount = 0;
    agency_fee_row.is_invoice = 1;
    
    // Fetch charges from related doctypes where 'paid_by_clearing_agent' is checked
    frappe.call({
      method: "frappe.client.get_list",
      args: {
        doctype: "TRA Clearance",
        filters: {
          clearing_file: frm.doc.clearing_file,
          paid_by_clearing_agent: 1,
        },
        fields: ["total_charges"],
      },
      callback: function (r) {
        if (r.message) {
          $.each(r.message, function (i, d) {
            let row = frm.add_child("charges");
            row.charge_type = "TRA Clearance";
            row.amount = d.total_charges;
            row.is_invoice = 0;
            frm.refresh_field("charges");
            calculate_totals(frm);
          });
        }
      },
    });
    
    frappe.call({
      method: "frappe.client.get_list",
      args: {
        doctype: "Port Clearance",
        filters: {
          clearing_file: frm.doc.clearing_file,
          paid_by_clearing_agent: 1,
        },
        fields: ["total_charges"],
      },
      callback: function (r) {
        if (r.message) {
          $.each(r.message, function (i, d) {
            let row = frm.add_child("charges");
            row.charge_type = "Port Clearance";
            row.amount = d.total_charges;
            row.is_invoice = 0;
            frm.refresh_field("charges");
            calculate_totals(frm);
          });
        }
      },
    });
    
    frappe.call({
      method: "frappe.client.get_list",
      args: {
        doctype: "Shipping Line Clearance",
        filters: {
          clearing_file: frm.doc.clearing_file,
          paid_by_clearing_agent: 1,
        },
        fields: ["total_charges"],
      },
      callback: function (r) {
        if (r.message) {
          $.each(r.message, function (i, d) {
            let row = frm.add_child("charges");
            row.charge_type = "Shipping Line Clearance";
            row.amount = d.total_charges;
            row.is_invoice = 0;
            frm.refresh_field("charges");
            calculate_totals(frm);
          });
        }
      },
    });
    
    frappe.call({
      method: "frappe.client.get_list",
      args: {
        doctype: "Physical Verification",
        filters: {
          clearing_file: frm.doc.clearing_file,
          paid_by_clearing_agent: 1,
        },
        fields: ["total_charges"],
      },
      callback: function (r) {
        if (r.message) {
          $.each(r.message, function (i, d) {
            let row = frm.add_child("charges");
            row.charge_type = "Physical Verification";
            row.amount = d.total_charges;
            row.is_invoice = 0;
            frm.refresh_field("charges");
            calculate_totals(frm);
          });
        }
      },
    });
    
    frm.refresh_field("charges");
    calculate_totals(frm);
  },
  
  generate_invoice: function (frm) {
    if (frm.is_new()) {
      frappe.msgprint(__("Please save the Clearing Charges before generating an invoice."));
      return;
    }

    if (frm.doc.charges && frm.doc.charges.length > 0) {
      let items = [];
      
      frm.doc.charges.forEach(function (row) {
        if (row.is_invoice) {
          items.push({
            item_code: row.charge_type,
            qty: row.quantity || 1,
            rate: row.amount,
            amount: row.amount,
          });
        }
      });
      
      if (items.length === 0) {
        frappe.msgprint(__("Please select charges to invoice by checking 'Is Invoice' field."));
        return;
      }
      
      // Create Sales Invoice as DRAFT (not submitted)
      frappe.call({
        method: "frappe.client.insert",
        args: {
          doc: {
            doctype: "Sales Invoice",
            customer: frm.doc.consigee,
            items: items,
            posting_date: frappe.datetime.nowdate(),
            clearing_charges: frm.doc.name,
            // Do NOT set docstatus: 1 - keep as draft
          },
        },
        callback: function (r) {
          if (r.message) {
            // Link the invoice WITHOUT submitting
            frm.set_value("reference_number", r.message.name);
            frm.set_value("invoice_status", r.message.status || "Draft");
            frm.save().then(() => {
              frappe.msgprint(
                __("Sales Invoice {0} created successfully as Draft. You can edit and submit it.", [r.message.name])
              );
            });
          }
        },
      });
    } else {
      frappe.msgprint(__("Please add charges to create an invoice."));
    }
  },
});

// Child table events
frappe.ui.form.on("Clearing Charge Detail", {
  amount: function (frm, cdt, cdn) {
    calculate_totals(frm);
  },
  is_invoice: function (frm, cdt, cdn) {
    calculate_totals(frm);
  },
  charge_type: function (frm, cdt, cdn) {
    calculate_totals(frm);
  },
  charges_remove: function (frm) {
    calculate_totals(frm);
  }
});

function calculate_totals(frm) {
  let tra_total = 0;
  let port_total = 0;
  let shipment_total = 0;
  let physical_total = 0;
  let transport_total = 0;
  let agency_fee_total = 0;
  let total_debit = 0;
  
  if (frm.doc.charges) {
    frm.doc.charges.forEach(function (charge) {
      let amount = flt(charge.amount || 0);
      
      if (charge.charge_type === "TRA Clearance") {
        tra_total += amount;
      } else if (charge.charge_type === "Port Clearance") {
        port_total += amount;
      } else if (charge.charge_type === "Shipping Line Clearance") {
        shipment_total += amount;
      } else if (charge.charge_type === "Physical Verification") {
        physical_total += amount;
      } else if (charge.charge_type === "Transport") {
        transport_total += amount;
      } else if (charge.charge_type === "Clearing Agency Fee") {
        agency_fee_total += amount;
      }
      
      if (charge.is_invoice) {
        total_debit += amount;
      }
    });
  }
  
  const total = tra_total + port_total + shipment_total + physical_total;
  frm.set_value("tra_clearance_total", tra_total);
  frm.set_value("port_clearance_total", port_total);
  frm.set_value("shipment_clearance_total", shipment_total);
  frm.set_value("physical_clearance_total", physical_total);
  frm.set_value("total", total);
  frm.set_value("transport_total", transport_total);
  frm.set_value("agency_fee", agency_fee_total);
  frm.set_value("total_debit", total_debit);
  frm.set_value("total_clearing_charges", total + total_debit);
}
