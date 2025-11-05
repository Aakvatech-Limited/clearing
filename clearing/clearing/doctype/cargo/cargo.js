// Copyright (c) 2024, Nelson Mpanju and contributors
// For license information, please see license.txt

frappe.ui.form.on('Cargo', {
	container_number(frm, cdt, cdn) {
		updateQuantityField(frm, cdt, cdn, 'container_number', 'quantity_of_container');
	},
	hs_code(frm, cdt, cdn) {
		updateQuantityField(frm, cdt, cdn, 'hs_code', 'quantity_of_hs_code');
	}
});

function updateQuantityField(frm, cdt, cdn, sourceField, targetField) {
	const row = locals[cdt][cdn];
	const rawValue = (row[sourceField] || '').trim();
	const count = rawValue ? rawValue.split(/[\s,;]+/).filter(Boolean).length : 0;

	const setValueResult = frappe.model.set_value(cdt, cdn, targetField, count);

	Promise.resolve(setValueResult).then(() => {
		if (frm && frm.doc) {
			frm.trigger('update_total_container_summary');
			frm.refresh_field('cargo_details');
			frm.trigger('bind_cargo_input_handlers');
		}
	});
}
