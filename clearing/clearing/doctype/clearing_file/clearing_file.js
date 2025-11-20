// Copyright (c) 2024, Nelson Mpanju and contributors
// For license information, please see license.txt

const TANCIS_FIELDS = [
  "tancis_lodging_date",
  "reference_no",
  "tansad_no",
  "declaration_type",
  "cl_plan",
  "awbbl_no",
];

const HEADLINE_PRIORITY = {
  red: 4,
  orange: 3,
  yellow: 2,
  blue: 1,
  green: 0,
};

const CLEARANCE_TYPES = ["TRA Clearance", "Shipping Line Clearance"];

frappe.ui.form.on("Clearing File", {
  refresh: function (frm) {
    reset_headline_messages(frm);

    // Check clearing documents status
    check_clearing_documents_status(frm);

    frm.__tancis_original = Object.fromEntries(
      TANCIS_FIELDS.map((field) => [field, frm.doc[field] || null])
    );
    frm.__tancis_warning_shown = false;

    TANCIS_FIELDS.forEach((field) => {
      const hasValue = !!frm.doc[field];
      const shouldLock = !frm.is_new() && hasValue;
      frm.set_df_property(field, "read_only", shouldLock ? 1 : 0);
    });

    frm.trigger("update_cargo_description");
    frm.trigger("update_total_container_summary");
    frm.trigger("bind_cargo_input_handlers");

    // Force refresh of submit button
    if (frm.doc.status === "Delivered") {
      frm.page
        .set_primary_action(__("Submit"), function () {
          frm.save("Submit");
        })
        .show();
    }

    // Show transit bond alert for IM8 declaration type when status is Delivered or submitted
    if (frm.doc.declaration_type === "IM8 TRANSIT AND TRANSHIPMENT" &&
        (frm.doc.status === "Delivered" || frm.doc.docstatus === 1) &&
        !frm.doc.bond_returned) {
      frm.set_intro(
        `<div style="padding:15px; background:#fff3cd; border:1px solid #ffeeba; border-radius:5px; color:#856404;">
          <strong>Transit Bond Alert:</strong><br>
          Transit Bond has not yet been returned for this IM8 TRANSIT AND TRANSHIPMENT declaration.
        </div>`,
        "yellow"
      );
    }

    if (frm.doc.status === "Delivered" && frm.doc.name) {
      frappe.call({
        method:
          "clearing.clearing.doctype.clearing_file.clearing_file.check_container_interchange_completion",
        args: { clearing_file: frm.doc.name },
        callback: function (r) {
          const data = r.message || {};
          const finalDone = !!data.final_done;
          const refundDone = !!data.refund_done;

          const pendingSteps = [];
          if (!finalDone) {
            pendingSteps.push(__("Final EIR"));
          }
          if (!refundDone) {
            pendingSteps.push(__("Container Deposit Refund"));
          }

          if (pendingSteps.length) {
            const message = __(
              "Pending Container Interchange record: {0}",
              [pendingSteps.join(", ")]
            );
            set_headline_message(frm, "container", message, "orange");
          } else {
            set_headline_message(frm, "container", null);
          }
        },
      });
    } else {
      set_headline_message(frm, "container", null);
    }
    // Update the "Attach Documents" button to be primary
    const container = document.querySelector(
      '[data-fieldname="attach_documents"]'
    );
    if (container) {
      const button = container.querySelector("button");
      if (button) {
        button.className = "btn btn-xs btn-default bold btn-primary";
      }
    }

    function handle_clearance_creation(
      doctype,
      label,
      filters,
      new_doc_data,
      success_message
    ) {
      frm.add_custom_button(
        __(label),
        function () {
          const proceed = () => {
            frappe.call({
              method: "frappe.client.get_list",
              args: {
                doctype: doctype,
                filters: filters,
                limit: 1,
              },
              callback: function (r) {
                if (r.message && r.message.length > 0) {
                  // Document exists, open it
                  frappe.set_route("Form", doctype, r.message[0].name);
                } else {
                  // Create a new unsaved document
                  let new_doc = frappe.model.get_new_doc(doctype);

                  // Set the basic fields
                  Object.assign(new_doc, new_doc_data);

                  if (!new_doc.posting_date) {
                    new_doc.posting_date = frappe.datetime.get_today();
                  }

                  // Open the new document form without saving
                  frappe.set_route("Form", doctype, new_doc.name);

                  frappe.msgprint(__(success_message + " Please fill in the required fields and save."));
                }
              },
            });
          };

          // Allow TRA & Shipping Line to start; require TRA before other clearances
          const requires_tra_first = [
            "Physical Verification",
            "Port Clearance",
          ].includes(doctype);

          if (requires_tra_first) {
            if (!CLEARANCE_TYPES.length) {
              proceed();
              return;
            }

            const checkClearance = (index = 0) => {
              const doctypeToCheck = CLEARANCE_TYPES[index];
              frappe.call({
                method: "frappe.client.get_list",
                args: {
                  doctype: doctypeToCheck,
                  filters: { clearing_file: frm.doc.name },
                  limit: 1,
                  fields: ["name"],
                },
                callback: function (r) {
                  const hasClearance = r.message && r.message.length > 0;
                  if (hasClearance) {
                    proceed();
                    return;
                  }

                  const nextIndex = index + 1;
                  if (nextIndex < CLEARANCE_TYPES.length) {
                    checkClearance(nextIndex);
                    return;
                  }

                  const requiredClearanceLabel = CLEARANCE_TYPES.join(" or ");
                  const requiredClearancePrompt = CLEARANCE_TYPES.length
                    ? `a ${requiredClearanceLabel}`
                    : __("a clearance record");

                  frappe.msgprint(
                    __(
                      "Please create {0} for this Clearing File before proceeding.",
                      [requiredClearancePrompt]
                    )
                  );
                },
                error: () => proceed(), // fallback to let server-side validation handle
              });
            };

            checkClearance();
          } else {
            proceed();
          }
        },
        null,
        "primary"
      ); // Make the button primary
    }

    if (frm.doc.status === "Pre-Lodged" || frm.doc.status === "On Process") {
      // TRA Clearance
      handle_clearance_creation(
        "TRA Clearance",
        "TRA Clearance",
        { clearing_file: frm.doc.name },
        {
          doctype: "TRA Clearance",
          clearing_file: frm.doc.name,
          customer: frm.doc.customer,
          status: "Payment Pending",
        },
        "TRA Clearance created successfully"
      );

      // Shipping Line Clearance (show regardless, server will enforce order)
      if (frm.doc.mode_of_transport !== "Air") {
        handle_clearance_creation(
          "Shipping Line Clearance",
          "Shipping Line Clearance",
          { clearing_file: frm.doc.name },
          {
            doctype: "Shipping Line Clearance",
            clearing_file: frm.doc.name,
            customer: frm.doc.customer,
            status: "Unpaid",
          },
          "Shipping Line Clearance created successfully"
        );
      }

      // Physical Verification
      handle_clearance_creation(
        "Physical Verification",
        "Physical Verification",
        { clearing_file: frm.doc.name },
        {
          doctype: "Physical Verification",
          clearing_file: frm.doc.name,
          customer: frm.doc.customer,
          status: "Payment Pending",
        },
        "Physical Verification created successfully"
      );

      // Port Clearance
      let port_clearance_data = {
        doctype: "Port Clearance",
        clearing_file: frm.doc.name,
        customer: frm.doc.customer,
        status: "Unpaid",
      };

      // Auto-check has_transit_bond for IM8 declaration type
      if (frm.doc.declaration_type === "IM8 TRANSIT AND TRANSHIPMENT") {
        port_clearance_data.has_transit_bond = 1;
      }

      handle_clearance_creation(
        "Port Clearance",
        "Port Clearance",
        { clearing_file: frm.doc.name },
        port_clearance_data,
        "Port Clearance created successfully"
      );
    }

    frm.fields_dict.mode_of_transport.df.onchange = () => {
      frm.refresh();
    };

    // Update button types for custom actions
    [
      "TRA Clearance",
      "Port Clearance",
      "Physical Verification",
      "Shipping Line Clearance",
    ].forEach((action) => {
      frm.change_custom_button_type(action, null, "primary");
    });
  },

  cargo_details_on_form_rendered: function (frm) {
    frm.trigger("bind_cargo_input_handlers");
  },

  validate: function (frm) {
    if (frm.__tancis_warning_shown) {
      return;
    }

    const originalValues = frm.__tancis_original || {};
    const newlyCaptured = TANCIS_FIELDS.filter((field) => {
      const before = originalValues[field];
      const current = frm.doc[field];
      return !before && !!current;
    });

    if (!newlyCaptured.length) {
      return;
    }

    frappe.validated = false;
    frappe.warn(
      __("Heads Up"),
      __("You cannot change TANCIS details after it has been set."),
      () => {
        frm.__tancis_warning_shown = true;
        frappe.validated = true;
        frm.save();
      },
      () => {
        frm.__tancis_warning_shown = false;
      },
      true
    );
  },

  attach_documents: function (frm) {
    // Check if the Clearing File is new and hasn't been saved
    if (frm.is_new()) {
      // Save the form automatically
      frm
        .save()
        .then(() => {
          proceedWithAttachmentDialog(frm);
        })
        .catch((err) => {
          frappe.msgprint(
            __("Error saving the Clearing File. Please try again.")
          );
          console.error("Error saving Clearing File:", err);
        });
    } else {
      proceedWithAttachmentDialog(frm);
    }
  },

  customer: function (frm) {
    if (frm.doc.customer) {
      frappe.call({
        method:
          "clearing.clearing.doctype.clearing_file.clearing_file.get_address_display_from_link",
        args: { doctype: "Customer", name: frm.doc.customer },
        callback: function (r) {
          if (r.message) {
            frm.set_value("address_display", r.message.address_display);
            frm.set_value("customer_address", r.message.customer_address);
          } else {
            frm.set_value("address_display", "");
            frm.set_value("customer_address", "");
          }
        },
      });
    } else {
      frm.set_value("address_display", "");
      frm.set_value("customer_address", "");
    }
  },

  update_cargo_description: function (frm) {
    let descriptions = frm.doc.cargo_details
      .map((row) => row.cargo_description)
      .filter(Boolean);
    frm.set_value("cargo_description", descriptions.join("\n"));
  },

  bind_cargo_input_handlers: function (frm) {
    const cargoField = frm.fields_dict && frm.fields_dict.cargo_details;
    if (!cargoField || !cargoField.grid) {
      return;
    }

    const grid = cargoField.grid;
    const wrapper = $(grid.wrapper);
    wrapper.off(".cargo-count");

    const handler = () => {
      setTimeout(() => frm.trigger("update_total_container_summary"), 50);
    };

    ["container_number", "hs_code"].forEach((fieldname) => {
      wrapper.on(
        "change.cargo-count input.cargo-count",
        `[data-fieldname="${fieldname}"]`,
        handler
      );
    });
  },

  update_total_container_summary: function (frm) {
    const allowUpdate = frm.doc.docstatus !== 1;
    let totalContainers = 0;
    let totalHsCodes = 0;
    const splitPattern = /[\s,;]+/;

    (frm.doc.cargo_details || []).forEach((row) => {
      const containerRaw = (row.container_number || "").trim();
      const containerCount = containerRaw
        ? containerRaw.split(splitPattern).filter(Boolean).length
        : 0;
      totalContainers += containerCount;

      const existingContainer = Number(row.quantity_of_container) || 0;
      if (allowUpdate && existingContainer !== containerCount) {
        frappe.model.set_value(row.doctype, row.name, "quantity_of_container", containerCount);
      }

      const hsRaw = (row.hs_code || "").trim();
      const hsCount = hsRaw ? hsRaw.split(splitPattern).filter(Boolean).length : 0;
      totalHsCodes += hsCount;

      const existingHs = Number(row.quantity_of_hs_code) || 0;
      if (allowUpdate && existingHs !== hsCount) {
        frappe.model.set_value(row.doctype, row.name, "quantity_of_hs_code", hsCount);
      }
    });

    const totalText = String(totalContainers || 0);
    if (allowUpdate && (frm.doc.total_container_summary || "0") !== totalText) {
      frm.set_value("total_container_summary", totalText);
    } else if (!allowUpdate) {
      frm.refresh_field("total_container_summary");
    }

    if (frm.fields_dict && frm.fields_dict.total_hs_code_summary) {
      const totalHsText = String(totalHsCodes || 0);
      if (allowUpdate) {
        if ((frm.doc.total_hs_code_summary || "0") !== totalHsText) {
          frm.set_value("total_hs_code_summary", totalHsText);
        }
      } else {
        frm.refresh_field("total_hs_code_summary");
      }
    }
  },

  cargo_details_add: function (frm) {
    frm.trigger("update_total_container_summary");
    frm.trigger("bind_cargo_input_handlers");
  },

  cargo_details_remove: function (frm) {
    frm.trigger("update_total_container_summary");
    frm.trigger("update_cargo_description");
    frm.trigger("bind_cargo_input_handlers");
  },

  after_save: function (frm) {
    frm.trigger("update_cargo_description");
    frm.trigger("update_total_container_summary");
  },
});

