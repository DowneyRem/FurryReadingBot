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


def to_str(value: Any) -> str:
	"""把字段读成字符串：``None`` / 缺失 → ``""``，其余 ``str()``。"""
	return "" if value is None else str(value)


def to_int(value: Any) -> int:
	"""把字段读成整数：``None`` / 非法值 → 0（不抛异常，旧数据不至于炸存储）。"""
	try:
		return int(value)
	except (TypeError, ValueError):
		return 0

