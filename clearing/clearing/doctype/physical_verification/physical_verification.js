// Copyright (c) 2024, Nelson Mpanju and contributors
// For license information, please see license.txt

frappe.ui.form.on("Physical Verification", {
    refresh(frm) {
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
                            // Port Clearance button
                            handle_clearance_creation(
                                'Port Clearance', 'Port Clearance',
                                { clearing_file: frm.doc.clearing_file },
                                { doctype: 'Port Clearance', clearing_file: frm.doc.clearing_file, customer: frm.doc.customer, status: 'Unpaid' },
                                'Port Clearance created successfully'
                            );

                            // TRA Clearance button
                            handle_clearance_creation(
                                'TRA Clearance', 'TRA Clearance',
                                { clearing_file: frm.doc.clearing_file },
                                { doctype: 'TRA Clearance', clearing_file: frm.doc.clearing_file, customer: frm.doc.customer, status: 'Payment Pending' },
                                'TRA Clearance created successfully'
                            );

                            // Shipment Clearance button
                            handle_clearance_creation(
                                'Shipment Clearance', 'Shipment Clearance',
                                { clearing_file: frm.doc.clearing_file },
                                { doctype: 'Shipment Clearance', clearing_file: frm.doc.clearing_file, customer: frm.doc.customer, status: 'Unpaid' },
                                'Shipment Clearance created successfully'
                            );
                        }

                        // Update button types for custom actions
                        ['Port Clearance', 'TRA Clearance', 'Shipment Clearance'].forEach(action => {
                            frm.change_custom_button_type(action, null, 'primary');
                        });
                    }
                }
            });
        }

        // Helper function to create or redirect to documents
        function handle_clearance_creation(doctype, label, filters, new_doc_data, success_message) {
            frm.add_custom_button(__(label), function () {
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

                            if (frm.doc.status === 'Pre-Lodged') {
                                frm.set_value('status', 'On Process');
                                frm.save_or_update();
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

                                        frm.set_value('status', 'On Process');
                                        frm.save_or_update();
                                    }
                                }
                            });
                        }
                    }
                });
            }, null, 'primary'); // Make the button primary
        }
    },

    attach_documents: function (frm) {
        // Create the dialog for document attachment
        let d = new frappe.ui.Dialog({
            title: 'Attach Clearing Document',
            fields: [
                {
                    label: 'Document Type',
                    fieldname: 'document_type',
                    fieldtype: 'Link',
                    options: 'Clearing Document Type',
                    change: function () {
                        let document_type = d.get_value('document_type');
                        if (document_type) {
                            frappe.call({
                                method: 'frappe.client.get',
                                args: {
                                    doctype: 'Clearing Document Type',
                                    name: document_type
                                },
                                callback: function (r) {
                                    if (r.message && r.message.clearing_document_attribute) {
                                        let attributes_table = d.get_field('document_attributes').grid;
                                        attributes_table.df.data = []; // Clear existing data
                                        attributes_table.refresh();

                                        // Populate table with attributes
                                        r.message.clearing_document_attribute.forEach(aattribute => {
                                            d.fields_dict.document_attributes.df.data.push({
                                                attribute: aattribute.document_attribute,
                                                mandatory: aattribute.mandatory,
                                                value: ''
                                            });
                                        });
                                        attributes_table.refresh();
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
            ],
            size: 'large',
            primary_action_label: 'Submit',
            primary_action(values) {
                let attachment_url = document.querySelector('.attached-file-link').getAttribute('href');

                // Validate mandatory fields
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

                // If validation fails, stop submission
                if (invalid) return;

                // Prepare the child table data
                let clearing_document_attributes = values.document_attributes.map(attr => ({
                    document_attribute: attr.attribute,
                    document_attribute_value: attr.value,
                    mandatory: attr.mandatory
                }));

                // Use Frappe API to create the Clearing Document
                frappe.call({
                    method: "frappe.client.insert",
                    args: {
                        doc: {
                            doctype: "Clearing Document",
                            clearing_file: frm.doc.clearing_file,
                            document_attachment: attachment_url,
                            clearing_document_type: values.document_type,
                            linked_file: 'Physical Verification',
                            clearing_document_attributes: clearing_document_attributes // Handle child table
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
                        frappe.msgprint(__('Failed to create Clearing Document. Please try again.'));
                    }
                });
            }
        });

        // Set a query to filter "Document Type" where linked_document = "Physical Verification"
        d.fields_dict.document_type.get_query = function () {
            return {
                filters: {
                    linked_document: "Physical Verification"
                }
            };
        };

        d.show();
    }
});
