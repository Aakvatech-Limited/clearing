// Copyright (c) 2024, Nelson Mpanju and contributors
// For license information, please see license.txt
const CLEARANCE_SOURCES = [
  ["TRA Clearance", "TRA Clearance"],
  ["Port Clearance", "Port Clearance"],
  ["Shipping Line Clearance", "Shipping Line Clearance"],
  ["Physical Verification", "Physical Verification"],
];

const CLEARANCE_SOURCE_NAMES = CLEARANCE_SOURCES.map(([, chargeType]) => chargeType);

const INVOICE_DEFAULT_ROWS = [
  { charge_type: "Transport" },
  { charge_type: "Clearing Agency Fee" },
];

frappe.ui.form.on("Clearing Charges", {
  async onload(frm) {
    await setup_disbursement_link_behaviour(frm);
  },

  async refresh(frm) {
    await setup_disbursement_link_behaviour(frm);

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
      await setup_disbursement_link_behaviour(frm);
      await sync_clearing_service_invoice_metrics(frm);
      fetch_and_set_disbursements(frm);
      fetch_and_set_reimbursements(frm);
    } else {
      await setup_disbursement_link_behaviour(frm);
      clear_child_table(frm, "reimbursement");
      frm.set_value("total_paid_amount", 0);
      frm.set_value("total_outstanding_amount", 0);
    }
  },

  generate_invoice(frm) {
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

  async make_jv(frm) {
    if (frm.is_new()) {
      frappe.msgprint(__("Please save the document first."));
      return;
    }

    if (!frm.doc.clearing_file) {
      frappe.msgprint(__("Please set a Clearing File before creating Journal Entries."));
      return;
    }

    const eligible = get_journal_entry_eligible_charges(frm);
    if (!eligible.length) {
      frappe.msgprint(__("All non-invoice charges already have a Journal Entry or have zero amount."));
      return;
    }

    open_make_jv_dialog(frm, eligible);
  },

  async make_payment(frm) {
    if (frm.is_new()) {
      frappe.msgprint(__("Please save the document first."));
      return;
    }

    if (!frm.doc.clearing_file) {
      frappe.msgprint(__("Please set a Clearing File before making a payment."));
      return;
    }

    await ensure_manual_charge_disbursement_entries(frm);

    const jeResp = await frappe.call({
      method: "clearing.clearing.doctype.clearing_charges.clearing_charges.get_disbursement_journal_entries_detailed",
      args: { clearing_file: frm.doc.clearing_file },
    });
    const jeRows = jeResp.message || [];
    const invoiceRows = await get_outstanding_service_invoices(frm);

    if (!jeRows.length && !invoiceRows.length) {
      frappe.msgprint(
        __(
          "No outstanding Journal Entries or submitted Sales Invoices were found for this document."
        )
      );
      return;
    }

    open_payment_dialog(frm, jeRows, invoiceRows);
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
  let manual_total = 0;
  let invoice_total = 0;
  let non_invoice_total = 0;

  if (frm.doc.charges) {
    frm.doc.charges.forEach(function (charge) {
      const amount = flt(charge.amount || 0);
      const isInvoice = Number(charge.is_invoice) === 1;

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
      } else if (!isInvoice) {
        manual_total += amount;
      }

      if (!isInvoice) {
        non_invoice_total += amount;
      }

      if (isInvoice) {
        invoice_total += amount;
      }
    });
  }

  const total = non_invoice_total;
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

async function setup_disbursement_link_behaviour(frm) {
  if (!frm) {
    return;
  }

  if (!frm.__disbursement_behaviour_initialized) {
    configure_disbursement_query(frm);
    configure_disbursement_new_doc_defaults(frm);
    frm.__disbursement_behaviour_initialized = true;
  }

  await ensure_disbursement_defaults(frm);
}

function configure_disbursement_query(frm) {
  if (!frm || typeof frm.set_query !== "function") {
    return;
  }

  frm.set_query("disbursement", "charges", function (doc, cdt, cdn) {
    const row = (locals[cdt] && locals[cdt][cdn]) || null;
    if (!doc || !doc.clearing_file || !row) {
      return {
        filters: [["Journal Entry", "name", "=", "__invalid__"]],
      };
    }

    if (Number(row.is_invoice) === 1) {
      return {
        filters: [["Journal Entry", "name", "=", "__invalid__"]],
      };
    }

    const filters = {
      clearing_file: doc.clearing_file,
      docstatus: ["<", 2],
    };

    const lockedEntries = (doc.charges || [])
      .filter(
        (child) =>
          child &&
          child.name !== row.name &&
          child.disbursement &&
          child.disbursement !== row.disbursement
      )
      .map((child) => child.disbursement);
    if (lockedEntries.length) {
      filters.name = ["not in", lockedEntries];
    }

    if ((row.charge_type || "").trim()) {
      filters.user_remark = ["like", `${row.charge_type.trim()}%`];
    }

    return { filters };
  });
}

function configure_disbursement_new_doc_defaults(frm) {
  if (!frm || typeof frm.get_docfield !== "function") {
    return;
  }

  const disbursementField = frm.get_docfield("charges", "disbursement");
  if (!disbursementField) {
    return;
  }

  disbursementField.get_route_options_for_new_doc = (row) => {
    const charge = row && row.doc ? row.doc : null;
    if (!frm.doc.clearing_file || !charge || Number(charge.is_invoice) === 1) {
      return {};
    }

    const { headerRemark, accountRemark } = build_disbursement_user_remark(frm, charge);

    const routeOptions = {
      clearing_file: frm.doc.clearing_file,
      voucher_type: "Debit Note",
    };

    if (frappe.datetime && typeof frappe.datetime.nowdate === "function") {
      routeOptions.posting_date = frappe.datetime.nowdate();
    }

    if (headerRemark) {
      routeOptions.user_remark = headerRemark;
      routeOptions.remark = headerRemark;
    }

    const defaults =
      (frm.__disbursement_defaults && frm.__disbursement_defaults.defaults) || null;
    if (defaults) {
      if (defaults.company) {
        routeOptions.company = defaults.company;
      }
      routeOptions.voucher_type = defaults.voucher_type || routeOptions.voucher_type;
      const accountRows = build_disbursement_account_rows(
        defaults,
        charge,
        accountRemark,
        frm.doc
      );
      if (accountRows.length) {
        routeOptions.accounts = accountRows;
      }
    }

    return routeOptions;
  };
}

async function ensure_disbursement_defaults(frm) {
  const clearingFile = (frm.doc.clearing_file || "").trim();
  if (!clearingFile) {
    frm.__disbursement_defaults = null;
    frm.__disbursement_defaults_request = null;
    return null;
  }

  const cached = frm.__disbursement_defaults;
  if (cached && cached.clearing_file === clearingFile && cached.defaults) {
    return cached.defaults;
  }

  const pending = frm.__disbursement_defaults_request;
  if (pending && pending.clearing_file === clearingFile) {
    return pending.promise;
  }

  const promise = frappe
    .call({
      method:
        "clearing.clearing.doctype.clearing_charges.clearing_charges.get_disbursement_journal_entry_defaults",
      args: { clearing_file: clearingFile },
    })
    .then(({ message }) => {
      const defaults = message || null;
      frm.__disbursement_defaults = { clearing_file: clearingFile, defaults };
      return defaults;
    })
    .catch((error) => {
      console.error("Failed to load disbursement journal entry defaults", error);
      frm.__disbursement_defaults = { clearing_file: clearingFile, defaults: null };
      return null;
    })
    .finally(() => {
      frm.__disbursement_defaults_request = null;
    });

  frm.__disbursement_defaults_request = { clearing_file: clearingFile, promise };
  return promise;
}

function build_disbursement_user_remark(frm, charge) {
  const docLabel =
    (frm.doctype && typeof frm.doctype === "string" && frm.doctype.trim()) || "Clearing Charges";
  const docName = (frm.doc && frm.doc.name && frm.doc.name.trim()) || "";
  const clearingFile = (frm.doc.clearing_file || "").trim();
  const chargeType = (charge && charge.charge_type && charge.charge_type.trim()) || "";

  const coreParts = [];
  if (docName) {
    coreParts.push(`${docLabel}: ${docName}`);
  }
  if (clearingFile) {
    coreParts.push(`Clearing File ${clearingFile}`);
  }
  const accountRemark = coreParts.join(" | ");

  const headerParts = [];
  if (chargeType) {
    headerParts.push(chargeType);
  }
  if (accountRemark) {
    headerParts.push(accountRemark);
  }
  const headerRemark = headerParts.join(" | ");

  return { headerRemark, accountRemark };
}

function build_disbursement_account_rows(defaults, charge, remark, parentDoc) {
  if (!defaults || !charge) {
    return [];
  }

  const amount = Math.abs(flt(charge.amount || 0));
  if (amount <= 0) {
    return [];
  }

  const rows = [];
  const referenceType = parentDoc && parentDoc.doctype ? parentDoc.doctype : null;
  const referenceName = parentDoc && parentDoc.name ? parentDoc.name : null;
  const accountRemark = remark || null;

  if (defaults.party_account) {
    const debitRow = {
      doctype: "Journal Entry Account",
      account: defaults.party_account,
      debit_in_account_currency: amount,
      credit_in_account_currency: 0,
    };
    if (defaults.party_account_currency) {
      debitRow.account_currency = defaults.party_account_currency;
    }
    if (defaults.party_type) {
      debitRow.party_type = defaults.party_type;
    }
    if (defaults.party) {
      debitRow.party = defaults.party;
    }
    if (accountRemark) {
      debitRow.user_remark = accountRemark;
    }
    if (referenceType && referenceName) {
      debitRow.reference_type = referenceType;
      debitRow.reference_name = referenceName;
    }
    rows.push(debitRow);
  }

  if (defaults.bank_account) {
    const creditRow = {
      doctype: "Journal Entry Account",
      account: defaults.bank_account,
      debit_in_account_currency: 0,
      credit_in_account_currency: amount,
    };
    if (defaults.bank_account_currency) {
      creditRow.account_currency = defaults.bank_account_currency;
    }
    if (accountRemark) {
      creditRow.user_remark = accountRemark;
    }
    if (referenceType && referenceName) {
      creditRow.reference_type = referenceType;
      creditRow.reference_name = referenceName;
    }
    rows.push(creditRow);
  }

  return rows;
}

function get_journal_entry_eligible_charges(frm) {
  const currency =
    frm.doc.currency ||
    (frappe.boot && frappe.boot.sysdefaults && frappe.boot.sysdefaults.currency);

  return (frm.doc.charges || [])
    .filter((charge) => {
      if (!charge) {
        return false;
      }
      if (Number(charge.is_invoice) === 1) {
        return false;
      }
      if (CLEARANCE_SOURCE_NAMES.includes((charge.charge_type || "").trim())) {
        return false;
      }
      if (flt(charge.amount || 0) <= 0) {
        return false;
      }
      if (charge.disbursement) {
        return false;
      }
      return true;
    })
    .map((charge, index) => {
      const idx = charge.idx || index + 1;
      const key = charge.name || `charge-${idx}`;
      const amount = flt(charge.amount || 0);
      const label = `${charge.charge_type || __("Charge")} | ${format_currency(amount, currency)}`;
      return {
        key,
        idx,
        charge,
        label,
        amount,
        currency,
      };
    });
}

function open_make_jv_dialog(frm, eligibleCharges) {
  const valueMap = {};
  const options = eligibleCharges.map((entry) => {
    valueMap[entry.key] = entry.charge;
    return {
      label: entry.label,
      value: entry.key,
      checked: true,
    };
  });

  const dialog = new frappe.ui.Dialog({
    title: __("Create Journal Entries"),
    fields: [
      {
        fieldname: "charges",
        label: __("Charges"),
        fieldtype: "MultiCheck",
        options,
        reqd: 1,
        columns: "20rem",
      },
      {
        fieldname: "posting_date",
        label: __("Posting Date"),
        fieldtype: "Date",
        default: frappe.datetime && frappe.datetime.nowdate ? frappe.datetime.nowdate() : undefined,
      },
    ],
    primary_action_label: __("Create"),
    async primary_action(values) {
      const selected = (values.charges || []).filter(Boolean);
      if (!selected.length) {
        frappe.msgprint(__("Select at least one charge."));
        return;
      }

      const rows = selected
        .map((value) => valueMap[value])
        .filter((charge) => !!charge && !!charge.name);
      if (!rows.length) {
        frappe.msgprint(__("Unable to locate the selected charges. Please try again."));
        return;
      }

      dialog.hide();

      try {
        const response = await frappe.call({
          method:
            "clearing.clearing.doctype.clearing_charges.clearing_charges.make_disbursement_journal_entries",
          args: {
            clearing_charges: frm.doc.name,
            charges: rows.map((row) => row.name),
            posting_date: values.posting_date,
          },
          freeze: true,
          freeze_message: __("Creating Journal Entries..."),
        });

        const created = response.message || [];
        if (created.length) {
          const names = created.map((item) => item.journal_entry).join(", ");
          frappe.msgprint(
            __("Created Journal Entry {0}.", [names]),
            __("Success")
          );
        } else {
          frappe.msgprint(__("No Journal Entries were created."));
        }
        await frm.reload_doc();
      } catch (error) {
        console.error("Failed to create journal entries", error);
      }
    },
  });

  dialog.show();
}

function get_pending_manual_charge_names(frm) {
  return (frm.doc.charges || [])
    .filter((charge) => {
      if (!charge || !charge.name) {
        return false;
      }
      if (Number(charge.is_invoice) === 1) {
        return false;
      }
      if (CLEARANCE_SOURCE_NAMES.includes((charge.charge_type || "").trim())) {
        return false;
      }
      if (charge.disbursement) {
        return false;
      }
      return flt(charge.amount || 0) > 0;
    })
    .map((charge) => charge.name);
}

async function ensure_manual_charge_disbursement_entries(frm) {
  if (!frm || !frm.doc || !frm.doc.name) {
    return;
  }

  const pending = get_pending_manual_charge_names(frm);
  if (!pending.length) {
    return;
  }

  try {
    await frappe.call({
      method:
        "clearing.clearing.doctype.clearing_charges.clearing_charges.make_disbursement_journal_entries",
      args: {
        clearing_charges: frm.doc.name,
        charges: pending,
        posting_date:
          frappe.datetime && typeof frappe.datetime.nowdate === "function"
            ? frappe.datetime.nowdate()
            : undefined,
      },
      freeze: true,
      freeze_message: __("Preparing Journal Entries..."),
    });
    await frm.reload_doc();
  } catch (error) {
    console.error("Failed to create disbursement journals for manual charges", error);
    frappe.msgprint(
      __("Unable to prepare Journal Entries for the outstanding manual charges. Please try again.")
    );
  }
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
    async primary_action(values) {
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
      await create_invoice_from_charges(frm, charges, values.posting_date, dialog);
    },
  });

  dialog.show();
}

