// Copyright (c) 2024, Nelson Mpanju and contributors
// For license information, please see license.txt
const CLEARANCE_SOURCES = [
  ["TRA Clearance", "TRA Clearance"],
  ["Port Clearance", "Port Clearance"],
  ["Shipping Line Clearance", "Shipping Line Clearance"],
  ["Physical Verification", "Physical Verification"],
];

const INVOICE_DEFAULT_ROWS = [
  { charge_type: "Transport" },
  { charge_type: "Clearing Agency Fee" },
];

frappe.ui.form.on("Clearing Charges", {
  async refresh(frm) {
    const needsTotals = frm.is_new() || !!frm.doc.__unsaved;
    if (needsTotals) {
      calculate_totals(frm);
    }

    if (frm.doc.clearing_file) {
      await populate_clearance_charges(frm);
      await sync_clearing_service_invoice_metrics(frm);
      fetch_and_set_disbursements(frm);
      fetch_and_set_reimbursements(frm);
    } else {
      clear_child_table(frm, "reimbursement");
      frm.set_value("total_paid_amount", 0);
      frm.set_value("total_outstanding_amount", 0);
    }
  },

  async clearing_file(frm) {
    await populate_clearance_charges(frm, { resetExisting: true });
    if (frm.doc.clearing_file) {
      await sync_clearing_service_invoice_metrics(frm);
      fetch_and_set_disbursements(frm);
      fetch_and_set_reimbursements(frm);
    } else {
      clear_child_table(frm, "reimbursement");
      frm.set_value("total_paid_amount", 0);
      frm.set_value("total_outstanding_amount", 0);
    }
  },

  generate_invoice: function (frm) {
    if (frm.is_new()) {
      frappe.msgprint(__("Please save the Clearing Charges before generating an invoice."));
      return;
    }

    if (!frm.doc.consigee) {
      frappe.msgprint(__("Please set a Consignee before generating an invoice."));
      return;
    }

    const eligible = get_invoice_eligible_charges(frm);
    if (!eligible.length) {
      frappe.msgprint(
        __("All invoice charges have already been invoiced. Mark new rows as 'Is Invoice' to proceed.")
      );
      return;
    }

    open_invoice_dialog(frm, eligible);
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

async function populate_clearance_charges(frm, options = {}) {
  const resetExisting = !!options.resetExisting;

  if (resetExisting) {
    frm.clear_table("charges");
  }

  ensure_default_invoice_rows(frm);

  if (!frm.doc.clearing_file) {
    frm.refresh_field("charges");
    calculate_totals(frm);
    return;
  }

  const records = await Promise.all(
    CLEARANCE_SOURCES.map(([doctype, chargeType]) =>
      fetch_clearance_rows(frm, doctype, chargeType)
    )
  );

  const totalsByCharge = {};
  records
    .flat()
    .forEach(({ charge_type, amount }) => {
      if (!charge_type) {
        return;
      }
      const key = charge_type;
      totalsByCharge[key] = (totalsByCharge[key] || 0) + flt(amount || 0);
    });

  Object.entries(totalsByCharge).forEach(([chargeType, total]) => {
    add_or_update_clearance_row(frm, chargeType, total);
  });

  frm.refresh_field("charges");
  calculate_totals(frm);
}

function ensure_default_invoice_rows(frm) {
  const existing = new Set((frm.doc.charges || []).map((row) => row.charge_type));
  let changed = false;
  INVOICE_DEFAULT_ROWS.forEach(({ charge_type }) => {
    if (existing.has(charge_type)) {
      return;
    }
    const row = frm.add_child("charges");
    row.charge_type = charge_type;
    row.amount = 0;
    row.is_invoice = 1;
    changed = true;
  });
  if (changed) {
    frm.refresh_field("charges");
  }
}

function fetch_clearance_rows(frm, doctype, chargeType) {
  return frappe
    .call({
      method: "frappe.client.get_list",
      args: {
        doctype,
        filters: {
          clearing_file: frm.doc.clearing_file,
          paid_by_clearing_agent: 1,
        },
        fields: ["name", "total_charges"],
        limit_page_length: 500,
      },
    })
    .then((r) => {
      const rows = r.message || [];
      return rows.map((row) => ({
        charge_type: chargeType,
        amount: flt(row.total_charges || 0),
      }));
    })
    .catch(() => []);
}

function add_or_update_clearance_row(frm, chargeType, amount) {
  const rows = frm.doc.charges || [];
  let target = rows.find((row) => !row.is_invoice && row.charge_type === chargeType);

  if (!target) {
    target = frm.add_child("charges");
    target.charge_type = chargeType;
    target.is_invoice = 0;
  }

  target.amount = flt(amount || 0);
}

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
  let invoice_total = 0;

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
        invoice_total += amount;
      }
    });
  }

  const total = tra_total + port_total + shipment_total + physical_total;
  let services_total = 0;
  let services_outstanding_total = 0;
  (frm.doc.clearing_services || []).forEach((row) => {
    services_total += flt(row.grand_total || 0);
    services_outstanding_total += flt(row.outstanding_amount || 0);
  });

  set_number_field_if_changed(frm, "tra_clearance_total", tra_total);
  set_number_field_if_changed(frm, "port_clearance_total", port_total);
  set_number_field_if_changed(frm, "shipment_clearance_total", shipment_total);
  set_number_field_if_changed(frm, "physical_clearance_total", physical_total);
  set_number_field_if_changed(frm, "total", total);
  set_number_field_if_changed(frm, "transport_total", transport_total);
  set_number_field_if_changed(frm, "agency_fee", agency_fee_total);
  set_number_field_if_changed(frm, "total_debit", invoice_total);
  set_number_field_if_changed(frm, "total_sales_invoice", services_total);
  set_number_field_if_changed(frm, "outstanding_amount", services_outstanding_total);
  set_number_field_if_changed(
    frm,
    "total_clearing_charges",
    total + services_total
  );
  set_number_field_if_changed(
    frm,
    "balance",
    services_outstanding_total + flt(frm.doc.total_outstanding_amount || 0)
  );
}

