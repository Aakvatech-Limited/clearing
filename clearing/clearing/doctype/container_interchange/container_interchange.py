# Copyright (c) 2024, Nelson Mpanju and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class ContainerInterchange(Document):
	def before_submit(self):
		self.validate_shipping_line_deposit()
		self.validate_final_eir_against_delivery_note()

	def validate_final_eir_against_delivery_note(self):
		if not self.clearing_file:
			return

		has_linked_delivery_note = bool(
			frappe.db.exists(
				"CF Delivery Note",
				{"container_interchange": self.name, "docstatus": ["<", 2]},
			)
		)
		if not has_linked_delivery_note:
			return

		if not self.final or not self.eir_number_reference or not self.eir_date:
			frappe.throw(
				_("Final EIR is required (Has Final EIR, EIR Number Reference, EIR Date) before submitting.")
			)

	def validate_shipping_line_deposit(self):
		if not self.clearing_file:
			return

		deposit_amount = frappe.db.get_value(
			"Shipping Line Clearance",
			{"clearing_file": self.clearing_file, "docstatus": ["<", 2]},
			"container_deposit_amount",
		)

		if not flt(deposit_amount):
			return

		if not self.refund or not flt(self.refund_amount) or not self.refund_date:
			frappe.throw(
				_(
					"A Container Deposit of {0} is recorded in Shipping Line Clearance for "
					"Clearing File {1}. Please update the refund (tick Container Deposit "
					"Refunded, set Refund Date and Refund Amount) before submitting."
				).format(flt(deposit_amount), self.clearing_file)
			)

		if not self.final or not self.eir_number_reference or not self.eir_date:
			frappe.throw(
				_(
					"A Container Deposit of {0} is recorded in Shipping Line Clearance for "
					"Clearing File {1}. Please update the Final EIR (tick Has Final EIR, "
					"set EIR Number Reference and EIR Date) before submitting."
				).format(flt(deposit_amount), self.clearing_file)
			)
