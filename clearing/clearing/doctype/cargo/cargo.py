# Copyright (c) 2024, Nelson Mpanju and contributors
# For license information, please see license.txt

import re

from frappe.model.document import Document
from frappe.utils import cstr


class Cargo(Document):
	def validate(self):
		self._update_container_quantity()

	def _update_container_quantity(self):
		"""Update quantity_of_container based on the number of container numbers provided."""
		raw_value = cstr(self.container_number)
		if not raw_value:
			self.quantity_of_container = 0
			return

		container_codes = [code.strip() for code in re.split(r"[\s,;]+", raw_value) if code.strip()]
		self.quantity_of_container = len(container_codes)