function get_invoice_eligible_charges(frm) {
  const currency =
    frm.doc.currency ||
    (frappe.boot && frappe.boot.sysdefaults && frappe.boot.sysdefaults.currency);

  return (frm.doc.charges || [])
    .filter((charge) => {
      if (!charge || !charge.is_invoice) {
        return false;
      }
      if (charge.invoice_reference) {
        return false;
      }
      return flt(charge.amount || 0) > 0;
    })
    .map((charge, index) => {
      const idx = charge.idx || index + 1;
      const key = charge.name || `charge-${idx}`;
      const chargeCurrency = currency;
      const formattedAmount = format_currency(flt(charge.amount || 0), chargeCurrency);
      return {
        key,
        idx,
        charge,
        label: `${charge.charge_type || __("Charge")} | ${formattedAmount}`,
        amount: flt(charge.amount || 0),
        currency: chargeCurrency,
        formattedAmount,
      };
    });
}

function open_invoice_dialog(frm, eligibleCharges) {
  const valueMap = {};
  const options = eligibleCharges.map((entry, index) => {
    const option = {
      label: entry.label,
      value: entry.key,
      checked: false,
      description: entry.formattedAmount,
    };
    valueMap[entry.key] = entry.charge;
    return option;
  });

  let dialog;
  dialog = new frappe.ui.Dialog({
    title: __("Generate Sales Invoice"),
    fields: [
      {
        fieldname: "charges",
        label: __("Charges to Invoice"),
        fieldtype: "MultiCheck",
        options,
        reqd: 1,
        columns: "20rem",
        select_all: true,
      },
      {
        fieldname: "posting_date",
        label: __("Posting Date"),
        fieldtype: "Date",
        default: frappe.datetime.nowdate(),
      },
    ],
    primary_action_label: __("Create Invoice"),
    primary_action(values) {
      const selected = (values.charges || []).filter(Boolean);
      if (!selected.length) {
        frappe.msgprint(__("Select at least one charge to invoice."));
        return;
      }
      const charges = selected
        .map((value) => valueMap[value])
        .filter((charge) => !!charge);
      if (!charges.length) {
        frappe.msgprint(__("Unable to locate the selected charges. Please try again."));
        return;
      }
      create_invoice_from_charges(frm, charges, values.posting_date, dialog);
    },
  });

  dialog.show();
}