frappe.ui.form.on("Cargo Details", {
  cargo_description: function (frm) {
    frm.trigger("update_cargo_description");
  },
});

frappe.ui.form.on("Cargo", {
  package_type: function (frm, cdt, cdn) {
    var row = locals[cdt][cdn];
    var container_number_df = frappe.meta.get_docfield(
      "Cargo",
      "container_number",
      frm.doc.name
    );
    var seal_number_df = frappe.meta.get_docfield(
      "Cargo",
      "seal_number",
      frm.doc.name
    );

    if (row.package_type === "Loose") {
      frappe.model.set_value(cdt, cdn, "container_number", "");
      frappe.model.set_value(cdt, cdn, "seal_number", "");
      container_number_df.hidden = 1;
      seal_number_df.hidden = 1;
    } else {
      container_number_df.hidden = 0;
      seal_number_df.hidden = 0;
    }

    frm.fields_dict.cargo_details.grid.toggle_display(
      "container_number",
      !container_number_df.hidden
    );
    frm.fields_dict.cargo_details.grid.toggle_display(
      "seal_number",
      !seal_number_df.hidden
    );
    frm.fields_dict.cargo_details.grid.refresh();
    frm.trigger("update_total_container_summary");
    frm.trigger("bind_cargo_input_handlers");
  },

  quantity_of_container: function (frm) {
    frm.trigger("update_total_container_summary");
    frm.trigger("bind_cargo_input_handlers");
  },
  quantity_of_hs_code: function (frm) {
    frm.trigger("update_total_container_summary");
    frm.trigger("bind_cargo_input_handlers");
  },
});

