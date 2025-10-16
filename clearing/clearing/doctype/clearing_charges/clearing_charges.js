// Copyright (c) 2024, Nelson Mpanju and contributors
// For license information, please see license.txt
frappe.ui.form.on("Clearing Charges", {
  refresh: function (frm) {
    const needsTotals = frm.is_new() || !!frm.doc.__unsaved;
    if (needsTotals) {
      calculate_totals(frm);
    }

    if (frm.doc.clearing_file) {
      fetch_and_set_disbursements(frm);
      fetch_and_set_reimbursements(frm);
    } else {
      clear_child_table(frm, "disbursement");
      clear_child_table(frm, "reimbursement");
      frm.set_value("total_paid_amount", 0);
      frm.set_value("total_outstanding_amount", 0);
    }
  },

  clearing_file: function (frm) {
    frm.clear_table("charges");

    let transport_row = frm.add_child("charges");
    transport_row.charge_type = "Transport";
    transport_row.amount = 0;
    transport_row.is_invoice = 1;

    let agency_fee_row = frm.add_child("charges");
    agency_fee_row.charge_type = "Clearing Agency Fee";
    agency_fee_row.amount = 0;
    agency_fee_row.is_invoice = 1;

    const fetchCharges = (doctype, chargeType) => {
      frappe.call({
        method: "frappe.client.get_list",
        args: {
          doctype: doctype,
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
              row.charge_type = chargeType;
              row.amount = d.total_charges;
              row.is_invoice = 0;
              frm.refresh_field("charges");
              calculate_totals(frm);
            });
          }
        },
      });
    };

    fetchCharges("TRA Clearance", "TRA Clearance");
    fetchCharges("Port Clearance", "Port Clearance");
    fetchCharges("Shipping Line Clearance", "Shipping Line Clearance");
    fetchCharges("Physical Verification", "Physical Verification");

    frm.refresh_field("charges");
    calculate_totals(frm);

    if (frm.doc.clearing_file) {
      fetch_and_set_disbursements(frm);
      fetch_and_set_reimbursements(frm);
    }
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

      frappe.call({
        method: "frappe.client.insert",
        args: {
          doc: {
            doctype: "Sales Invoice",
            customer: frm.doc.consigee,
            items: items,
            posting_date: frappe.datetime.nowdate(),
            clearing_charges: frm.doc.name,
          },
        },
        callback: function (r) {
          if (r.message) {
            upsert_primary_clearing_service(frm, r.message);
            frm
              .save()
              .then(() => {
                frappe.msgprint(
                  __("Sales Invoice {0} created successfully as Draft. You can edit and submit it.", [
                    r.message.name,
                  ])
                );
              })
              .then(() => frm.reload_doc());
          }
        },
      });
    } else {
      frappe.msgprint(__("Please add charges to create an invoice."));
    }
  },

  make_payment(frm) {
    if (frm.is_new()) {
      frappe.msgprint(__("Please save the document first."));
      return;
    }

    if (!frm.doc.clearing_file) {
      frappe.msgprint(__("Please set a Clearing File before making a payment."));
      return;
    }

    frappe.call({
      method: "clearing.clearing.doctype.clearing_charges.clearing_charges.get_disbursement_journal_entries_detailed",
      args: { clearing_file: frm.doc.clearing_file },
      callback(r) {
        const rows = r.message || [];
        if (!rows.length) {
          frappe.msgprint(__("No outstanding Journal Entries were found for this Clearing File."));
          return;
        }
        open_payment_dialog(frm, rows);
      },
    });
  },
});