function create_invoice_from_charges(frm, charges, postingDate, dialog) {
  const items = charges.map((charge) => ({
    item_code: charge.charge_type,
    qty: charge.quantity || 1,
    rate: flt(charge.amount || 0),
    amount: flt(charge.amount || 0),
  }));

  frappe.call({
    method: "frappe.client.insert",
    args: {
      doc: {
        doctype: "Sales Invoice",
        customer: frm.doc.consigee,
        items,
        posting_date: postingDate || frappe.datetime.nowdate(),
        clearing_charges: frm.doc.name,
        currency: frm.doc.currency || undefined,
      },
    },
    freeze: true,
    freeze_message: __("Preparing Sales Invoice..."),
    callback(r) {
      if (!r.message) {
        return;
      }
      const invoiceDoc = r.message;
      dialog.hide();
      upsert_primary_clearing_service(frm, invoiceDoc);
      mark_charges_as_invoiced(frm, charges, invoiceDoc);
      sync_clearing_service_invoice_metrics(frm);
      frm
        .save()
        .then(() => {
          frappe.msgprint(
            __("Sales Invoice {0} created successfully as Draft. You can edit and submit it.", [
              invoiceDoc.name,
            ])
          );
        })
        .then(() => frm.reload_doc());
    },
  });
}

function mark_charges_as_invoiced(frm, charges, invoiceDoc) {
  if (!invoiceDoc || !invoiceDoc.name) {
    return;
  }

  charges.forEach((charge) => {
    if (!charge) {
      return;
    }
    const doctype = charge.doctype || "Clearing Charge Detail";
    const docname = charge.name;
    charge.invoice_reference = invoiceDoc.name;
    frappe.model.set_value(doctype, docname, "invoice_reference", invoiceDoc.name);
  });

  frm.refresh_field("charges");
  calculate_totals(frm);
}

function detach_charges_from_invoice(frm, invoiceName) {
  if (!invoiceName) {
    return;
  }
  let updated = false;
  (frm.doc.charges || []).forEach((charge) => {
    if (!charge || charge.invoice_reference !== invoiceName) {
      return;
    }
    charge.invoice_reference = "";
    const doctype = charge.doctype || "Clearing Charge Detail";
    if (charge.name) {
      frappe.model.set_value(doctype, charge.name, "invoice_reference", "");
    }
    updated = true;
  });
  if (updated) {
    frm.refresh_field("charges");
    calculate_totals(frm);
  }
}