// Function to handle the attachment dialog process
function proceedWithAttachmentDialog(frm) {
  let d = new frappe.ui.Dialog({
    title: "Attach Clearing Document",
    fields: [
      {
        label: "Document Type",
        fieldname: "document_type",
        fieldtype: "Link",
        options: "Clearing Document Type",
        change: function () {
          let document_type = d.get_value("document_type");
          if (document_type) {
            frappe.call({
              method: "frappe.client.get",
              args: {
                doctype: "Clearing Document Type",
                name: document_type,
              },
              callback: function (r) {
                if (r.message && r.message.clearing_document_attribute) {
                  let attributes_table = d.get_field(
                    "document_attributes"
                  ).grid;
                  attributes_table.df.data = []; // Clear existing data
                  attributes_table.refresh();

                  // Populate table with attributes
                  r.message.clearing_document_attribute.forEach(
                    (aattribute) => {
                      d.fields_dict.document_attributes.df.data.push({
                        attribute: aattribute.document_attribute,
                        mandatory: aattribute.mandatory,
                        value: "",
                      });
                    }
                  );
                  attributes_table.refresh();
                } else {
                  frappe.msgprint(
                    __("No attributes found for the selected document type.")
                  );
                }
              },
              error: function () {
                frappe.msgprint(
                  __(
                    "Failed to retrieve document attributes. Please try again."
                  )
                );
              },
            });
          }
        },
      },
      { fieldname: "attach_document", fieldtype: "Column Break" },
      {
        label: "Attach Document",
        fieldname: "attach_document",
        fieldtype: "Attach",
      },
      { fieldname: "attach_document", fieldtype: "Section Break" },
      {
        label: "Document Attributes",
        fieldname: "document_attributes",
        fieldtype: "Table",
        options: "Clearing Document Attribute",
        fields: [
          {
            fieldname: "attribute",
            label: "Attribute",
            fieldtype: "Data",
            in_list_view: 1,
          },
          {
            fieldname: "value",
            label: "Value",
            fieldtype: "Data",
            in_list_view: 1,
          },
          {
            fieldname: "mandatory",
            label: "Mandatory",
            fieldtype: "Check",
            in_list_view: 1,
            read_only: 1,
          },
        ],
      },
    ],
    size: "large",
    primary_action_label: "Submit",
    primary_action: function (values) {
      // Validation: Check if mandatory fields have values
      let invalid = false;
      values.document_attributes.forEach((attr) => {
        if (attr.mandatory && !attr.value) {
          invalid = true;
          frappe.msgprint({
            title: __("Missing Value"),
            message: `Please fill the value for ${attr.attribute} as it is mandatory.`,
            indicator: "red",
          });
        }
      });

      // If validation fails, stop submission
      if (invalid) return;

      // Prepare the child table data
      let clearing_document_attributes = values.document_attributes.map(
        (attr) => ({
          document_attribute: attr.attribute,
          document_attribute_value: attr.value,
          mandatory: attr.mandatory,
        })
      );

      // Get the attachment URL
      let attachment_url = document
        .querySelector(".attached-file-link")
        .getAttribute("href");

      // Use Frappe API to create the document
      frappe.call({
        method: "frappe.client.insert",
        args: {
          doc: {
            doctype: "Clearing Document",
            clearing_file: frm.doc.name,
            document_attachment: attachment_url, // Attach document here
            clearing_document_type: values.document_type,
            document_type: values.document_type,
            clearing_document_attributes: clearing_document_attributes, // Handle child table
          },
        },
        callback: function (response) {
          if (response && response.message) {
            frappe.msgprint(__("Clearing Document created successfully."));
            d.hide();
            // Refresh the form to update document list and check transit status
            frm.reload_doc();
          } else {
            console.error("Failed to create Clearing Document.");
            frappe.msgprint(
              __(
                "There was an issue creating the Clearing Document. Please try again."
              )
            );
          }
        },
        error: function (err) {
          console.error("Error during document creation:", err);
          frappe.msgprint(
            __("Failed to create Clearing Document. Please try again.")
          );
        },
      });
    },
  });

  // Set a query to filter "Document Type" where linked_document = "Clearing File"
  d.fields_dict.document_type.get_query = function () {
    return {
      filters: {
        linked_document: "Clearing File",
      },
    };
  };

  d.show();
}

