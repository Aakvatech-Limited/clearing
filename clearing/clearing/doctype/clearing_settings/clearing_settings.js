// Copyright (c) 2024, Nelson Mpanju and contributors
// For license information, please see license.txt

frappe.ui.form.on('Clearing Settings', {
    refresh: function(frm) {
        // Table MultiSelect child filter: restrict to leaf Cash/Bank under Assets
        const grid = frm.fields_dict['cash_or_bank_group_account']?.grid;
        if (grid && grid.get_field && grid.get_field('account_group')) {
            grid.get_field('account_group').get_query = function() {
                return {
                    filters: {
                        'root_type': 'Asset',
                        'is_group': 0,
                        'account_type': ['in', ['Cash', 'Bank']]
                    }
                };
            };
        } else {
            // Fallback if field type changes to Link in future
            frm.set_query('cash_or_bank_group_account', function() {
                return {
                    filters: {
                        'root_type': 'Asset',
                        'is_group': 0,
                        'account_type': ['in', ['Cash', 'Bank']]
                    }
                };
            });
        }

        // Receivable accounts (Table MultiSelect): restrict to leaf Receivable
        const recvGrid = frm.fields_dict['clearing_receivable_account']?.grid;
        if (recvGrid && recvGrid.get_field && recvGrid.get_field('account')) {
            recvGrid.get_field('account').get_query = function() {
                return {
                    filters: {
                        'account_type': 'Receivable',
                        'is_group': 0
                    }
                };
            };
        } else {
            frm.set_query('clearing_receivable_account', function() {
                return {
                    filters: {
                        'account_type': 'Receivable',
                        'is_group': 0
                    }
                };
            });
        }
    }
});
