// Copyright (c) 2024, Nelson Mpanju and contributors
// For license information, please see license.txt

frappe.ui.form.on("Shipping Line Clearance", {
  refresh: function (frm) {
    handleDocumentExpiry(frm);
    customizeAttachDocumentsButton();

    if (frm.doc.clearing_file) {
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

      handle_clearance_creation(
        frm,
        "Port Clearance",
        "Port Clearance",
        { clearing_file: frm.doc.clearing_file },
        {
          doctype: "Port Clearance",
          clearing_file: frm.doc.clearing_file,
          customer: frm.doc.customer,
          status: "Unpaid",
        },
        "Port Clearance created successfully"
      );
    }
  },

  attach_documents: function (frm) {
    openDocumentAttachmentDialog(frm);
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
            frappe.set_route("Form", doctype, r.message[0].name);
            if (frm.doc.status === "Pre-Lodged")
              frm.set_value("status", "On Process").save_or_update();
          } else {
            frappe.call({
              method: "frappe.client.insert",
              args: { doc: new_doc_data },
              callback: function (r) {
                if (!r.exc) {
                  frappe.msgprint(__(success_message));
                  frappe.set_route("Form", doctype, r.message.name);
                  frm.set_value("status", "On Process").save_or_update();
                }
              },
            });
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

function openDocumentAttachmentDialog(frm) {
  const d = new frappe.ui.Dialog({
    title: "Attach Document",
    fields: getDialogFields(),
    size: "large",
    primary_action_label: "Submit",
    primary_action: function (values) {
      frappe.call({
        method: "frappe.client.get_list",
        args: {
          doctype: "Clearing Document",
          filters: {
            clearing_file: frm.doc.clearing_file,
            document_type: values.document_type,
            linked_file: "Shipping Line Clearance",
          },
        },
        callback: function (r) {
          if (r.message?.length > 0) {
            frappe.throw(__("Document already attached!"));
            return;
          }

          const invalid = values.document_attributes.some(
            (attr) => attr.mandatory && !attr.value
          );
          if (invalid) {
            frappe.msgprint(__("Fill all mandatory attributes."));
            return;
          }

          const attachment_url = d.get_value("attach_document");
          if (!attachment_url) {
            frappe.msgprint(__("Attach a file first!"));
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
                clearing_document_attributes: values.document_attributes.map(
                  (attr) => ({
                    document_attribute: attr.attribute,
                    document_attribute_value: attr.value,
                    mandatory: attr.mandatory,
                  })
                ),
              },
            },
            callback: function () {
              frappe.msgprint(__("Document attached successfully!"));
              d.hide();
              frm.refresh();
            },
          });
        },
      });
    },
  });

  d.fields_dict.document_type.get_query = () => ({
    filters: { linked_document: "Shipping Line Clearance" },
  });
  d.show();
}

function getDialogFields() {
  return [
    {
      label: "Document Type",
      fieldname: "document_type",
      fieldtype: "Link",
      options: "Clearing Document Type",
      change: function () {
        const document_type = this.get_value();
        if (!document_type) return;

        frappe.call({
          method: "frappe.client.get",
          args: { doctype: "Clearing Document Type", name: document_type },
          callback: function (r) {
            const attributes_table = cur_dialog.get_field(
              "document_attributes"
            ).grid;
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