// Handle declaration type change
frappe.ui.form.on("Clearing File", {
  declaration_type: function(frm) {
    if (frm.doc.declaration_type === "IM8 TRANSIT AND TRANSHIPMENT") {
      frappe.msgprint({
        title: __("Transit Bond Notice"),
        message: __("IM8 TRANSIT AND TRANSHIPMENT declaration type selected. Transit Bond will be automatically checked in related Port Clearance documents."),
        indicator: "blue"
      });
    }
  },

  bond_returned: function(frm) {
    // Clear any transit bond alerts when bond is marked as returned
    if (frm.doc.bond_returned && frm.doc.declaration_type === "IM8 TRANSIT AND TRANSHIPMENT") {
      frm.set_intro("");
    }
  },

  mode_of_transport: function(frm) {
    // Refresh clearing document status when mode of transport changes
    check_clearing_documents_status(frm);
  }
});

// Trigger document check when documents are added/removed
frappe.ui.form.on("Clearing File Document", {
  document_name: function(frm) {
    check_clearing_documents_status(frm);
  },

  clearing_file_document_remove: function(frm) {
    setTimeout(() => check_clearing_documents_status(frm), 100);
  }
});

function get_required_clearing_documents_js(mode_of_transport) {
  const base_required_docs = [
    "Authorization Letter",
    "Commercial Invoice",
    "Packing List",
  ];

  if (mode_of_transport === "Air") {
    return [...base_required_docs, "Air Waybill (AWB)"];
  }

  if (mode_of_transport === "Sea") {
    return [...base_required_docs, "Bill of Lading B/L"];
  }

  return [...base_required_docs, "Air Waybill (AWB)"];
}

