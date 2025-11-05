# Copyright (c) 2024, Nelson Mpanju and contributors
# For license information, please see license.txt

import re

from frappe.model.document import Document
from frappe.utils import cstr


class Cargo(Document):
	def validate(self):
		self._update_quantities()

	def _update_quantities(self):
		"""Keep derived quantity fields in sync with their source values."""
		self.quantity_of_container = self._count_codes(self.container_number)
		self.quantity_of_hs_code = self._count_codes(self.hs_code)

	@staticmethod
	def _count_codes(value):
		raw_value = cstr(value).strip()
		if not raw_value:
			return 0
		return len([
			code for code in (
				segment.strip() for segment in re.split(r"[\s,;]+", raw_value)
			) if code
		])