function fetch_and_set_disbursements(frm) {
  frappe.call({
    method: "clearing.clearing.doctype.clearing_charges.clearing_charges.get_disbursement_journal_entries",
    args: { clearing_file: frm.doc.clearing_file },
    callback(r) {
      const rows = r.message || [];
      const charges = (frm.doc.charges || [])
        .filter((row) => Number(row.is_invoice) !== 1)
        .sort((left, right) => (left.idx || 0) - (right.idx || 0));

      const buckets = new Map();
      const unmatched = [];
      rows.forEach((row) => {
        const type =
          row.charge_type || inferChargeTypeFromRemark(row.remark) || null;
        if (type) {
          if (!buckets.has(type)) {
            buckets.set(type, []);
          }
          buckets.get(type).push(row);
        } else {
          unmatched.push(row);
        }
      });

      let changed = false;
      charges.forEach((charge) => {
        if (!charge || !charge.name) {
          return;
        }
        const chargeType = (charge.charge_type || "").trim();
        let entry = null;
        if (chargeType && buckets.has(chargeType) && buckets.get(chargeType).length) {
          entry = buckets.get(chargeType).shift();
        } else if (unmatched.length) {
          entry = unmatched.shift();
        }

        const targetJe = (entry && entry.journal_entry) || null;
        const targetDate =
          (entry && (entry.posting_date || entry.date || null)) || null;

        const currentJe = charge.disbursement || null;
        if (currentJe !== targetJe) {
          frappe.model.set_value(
            charge.doctype || "Clearing Charge Detail",
            charge.name,
            "disbursement",
            targetJe
          );
          changed = true;
        }

        const currentDate = charge.disbursed_date || null;
        if ((currentDate || null) !== (targetDate || null)) {
          frappe.model.set_value(
            charge.doctype || "Clearing Charge Detail",
            charge.name,
            "disbursed_date",
            targetDate || null
          );
          changed = true;
        }
      });

      if (changed) {
        frm.refresh_field("charges");
      }
    },
  });
}

function inferChargeTypeFromRemark(remark) {
  if (!remark) {
    return null;
  }
  const head = remark.split("|", 1)[0].trim();
  if (!head) {
    return null;
  }
  const parts = head.split(":");
  if (parts.length >= 1) {
    return parts[0].trim() || null;
  }
  return head || null;
}

