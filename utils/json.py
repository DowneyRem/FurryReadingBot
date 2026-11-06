from __future__ import annotations

from typing import Any


class JsonDict(dict):
	"""general json object that allows attributes to be bound to and also behaves like a dict"""

	def __getattr__(self, attr: Any) -> Any:
		return self.get(attr)

	def __setattr__(self, attr: Any, value: Any) -> None:
		self[attr] = value