function check_clearing_documents_status(frm) {
  if (!frm || !frm.doc) {
    return;
  }

  // Only show the attach-docs headline after the Clearing File is saved
  if (frm.is_new && frm.is_new()) {
    set_headline_message(frm, "docs", null);
    return;
  }

  if (!frm.doc.mode_of_transport) {
    set_headline_message(frm, "docs", null);
    return;
  }

  const requiredDocs = get_required_clearing_documents_js(frm.doc.mode_of_transport);
  const attachedDocs = (frm.doc.document || [])
    .map((row) => row.document_name)
    .filter(Boolean);

  const missingDocs = requiredDocs.filter(
    (doc) => !attachedDocs.includes(doc)
  );

  if (missingDocs.length) {
    set_headline_message(
      frm,
      "docs",
      __("Attach the following clearing documents to move this Clearing File to 'Open': {0}", [
        missingDocs.join(", "),
      ]),
      "yellow"
    );
    frm.__all_docs_alert_shown = false;
  } else {
    set_headline_message(frm, "docs", null);
    if (!frm.__all_docs_alert_shown) {
      frappe.show_alert(
        {
          message: __("All required clearing documents are attached."),
          indicator: "green",
        },
        5
      );
      frm.__all_docs_alert_shown = true;
    }
  }
}

