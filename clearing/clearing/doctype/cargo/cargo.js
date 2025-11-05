// Copyright (c) 2024, Nelson Mpanju and contributors
// For license information, please see license.txt

frappe.ui.form.on('Cargo', {
	container_number(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const rawValue = (row.container_number || '').trim();
		const count = rawValue ? rawValue.split(/[\s,;]+/).filter(Boolean).length : 0;

		const setValueResult = frappe.model.set_value(cdt, cdn, 'quantity_of_container', count);

		Promise.resolve(setValueResult).then(() => {
			if (frm && frm.doc) {
				frm.trigger('update_total_container_summary');
				frm.refresh_field('cargo_details');
				frm.trigger('bind_container_input_handlers');
			}
		});
	}
});