frappe.ui.form.on("Clearing Charge Detail", {
  amount: function (frm) {
    calculate_totals(frm);
  },
  is_invoice: function (frm) {
    calculate_totals(frm);
  },
  charge_type: function (frm) {
    calculate_totals(frm);
  },
  charges_remove: function (frm) {
    calculate_totals(frm);
  },
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
      const amount = flt(charge.amount || 0);

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
  const total_clearing_charges = total + total_debit;

  set_number_field_if_changed(frm, "tra_clearance_total", tra_total);
  set_number_field_if_changed(frm, "port_clearance_total", port_total);
  set_number_field_if_changed(frm, "shipment_clearance_total", shipment_total);
  set_number_field_if_changed(frm, "physical_clearance_total", physical_total);
  set_number_field_if_changed(frm, "total", total);
  set_number_field_if_changed(frm, "transport_total", transport_total);
  set_number_field_if_changed(frm, "agency_fee", agency_fee_total);
  set_number_field_if_changed(frm, "total_debit", total_debit);
  set_number_field_if_changed(frm, "total_clearing_charges", total_clearing_charges);
}

function fetch_and_set_disbursements(frm) {
  frappe.call({
    method: "clearing.clearing.doctype.clearing_charges.clearing_charges.get_disbursement_journal_entries",
    args: { clearing_file: frm.doc.clearing_file },
    callback: function (r) {
      const rows = r.message || [];
      update_child_table_if_changed(frm, "disbursement", rows, (row, target) => {
        target.journal_entry = row.journal_entry;
        if (row.date) {
          target.posting_date = row.date;
        }
      }, disbursement_snapshot);
    },
  });
}

function fetch_and_set_reimbursements(frm) {
  frappe.call({
    method: "clearing.clearing.doctype.clearing_charges.clearing_charges.get_reimbursement_payments_for_journal_entries",
    args: { clearing_file: frm.doc.clearing_file },
    callback: function (r) {
      const rows = r.message || [];
      const changed = update_child_table_if_changed(frm, "reimbursement", rows, (row, target) => {
        target.payment_entry = row.payment_entry;
        target.party = row.party;
        target.date = row.date;
        target.paid_amount = row.paid_amount;
        target.outstanding_amount = row.outstanding_amount;
      }, reimbursement_snapshot);

      let total_paid = 0.0;
      let total_outstanding = 0.0;
      rows.forEach((row) => {
        total_paid += flt(row.paid_amount || 0);
        total_outstanding += flt(row.outstanding_amount || 0);
      });
      frm.set_value("total_paid_amount", total_paid);
      frm.set_value("total_outstanding_amount", total_outstanding);

      if (changed && !frm.is_new()) {
        frm.save().catch(() => null);
      }
    },
  });
}

function clear_child_table(frm, fieldname) {
  if ((frm.doc[fieldname] || []).length) {
    frm.clear_table(fieldname);
    frm.refresh_field(fieldname);
  }
}

function update_child_table_if_changed(frm, fieldname, rows, assigner, snapshot) {
  const current = (frm.doc[fieldname] || []).map(snapshot);
  const target = rows.map(snapshot);

  if (arrays_equal(current, target)) {
    return false;
  }

  frm.clear_table(fieldname);
  rows.forEach((row) => {
    const child = frm.add_child(fieldname);
    assigner(row, child);
  });
  frm.refresh_field(fieldname);

  return true;
}

function disbursement_snapshot(row) {
  return {
    journal_entry: row.journal_entry,
    posting_date: row.posting_date || row.date || null,
  };
}

function reimbursement_snapshot(row) {
  return {
    payment_entry: row.payment_entry,
    party: row.party || "",
    date: row.date || null,
    paid_amount: flt(row.paid_amount || 0),
    outstanding_amount: flt(row.outstanding_amount || 0),
  };
}

function arrays_equal(left, right) {
  if (left.length !== right.length) {
    return false;
  }

  for (let i = 0; i < left.length; i++) {
    if (!objects_shallow_equal(left[i], right[i])) {
      return false;
    }
  }
  return true;
}

function objects_shallow_equal(a, b) {
  const aKeys = Object.keys(a);
  const bKeys = Object.keys(b);
  if (aKeys.length !== bKeys.length) {
    return false;
  }
  return aKeys.every((key) => {
    const av = a[key];
    const bv = b[key];
    if (typeof av === "number" || typeof bv === "number") {
      return Math.abs(flt(av || 0) - flt(bv || 0)) <= 0.000001;
    }
    return (av || "") === (bv || "");
  });
}

function open_payment_dialog(frm, rows) {
  const currency =
    frm.doc.currency ||
    (frappe.boot && frappe.boot.sysdefaults && frappe.boot.sysdefaults.currency);

  const options = rows.map((row) => {
    const outstanding = flt(row.outstanding || 0);
    const labelParts = [row.journal_entry];
    if (row.clearance_type) {
      labelParts.push(row.clearance_type);
    }
    const formattedOutstanding = format_currency(outstanding, currency);
    labelParts.push(__("Outstanding: {0}", [formattedOutstanding]));
    return {
      label: labelParts.join(" | "),
      value: row.journal_entry,
      outstanding,
    };
  });

  let dialog;
  const optionLabels = options.map((opt) => opt.label);
  dialog = new frappe.ui.Dialog({
    title: __("Make Payment"),
    fields: [
      {
        fieldname: "journal_entry",
        label: __("Journal Entry"),
        fieldtype: "Select",
        options: optionLabels.join("\n"),
        reqd: 1,
        default: optionLabels[0],
      },
      {
        fieldname: "amount_to_pay",
        label: __("Amount to Pay (optional)"),
        fieldtype: "Data",
        description: __("Leave blank to pay the full outstanding amount."),
      },
    ],
    primary_action_label: __("Proceed"),
    primary_action(values) {
      const selectedLabel = values.journal_entry || "";
      const selected = options.find((opt) => opt.label === selectedLabel) || {};
      const journal_entry = selected.value || selectedLabel.split("|")[0].trim();
      const row = rows.find((item) => item.journal_entry === journal_entry);
      if (!row) {
        frappe.msgprint(__("Please choose a valid Journal Entry."));
        return;
      }

      let amount = selected.outstanding || flt(row.outstanding || 0);
      if (values.amount_to_pay) {
        const parsed = parse_amount_input(values.amount_to_pay);
        if (!parsed || parsed <= 0) {
          frappe.msgprint(__("Please enter a valid payment amount."));
          return;
        }
        amount = Math.min(parsed, amount || parsed);
      }

      dialog.hide();
      frappe.call({
        method: "clearing.api.journal_entry.make_payment_entry_from_journal_entry",
        args: {
          journal_entry,
          allocated_amount: amount,
        },
        freeze: true,
        freeze_message: __("Preparing Payment Entry..."),
        callback(r) {
          if (!r.message) {
            return;
          }
          const doclist = frappe.model.sync(r.message);
          if (doclist && doclist.length) {
            frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
          }
        },
      });
    },
  });

  dialog.show();
}

function parse_amount_input(raw) {
  if (raw === null || raw === undefined) {
    return null;
  }
  const text = String(raw).trim();
  if (!text) {
    return null;
  }
  const normalized = text.replace(/,/g, "");
  const value = parseFloat(normalized);
  return Number.isFinite(value) ? value : null;
}

function set_number_field_if_changed(frm, fieldname, value) {
  const target = flt(value || 0);
  const current = flt(frm.doc[fieldname] || 0);
  if (Math.abs(current - target) <= 0.000001) {
    return false;
  }
  frm.set_value(fieldname, target);
  return true;
}

function upsert_primary_clearing_service(frm, invoiceDoc) {
  if (!invoiceDoc || !invoiceDoc.name) {
    return;
  }

  if (!frm.doc.clearing_services) {
    frm.doc.clearing_services = [];
  }

  let row =
    frm.doc.clearing_services.find((service) => service.reference_number === invoiceDoc.name) ||
    frm.doc.clearing_services[0];

  if (!row) {
    row = frm.add_child("clearing_services");
  }

  const doctype = row.doctype || "Clearing Services";
  const docname = row.name;

  frappe.model.set_value(doctype, docname, "reference_number", invoiceDoc.name);
  frappe.model.set_value(
    doctype,
    docname,
    "reference_date",
    invoiceDoc.posting_date || frappe.datetime.nowdate()
  );
  frappe.model.set_value(doctype, docname, "invoice_status", invoiceDoc.status || "Draft");

  frm.refresh_field("clearing_services");
}