function reset_headline_messages(frm) {
  if (!frm) {
    return;
  }

  frm.__headline_messages = {};

  if (frm.dashboard) {
    frm.dashboard.clear_headline();
    frm.dashboard.clear_comment && frm.dashboard.clear_comment();
  }
}

function set_headline_message(frm, key, message, indicator = "yellow") {
  if (!frm) {
    return;
  }

  if (!frm.__headline_messages) {
    frm.__headline_messages = {};
  }

  if (message) {
    let normalizedIndicator = "yellow";
    if (typeof indicator === "string") {
      normalizedIndicator = indicator.toLowerCase();
    }

    frm.__headline_messages[key] = {
      message,
      indicator: normalizedIndicator,
    };
  } else if (frm.__headline_messages[key]) {
    delete frm.__headline_messages[key];
  }

  refresh_headline_messages(frm);
}

function refresh_headline_messages(frm) {
  if (!frm || !frm.dashboard) {
    return;
  }

  const entries = Object.values(frm.__headline_messages || {});

  if (!entries.length) {
    frm.dashboard.clear_headline();
    frm.dashboard.clear_comment && frm.dashboard.clear_comment();
    return;
  }

  frm.dashboard.clear_headline();
  frm.dashboard.clear_comment && frm.dashboard.clear_comment();

  const indicator = entries.reduce((current, entry) => {
    const color = entry.indicator || "yellow";
    if (!current) {
      return color;
    }

    return (HEADLINE_PRIORITY[color] || 0) >= (HEADLINE_PRIORITY[current] || 0)
      ? color
      : current;
  }, null);

  const html = entries
    .map((entry) => `<div>${entry.message}</div>`)
    .join("");

  frm.dashboard.set_headline_alert(html, indicator || "yellow");
}
