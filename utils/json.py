from __future__ import annotations

from typing import Any


class JsonDict(dict):
	"""general json object that allows attributes to be bound to and also behaves like a dict"""

	def __getattr__(self, attr: Any) -> Any:
		return self.get(attr)

	def __setattr__(self, attr: Any, value: Any) -> None:
		self[attr] = value

	@classmethod
	def from_obj(cls, obj: Any) -> Any:
		"""递归把 dict / list 转成 JsonDict，便于属性访问。"""
		if isinstance(obj, dict):
			return cls({k: cls.from_obj(v) for k, v in obj.items()})
		if isinstance(obj, list):
			return [cls.from_obj(v) for v in obj]
		return obj