async function create_invoice_from_charges(frm, charges, postingDate, dialog) {
  const invoice = frappe.model.get_new_doc("Sales Invoice");
  const posting =
    postingDate ||
    (frappe.datetime && frappe.datetime.nowdate
      ? frappe.datetime.nowdate()
      : undefined);

  invoice.customer = frm.doc.consigee;
  invoice.clearing_charges = frm.doc.name;
  invoice.posting_date = posting;
  if (frm.doc.currency) {
    invoice.currency = frm.doc.currency;
  }
  if (Object.prototype.hasOwnProperty.call(invoice, "ignore_pricing_rule")) {
    invoice.ignore_pricing_rule = 1;
  }

  frappe.dom.freeze(__("Preparing Sales Invoice..."));
  try {
    let company = null;
    try {
      const defaults = await ensure_disbursement_defaults(frm);
      if (defaults && defaults.company) {
        company = defaults.company;
      }
    } catch (error) {
      console.error("Failed to fetch invoice company defaults", error);
    }
    if (!company && frappe.defaults && typeof frappe.defaults.get_user_default === "function") {
      company = frappe.defaults.get_user_default("Company");
    }
    if (company) {
      invoice.company = company;
    }

    let defaultIncomeAccount = null;
    if (company) {
      try {
        const { message } = await frappe.db.get_value(
          "Company",
          company,
          "default_income_account"
        );
        defaultIncomeAccount =
          message && typeof message === "object"
            ? message.default_income_account
            : message;
      } catch (error) {
        console.error("Failed to fetch company default income account", error);
      }
    }

    const missingRows = [];
    const tasks = [];

    (charges || []).forEach((charge, index) => {
      const row = frappe.model.add_child(invoice, "Sales Invoice Item", "items");
      const itemCode = ((charge && charge.charge_type) || "").trim();
      const qty = flt((charge && charge.quantity) || 1) || 1;
      const amount = flt((charge && charge.amount) || 0);

      row.item_code = itemCode;
      row.qty = qty;
      row.rate = qty ? amount / qty : amount;
      row.amount = amount;

      if (!itemCode) {
        missingRows.push(__("Row {0}: missing Item Code", [index + 1]));
        return;
      }

      tasks.push(
        frappe.db
          .get_value(
            "Item",
            itemCode,
            ["item_name", "description", "sales_uom", "stock_uom"]
          )
          .then(({ message }) => {
            const item = message || {};
            row.item_name = item.item_name || itemCode;
            row.description = item.description || item.item_name || itemCode;
            row.uom = item.sales_uom || item.stock_uom || row.uom || "Nos";
            row.income_account = row.income_account || defaultIncomeAccount || null;

            const missing = [];
            if (!row.uom) missing.push(__("UOM"));
            if (!row.income_account) missing.push(__("Income Account"));
            if (missing.length) {
              missingRows.push(__("{0}: {1}", [itemCode, missing.join(", ")]));
            }
          })
          .catch((error) => {
            console.error("Failed to fetch Item defaults", error);
            row.item_name = row.item_name || itemCode;
            row.description = row.description || itemCode;
            row.uom = row.uom || "Nos";
            if (!row.income_account && defaultIncomeAccount) {
              row.income_account = defaultIncomeAccount;
            }

            const missing = [];
            if (!row.uom) missing.push(__("UOM"));
            if (!row.income_account) missing.push(__("Income Account"));
            if (missing.length) {
              missingRows.push(__("{0}: {1}", [itemCode, missing.join(", ")]));
            }
          })
      );
    });

    await Promise.all(tasks);
    dialog.hide();
    frappe.set_route("Form", "Sales Invoice", invoice.name);

    if (missingRows.length) {
      frappe.msgprint(
        __("Some rows still need required values before Save:<br>{0}", [
          missingRows.join("<br>"),
        ])
      );
    }
  } finally {
    frappe.dom.unfreeze();
  }
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

function get_outstanding_service_invoice_total(frm) {
  return (frm.doc.clearing_services || []).reduce((total, row) => {
    if (!row || !row.reference_number) {
      return total;
    }
    return total + flt(row.outstanding_amount || 0);
  }, 0);
}

function has_outstanding_service_invoices(frm) {
  return get_outstanding_service_invoice_total(frm) > 0.000001;
}

async function get_outstanding_service_invoices(frm) {
  const invoiceNames = Array.from(
    new Set(
      (frm.doc.clearing_services || [])
        .map((row) => (row && row.reference_number ? row.reference_number : null))
        .filter((name) => !!name)
    )
  );

  if (!invoiceNames.length) {
    return [];
  }

  const resp = await frappe.call({
    method: "frappe.client.get_list",
    args: {
      doctype: "Sales Invoice",
      filters: {
        name: ["in", invoiceNames],
        docstatus: 1,
        outstanding_amount: [">", 0],
      },
      fields: ["name", "status", "grand_total", "outstanding_amount", "due_date"],
      limit_page_length: invoiceNames.length,
    },
  });

  const rows = resp.message || [];
  rows.sort((a, b) => (a.name || "").localeCompare(b.name || ""));
  return rows;
}

function open_payment_dialog(frm, rows, invoiceRows = []) {
  const includeServiceInvoices = !!invoiceRows.length;

  const currency =
    frm.doc.currency ||
    (frappe.boot && frappe.boot.sysdefaults && frappe.boot.sysdefaults.currency);

  const options = rows.map((row) => {
    const outstanding = flt(row.outstanding || 0);
    const labelParts = [row.journal_entry];
    if (row.item_label) {
      labelParts.push(row.item_label);
    }
    if (row.clearance_label) {
      labelParts.push(row.clearance_label);
    } else if (row.clearance_type) {
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

  const invoiceOptions = invoiceRows.map((row) => {
    const outstanding = flt(row.outstanding_amount || 0);
    const formattedOutstanding = format_currency(outstanding, currency);
    const labelParts = [row.name];
    labelParts.push(__("Outstanding: {0}", [formattedOutstanding]));
    if (row.status) {
      labelParts.push(row.status);
    }
    return {
      label: labelParts.join(" | "),
      value: row.name,
      outstanding,
      checked: false,
      description: __('Outstanding: {0}', [formattedOutstanding]),
    };
  });
  const invoiceByName = {};
  invoiceRows.forEach((row) => {
    invoiceByName[row.name] = row;
  });

  let dialog;
  dialog = new frappe.ui.Dialog({
    title: __("Make Payment"),
    fields: [
      {
        fieldname: "journal_entries",
        label: includeServiceInvoices
          ? __("Journal Entries (optional)")
          : __("Journal Entries"),
        fieldtype: "MultiCheck",
        options: options,
        columns: "20rem",
        select_all: true,
        sort_options: false,
        reqd: includeServiceInvoices ? 0 : 1,
      },
      {
        fieldname: "sales_invoices",
        label: __("Sales Invoices"),
        fieldtype: "MultiCheck",
        options: invoiceOptions,
        columns: "20rem",
        select_all: false,
        sort_options: false,
        reqd: 0,
        depends_on: includeServiceInvoices ? "eval:1" : "eval:0",
      },
      {
        fieldname: "amount_to_pay",
        label: __("Total Amount to Pay (optional)"),
        fieldtype: "Currency",
        description: __(
          "Leave blank to pay full outstanding for selected Journal Entries and Sales Invoices."
        ),
      },
    ],
    primary_action_label: __("Proceed"),
    primary_action(values) {
      const selectedValues = (values.journal_entries || []).filter(Boolean);
      const selectedInvoices = (values.sales_invoices || []).filter(Boolean);
      if (!selectedValues.length && !selectedInvoices.length) {
        frappe.msgprint(
          __("Please select at least one Journal Entry or Sales Invoice.")
        );
        return;
      }

      const selectedRows = selectedValues
        .map((name) => rowByName[name])
        .filter((row) => !!row);
      if (selectedValues.length && !selectedRows.length) {
        frappe.msgprint(__("The selected Journal Entries could not be found. Please try again."));
        return;
      }
      const selectedInvoiceRows = selectedInvoices
        .map((name) => invoiceByName[name])
        .filter((row) => !!row);
      if (selectedInvoices.length && !selectedInvoiceRows.length) {
        frappe.msgprint(__("The selected Sales Invoices could not be found. Please try again."));
        return;
      }

      const totalOutstanding =
        selectedRows.reduce((acc, row) => acc + flt(row.outstanding || 0), 0) +
        selectedInvoiceRows.reduce(
          (acc, row) => acc + flt(row.outstanding_amount || 0),
          0
        );
      if (totalOutstanding <= 0) {
        frappe.msgprint(
          __("The selected Journal Entries and Sales Invoices have no outstanding balance.")
        );
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
      const args = {
        journal_entries: selectedValues,
        sales_invoices: selectedInvoices,
        clearing_charges: frm.doc.name,
      };
      if (typeof amount === "number" && !Number.isNaN(amount)) {
        args.total_amount = amount;
      }
      frappe.call({
        method: "clearing.api.payment_entry.make_payment_entry_from_references",
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
