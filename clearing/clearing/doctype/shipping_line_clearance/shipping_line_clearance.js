// Copyright (c) 2024, Nelson Mpanju and contributors
// For license information, please see license.txt

frappe.require("/assets/clearing/js/stage_journal.js");

frappe.ui.form.on("Shipping Line Clearance", {
  refresh: function (frm) {
    handleDocumentExpiry(frm);
    customizeAttachDocumentsButton();
    frm.trigger("populate_container_fields");

    if (frm.doc.clearing_file) {
      // Fetch clearing file data to get declaration type
      frappe.call({
        method: "frappe.client.get",
        args: {
          doctype: "Clearing File",
          name: frm.doc.clearing_file,
        },
        callback: function (r) {
          if (r.message) {
            handle_clearance_creation(
              frm,
              "TRA Clearance",
              "TRA Clearance",
              { clearing_file: frm.doc.clearing_file },
              {
                doctype: "TRA Clearance",
                clearing_file: frm.doc.clearing_file,
                customer: frm.doc.customer,
                status: "Payment Pending",
              },
              "TRA Clearance created successfully"
            );

            handle_clearance_creation(
              frm,
              "Physical Verification",
              "Physical Verification",
              { clearing_file: frm.doc.clearing_file },
              {
                doctype: "Physical Verification",
                clearing_file: frm.doc.clearing_file,
                customer: frm.doc.customer,
                status: "Payment Pending",
              },
              "Physical Verification created successfully"
            );

            // Port Clearance with transit bond logic
            let port_clearance_data = {
              doctype: "Port Clearance",
              clearing_file: frm.doc.clearing_file,
              customer: frm.doc.customer,
              status: "Unpaid",
            };

            // Auto-check has_transit_bond for IM8 declaration type
            if (r.message.declaration_type === "IM8 TRANSIT AND TRANSHIPMENT") {
              port_clearance_data.has_transit_bond = 1;
            }

            handle_clearance_creation(
              frm,
              "Port Clearance",
              "Port Clearance",
              { clearing_file: frm.doc.clearing_file },
              port_clearance_data,
              "Port Clearance created successfully"
            );
          }
        },
      });
    }
  },

  attach_documents: async function (frm) {
    if (frm.doc.__unsaved) {
      frappe.msgprint(
        __("Please save the document before attaching documents.")
      );
      return;
    }

    await openDocumentAttachmentDialog(frm);
  },

  async make_journal(frm) {
    await frappe.require("/assets/clearing/js/stage_journal.js");
    await clearing.stageJournal.handle(frm, {
      tableField: "shipping_charges",
      serverMethod:
        "clearing.clearing.doctype.shipping_line_clearance.shipping_line_clearance.make_journal_entries",
    });
  },

  clearing_file: function (frm) {
    frm.trigger("populate_container_fields");
  },

  populate_container_fields: function (frm) {
    if (frm.doc.docstatus === 1) {
      return;
    }

    if (!frm.doc.clearing_file) {
      if (frm.doc.container_no) {
        frm.set_value("container_no", "");
      }
      if (frm.doc.port_of_loading) {
        frm.set_value("port_of_loading", "");
      }
      if (frm.doc.port_of_discharge) {
        frm.set_value("port_of_discharge", "");
      }
      return;
    }

    frappe.call({
      method: "clearing.clearing.doctype.shipping_line_clearance.shipping_line_clearance.get_cargo_container_data",
      args: { clearing_file: frm.doc.clearing_file },
      callback(r) {
        if (!r.message) {
          return;
        }

        const data = r.message;

        if (
          Object.prototype.hasOwnProperty.call(data, "container_no") &&
          (frm.doc.container_no || "") !== (data.container_no || "")
        ) {
          frm.set_value("container_no", data.container_no || "");
        }
        if (
          Object.prototype.hasOwnProperty.call(data, "port_of_loading") &&
          (frm.doc.port_of_loading || "") !== (data.port_of_loading || "")
        ) {
          frm.set_value("port_of_loading", data.port_of_loading || "");
        }
        if (
          Object.prototype.hasOwnProperty.call(data, "port_of_discharge") &&
          (frm.doc.port_of_discharge || "") !== (data.port_of_discharge || "")
        ) {
          frm.set_value("port_of_discharge", data.port_of_discharge || "");
        }
        if (
          Object.prototype.hasOwnProperty.call(data, "package_type") &&
          (frm.doc.package_type || "") !== (data.package_type || "")
        ) {
          frm.set_value("package_type", data.package_type || "");
        }
        if (
          Object.prototype.hasOwnProperty.call(data, "weight") &&
          (frm.doc.weight || "") !== (data.weight || "")
        ) {
          frm.set_value("weight", data.weight || "");
        }
        if (
          Object.prototype.hasOwnProperty.call(data, "volume") &&
          (frm.doc.volume || "") !== (data.volume || "")
        ) {
          frm.set_value("volume", data.volume || "");
        }
      },
    });
  },
});