function fetch_and_set_reimbursements(frm) {
  frappe.call({
    method: "clearing.clearing.doctype.clearing_charges.clearing_charges.get_reimbursement_payments_for_journal_entries",
    args: { clearing_file: frm.doc.clearing_file },
    callback: function (r) {
      const payload = r.message || {};
      const rows = payload.rows || [];
      const changed = update_child_table_if_changed(
        frm,
        "reimbursement",
        rows,
        (row, target) => {
          target.payment_entry = row.payment_entry;
          target.party = row.party;
          target.date = row.date;
          target.paid_amount = row.paid_amount;
          target.outstanding_amount = row.outstanding_amount;
        },
        reimbursement_snapshot
      );

      let total_paid = 0.0;
      rows.forEach((row) => {
        total_paid += flt(row.paid_amount || 0);
      });
      frm.set_value("total_paid_amount", total_paid);
      frm.set_value(
        "total_outstanding_amount",
        flt(payload.je_outstanding_total || 0)
      );

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

  const options = rows.map((row, index) => {
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
      checked: false,
      description: __('Outstanding: {0}', [formattedOutstanding]),
    };
  });

  const rowByName = {};
  rows.forEach((row) => {
    rowByName[row.journal_entry] = row;
  });

  let dialog;
  dialog = new frappe.ui.Dialog({
    title: __("Make Payment"),
    fields: [
      {
        fieldname: "journal_entries",
        label: __("Journal Entries"),
        fieldtype: "MultiCheck",
        options: options,
        columns: "20rem",
        select_all: true,
        sort_options: false,
        reqd: 1,
      },
      {
        fieldname: "amount_to_pay",
        label: __("Total Amount to Pay (optional)"),
        fieldtype: "Currency",
        description: __("Leave blank to pay the full outstanding amount for the selected entries."),
      },
    ],
    primary_action_label: __("Proceed"),
    primary_action(values) {
      const selectedValues = (values.journal_entries || []).filter(Boolean);
      if (!selectedValues.length) {
        frappe.msgprint(__("Please select at least one Journal Entry."));
        return;
      }

      const selectedRows = selectedValues
        .map((name) => rowByName[name])
        .filter((row) => !!row);
      if (!selectedRows.length) {
        frappe.msgprint(__("The selected Journal Entries could not be found. Please try again."));
        return;
      }

      const totalOutstanding = selectedRows.reduce(
        (acc, row) => acc + flt(row.outstanding || 0),
        0
      );
      if (totalOutstanding <= 0) {
        frappe.msgprint(__("The selected Journal Entries have no outstanding balance."));
        return;
      }

      let amount = null;
      if (values.amount_to_pay) {
        const parsed = parse_amount_input(values.amount_to_pay);
        if (!parsed || parsed <= 0) {
          frappe.msgprint(__("Please enter a valid payment amount."));
          return;
        }
        amount = Math.min(parsed, totalOutstanding);
      }

      dialog.hide();
      const args = { journal_entries: selectedValues };
      if (typeof amount === "number" && !Number.isNaN(amount)) {
        args.total_amount = amount;
      }
      frappe.call({
        method: "clearing.api.journal_entry.make_payment_entry_from_journal_entries",
        args,
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

  let row = frm.doc.clearing_services.find(
    (service) => service.reference_number === invoiceDoc.name
  );
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
  if (Object.prototype.hasOwnProperty.call(invoiceDoc, "grand_total")) {
    frappe.model.set_value(doctype, docname, "grand_total", invoiceDoc.grand_total || 0);
  }
  const outstanding =
    invoiceDoc.outstanding_amount ??
    invoiceDoc.outstanding_amount_after_payment ??
    null;
  if (outstanding !== null) {
    frappe.model.set_value(doctype, docname, "outstanding_amount", outstanding);
  }
  frm.refresh_field("clearing_services");
}

async function sync_clearing_service_invoice_metrics(frm) {
  const rows = frm.doc.clearing_services || [];
  if (!rows.length) {
    calculate_totals(frm);
    return;
  }

  const invoices = Array.from(
    new Set(
      rows
        .map((row) => row.reference_number)
        .filter((name) => typeof name === "string" && name.trim())
    )
  );

  if (!invoices.length) {
    return;
  }

  try {
    const { message } = await frappe.call({
      method: "frappe.client.get_list",
      args: {
        doctype: "Sales Invoice",
        filters: { name: ["in", invoices] },
        fields: ["name", "grand_total", "outstanding_amount", "status", "docstatus"],
        limit_page_length: invoices.length,
      },
    });

    const dataByName = {};
    (message || []).forEach((invoice) => {
      dataByName[invoice.name] = invoice;
    });

    rows.forEach((row) => {
      const invoice = dataByName[row.reference_number];
      if (!invoice) {
        return;
      }
      const doctype = row.doctype || "Clearing Services";
      const docname = row.name;
      let docstatus = parseInt(invoice.docstatus, 10);
      if (!Number.isFinite(docstatus)) {
        docstatus = 0;
      }
      const isCancelled = docstatus === 2;

      if (isCancelled) {
        detach_charges_from_invoice(frm, invoice.name);
        const services = frm.doc.clearing_services || [];
        const index = services.findIndex(
          (service) => service && service.reference_number === invoice.name
        );
        if (index >= 0) {
          services.splice(index, 1);
        }
        frm.refresh_field("clearing_services");
        calculate_totals(frm);
        return;
      }

      frappe.model.set_value(doctype, docname, "reference_number", invoice.name);
      frappe.model.set_value(
        doctype,
        docname,
        "grand_total",
        flt(invoice.grand_total || 0)
      );
      frappe.model.set_value(
        doctype,
        docname,
        "outstanding_amount",
        flt(invoice.outstanding_amount || 0)
      );
      frappe.model.set_value(
        doctype,
        docname,
        "invoice_status",
        invoice.status || row.invoice_status || ""
      );
    });
    frm.refresh_field("clearing_services");
    calculate_totals(frm);
  } catch (error) {
    console.error("Failed to refresh clearing service invoice metrics", error);
    calculate_totals(frm);
  }
}
