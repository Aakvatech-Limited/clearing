// Copyright (c) 2024, Nelson Mpanju and contributors
// For license information, please see license.txt

frappe.ui.form.on('Shipment Clearance', {
    refresh: function (frm) {
        // Display alert based on the document's expiration status
        handleDocumentExpiry(frm);

        // Modify the class of the 'Attach Documents' button, if present
        customizeAttachDocumentsButton();

        // Fetch the Clearing File document to get its status
        if (frm.doc.clearing_file) {
            frappe.call({
                method: "frappe.client.get",
                args: {
                    doctype: "Clearing File",
                    name: frm.doc.clearing_file
                },
                callback: function (r) {
                    if (r.message) {
                        const clearing_file_status = r.message.status;

                        // Add conditional buttons based on the Clearing File status
                        if (clearing_file_status === 'Pre-Lodged' || clearing_file_status === 'On Process') {
                            // TRA Clearance button
                            handle_clearance_creation(
                                'TRA Clearance', 'TRA Clearance',
                                { clearing_file: frm.doc.clearing_file },
                                { doctype: 'TRA Clearance', clearing_file: frm.doc.clearing_file, customer: frm.doc.customer, status: 'Payment Pending' },
                                'TRA Clearance created successfully'
                            );

                            // Physical Verification button
                            handle_clearance_creation(
                                'Physical Verification', 'Physical Verification',
                                { clearing_file: frm.doc.clearing_file },
                                { doctype: 'Physical Verification', clearing_file: frm.doc.clearing_file, customer: frm.doc.customer, status: 'Payment Pending' },
                                'Physical Verification created successfully'
                            );

                            // Port Clearance button
                            handle_clearance_creation(
                                'Port Clearance', 'Port Clearance',
                                { clearing_file: frm.doc.clearing_file },
                                { doctype: 'Port Clearance', clearing_file: frm.doc.clearing_file, customer: frm.doc.customer, status: 'Unpaid' },
                                'Port Clearance created successfully'
                            );
                        }

                        // Update button types for custom actions
                        ['TRA Clearance', 'Physical Verification', 'Port Clearance'].forEach(action => {
                            frm.change_custom_button_type(action, null, 'primary');
                        });
                    }
                }
            });
        }
    },

    attach_documents: function (frm) {
        // Trigger the dialog for document attachment
        openDocumentAttachmentDialog(frm);
    }
});

/**
 * Helper function to create or redirect to documents.
 */
function handle_clearance_creation(doctype, label, filters, new_doc_data, success_message) {
    cur_frm.add_custom_button(__(label), function () {
        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: doctype,
                filters: filters,
                limit: 1
            },
            callback: function (r) {
                if (r.message && r.message.length > 0) {
                    frappe.set_route('Form', doctype, r.message[0].name);

                    if (cur_frm.doc.status === 'Pre-Lodged') {
                        cur_frm.set_value('status', 'On Process');
                        cur_frm.save_or_update();
                    }
                } else {
                    // Create a new document if it doesn't exist
                    frappe.call({
                        method: "frappe.client.insert",
                        args: { doc: new_doc_data },
                        callback: function (r) {
                            if (!r.exc) {
                                frappe.msgprint(__(success_message));
                                frappe.set_route('Form', doctype, r.message.name);

                                cur_frm.set_value('status', 'On Process');
                                cur_frm.save_or_update();
                            }
                        }
                    });
                }
            }
        });
    }, null, 'primary'); // Make the button primary
}

/**
 * Handle document expiration and display appropriate alert messages.
 */
function handleDocumentExpiry(frm) {
    const expiryDate = new Date(frm.doc.delivery_order_expire_date);
    const today = new Date();

    // Calculate the difference in days between today and the expiry date
    const timeDiff = expiryDate.getTime() - today.getTime();
    const dayDiff = Math.ceil(timeDiff / (1000 * 3600 * 24));

    // Show red alert if the document is expired
    if (expiryDate < today) {
        frm.set_intro(`
            <div style="padding: 15px; background-color: #f8d7da; border: 1px solid #f5c6cb; border-radius: 5px; color: #721c24; font-size: 14px;">
                <strong>Important Notice:</strong><br>
                Delivery Order Attached is <strong>expired</strong> as of <strong>${expiryDate.toLocaleDateString()}</strong>.
                Please take the necessary actions.
            </div>
        `, 'red');
    }
    // Show yellow alert if the document will expire tomorrow
    else if (dayDiff === 1) {
        frm.set_intro(`
            <div style="padding: 15px; background-color: #fff3cd; border: 1px solid #ffeeba; border-radius: 5px; color: #856404; font-size: 14px;">
                <strong>Reminder:</strong><br>
                Delivery Order Attached will <strong>expire</strong> tomorrow on <strong>${expiryDate.toLocaleDateString()}</strong>.
                Please take the necessary actions.
            </div>
        `, 'yellow');
    }
}