function handle_clearance_creation(
  frm,
  doctype,
  label,
  filters,
  new_doc_data,
  success_message
) {
  frm.add_custom_button(
    __(label),
    function () {
      frappe.call({
        method: "frappe.client.get_list",
        args: { doctype: doctype, filters: filters, limit: 1 },
        callback: function (r) {
          if (r.message?.length > 0) {
            // Document exists, open it
            frappe.set_route("Form", doctype, r.message[0].name);
          } else {
            // Create a new unsaved document
            let new_doc = frappe.model.get_new_doc(doctype);

            // Set the basic fields
            Object.assign(new_doc, new_doc_data);

            // Open the new document form without saving
            frappe.set_route("Form", doctype, new_doc.name);

            frappe.msgprint(__(success_message + " Please fill in the required fields and save."));
          }
        },
      });
    },
    null,
    "primary"
  );
}

function handleDocumentExpiry(frm) {
  if (!frm.doc.delivery_order_expire_date) return;

  const expiryDate = new Date(frm.doc.delivery_order_expire_date);
  const today = new Date();
  const dayDiff = Math.ceil((expiryDate - today) / (1000 * 3600 * 24));

  if (expiryDate < today) {
    frm.set_intro(
      `
      <div style="padding:15px; background:#f8d7da; border:1px solid #f5c6cb; border-radius:5px; color:#721c24;">
        <strong>Important Notice:</strong><br>
        Delivery Order expired on ${expiryDate.toLocaleDateString()}.
      </div>
    `,
      "red"
    );
  } else if (dayDiff === 1) {
    frm.set_intro(
      `
      <div style="padding:15px; background:#fff3cd; border:1px solid #ffeeba; border-radius:5px; color:#856404;">
        <strong>Reminder:</strong><br>
        Delivery Order expires tomorrow (${expiryDate.toLocaleDateString()}).
      </div>
    `,
      "yellow"
    );
  }
}

function customizeAttachDocumentsButton() {
  const container = document.querySelector(
    '[data-fieldname="attach_documents"]'
  );
  if (container) {
    const button = container.querySelector("button");
    if (button) button.className = "btn btn-xs btn-default bold btn-primary";
  }
}


async function openDocumentAttachmentDialog(frm) {
  if (frm.is_new()) {
    await frm.save();
  }

  const d = new frappe.ui.Dialog({
    title: "Attach Document",
    fields: getDialogFields(frm),
    size: "large",
    primary_action_label: "Submit",
    primary_action(values) {
      const attributes = values.document_attributes || [];
      const invalid = attributes.some((attr) => attr.mandatory && !attr.value);
      if (invalid) {
        frappe.msgprint("Fill all mandatory attributes.");
        return;
      }

      const attachment_url = d.get_value("attach_document");
      if (!attachment_url) {
        frappe.msgprint("Attach a file first!");
        return;
      }

      frappe.call({
        method: "frappe.client.insert",
        args: {
          doc: {
            doctype: "Clearing Document",
            clearing_file: frm.doc.clearing_file,
            document_attachment: attachment_url,
            linked_file: "Shipping Line Clearance",
            document_type: values.document_type,
            clearing_document_attributes: attributes.map((attr) => ({
              document_attribute: attr.attribute,
              document_attribute_value: attr.value,
              mandatory: attr.mandatory,
            })),
          },
        },
        callback() {
          frappe.msgprint("Document attached successfully!");
          d.hide();
          frm.reload_doc();
        },
      });
    },
  });

  const attach_field = d.get_field("attach_document");
  if (attach_field) {
    attach_field.df.options = Object.assign({}, attach_field.df.options, {
      doctype: frm.doctype,
      docname: frm.doc.name,
    });
    attach_field.refresh();
  }

  d.fields_dict.document_type.get_query = () => ({
    filters: { linked_document: "Shipping Line Clearance" },
  });

  d.show();
}

function getDialogFields(frm) {
  return [
    {
      label: "Document Type",
      fieldname: "document_type",
      fieldtype: "Link",
      options: "Clearing Document Type",
      change: function () {
        const document_type = this.get_value();
        if (!document_type) return;

        const dialog = frappe.ui.get_open_dialog();
        if (!dialog) return;

        frappe.call({
          method: "frappe.client.get",
          args: { doctype: "Clearing Document Type", name: document_type },
          callback: function (r) {
            const attributes_table = dialog.get_field("document_attributes").grid;
            attributes_table.df.data = (
              r.message?.clearing_document_attribute || []
            ).map((attr) => ({
              attribute: attr.document_attribute,
              mandatory: attr.mandatory,
              value: "",
            }));
            attributes_table.refresh();
          },
        });
      },
    },
    { fieldname: "col_break", fieldtype: "Column Break" },
    {
      label: "Attach File",
      fieldname: "attach_document",
      fieldtype: "Attach",
      reqd: 1,
      options: frm
        ? {
            doctype: frm.doctype,
            docname: frm.doc && frm.doc.name,
          }
        : undefined,
    },
    { fieldname: "section_break", fieldtype: "Section Break" },
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
  ];
}