/**
 * Customize the 'Attach Documents' button to apply specific styles.
 */
function customizeAttachDocumentsButton() {
    const container = document.querySelector('[data-fieldname="attach_documents"]');
    if (container) {
        const button = container.querySelector('button');
        if (button) {
            // Apply custom styling to the button
            button.className = 'btn btn-xs btn-default bold btn-primary';
        }
    }
}

/**
 * Open a dialog to allow users to attach documents and fill in attributes.
 */
function openDocumentAttachmentDialog(frm) {
    let d = new frappe.ui.Dialog({
        title: 'Enter details',
        fields: getDialogFields(),
        size: 'large',
        primary_action_label: 'Submit',
        primary_action(values) {
            submitDocumentAttachment(frm, values, d);
        }
    });

    d.show();
}

/**
 * Returns the field structure for the document attachment dialog.
 */
function getDialogFields() {
    return [
        {
            label: 'Document Type',
            fieldname: 'document_type',
            fieldtype: 'Link',
            options: 'Clearing Document Type',
            change: function () {
                handleDocumentTypeChange(this);
            }
        },
        {
            fieldname: "attach_document",
            fieldtype: 'Column Break'
        },
        {
            label: 'Attach Document',
            fieldname: "attach_document",
            fieldtype: 'Attach'
        },
        {
            fieldname: "attach_document",
            fieldtype: 'Section Break'
        },
        {
            label: 'Document Attributes',
            fieldname: 'document_attributes',
            fieldtype: 'Table',
            options: 'Clearing Document Attribute',
            fields: [
                { fieldname: 'attribute', label: 'Attribute', fieldtype: 'Data', in_list_view: 1 },
                { fieldname: 'value', label: 'Value', fieldtype: 'Data', in_list_view: 1 },
                { fieldname: 'mandatory', label: 'mandatory', fieldtype: 'Check', in_list_view: 1, read_only: 1 }
            ]
        }
    ];
}

/**
 * Handle changes in the 'Document Type' field and update attributes accordingly.
 */
function handleDocumentTypeChange(field) {
    let document_type = field.get_value();
    if (document_type) {
        frappe.call({
            method: 'frappe.client.get',
            args: {
                doctype: 'Clearing Document Type',
                name: document_type
            },
            callback: function (r) {
                if (r.message && r.message.clearing_document_attribute) {
                    updateDocumentAttributes(r.message.clearing_document_attribute);
                } else {
                    frappe.msgprint(__('No attributes found for the selected document type.'));
                }
            },
            error: function (err) {
                console.error('Error fetching document type attributes:', err);
                frappe.msgprint(__('Failed to retrieve document attributes. Please try again.'));
            }
        });
    }
}

/**
 * Update the dialog's document attributes table with new data.
 */
function updateDocumentAttributes(attributes) {
    let attributes_table = cur_dialog.get_field('document_attributes').grid;
    attributes_table.df.data = []; // Clear existing data
    attributes_table.refresh();

    attributes.forEach(attr => {
        attributes_table.df.data.push({
            attribute: attr.document_attribute,
            mandatory: attr.mandatory,
            value: ''
        });
    });

    attributes_table.refresh();
}

/**
 * Submit the document attachment and handle the response.
 */
function submitDocumentAttachment(frm, values, d) {
    // Prepare the child table data
    let clearing_document_attributes = values.document_attributes.map(attr => ({
        document_attribute: attr.attribute,
        document_attribute_value: attr.value,
        mandatory: attr.mandatory
    }));

    let invalid = false;

    values.document_attributes.forEach(attr => {
        if (attr.mandatory && !attr.value) {
            invalid = true;
            frappe.msgprint({
                title: __('Missing Value'),
                message: `Please fill the value for ${attr.attribute} as it is mandatory.`,
                indicator: 'red'
            });
        }
    });

    if (invalid) return;

    let attachment_url = document.querySelector('.attached-file-link').getAttribute('href');

    // Use Frappe API to create the document
    frappe.call({
        method: "frappe.client.insert",
        args: {
            doc: {
                doctype: "Clearing Document",
                clearing_file: frm.doc.clearing_file,
                document_attachment: attachment_url,
                linked_file: 'Shipment Clearance',
                clearing_document_type: values.clearing_document_type,
                document_type: values.document_type,
                clearing_document_attributes: clearing_document_attributes
            }
        },
        callback: function (response) {
            if (response && response.message) {
                frappe.msgprint(__('Clearing Document created successfully.'));
                d.hide();
            } else {
                frappe.msgprint(__('There was an issue creating the Clearing Document. Please try again.'));
            }
        },
        error: function (err) {
            console.error('Error during document creation:', err);
            frappe.msgprint(__('Failed to create Clearing Document. Please try again.'));
        }
    });
}
