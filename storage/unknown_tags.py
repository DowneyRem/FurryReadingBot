"""未识别标签：来源里出现过、但词表还认不出的写法，落盘供补 aliases。

结构（``DATA_KEY = "tags"``）：

	"未知写法（normalize 后的键）": {
	    "text": "首次 / 最近见到的原样写法",
	    "count": 带这个写法的作品数,
	    "first_seen": ISO 时间,
	    "last_seen": ISO 时间,
	}

产品语义：
  - 键是 ``sources.tags.normalize()`` 的结果，大小写 / 全角差异归并成一条；
  - ``text`` 保留来源原样，方便直接抄进 ``tags.toml`` 的 ``aliases``；
  - ``count`` 按「作品」计数：同一次调用（一篇作品）里的重复写法只算一次；
  - 不做 TTL、**不自动淘汰**：没被人工判断过的写法不能悄悄消失，
    需要瘦身时显式调 ``prune()``；补完 aliases 后 ``clear()``。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from storage.json_store import JsonStore
from utils.json import JsonDict
from utils.time import utc_now_iso


def _as_int(value: Any) -> int:
	try:
		return int(value)
	except (TypeError, ValueError):
		return 0


class UnknownTagStore(JsonStore):
	"""未识别标签的计数表：归一键 → 原样写法 + 次数 + 首末时间。"""

	DATA_KEY = "tags"
	# prune() 的默认保留条数：只影响显式调用，不会自动淘汰
	DEFAULT_PRUNE = 500

	def __init__(self, path: Path | None = None) -> None:
		if path is None:
			path = Path(__file__).parent.parent.resolve() / "data" / "unknown_tags.json"
		super().__init__(path)

	def _normalize(self, info: Any) -> JsonDict | None:
		if not isinstance(info, dict):
			return None
		text = str(info.get("text") or "")
		if not text:
			return None
		return JsonDict(
			text=text,
			count=max(_as_int(info.get("count")), 0),
			first_seen=str(info.get("first_seen") or ""),
			last_seen=str(info.get("last_seen") or ""),
		)

	def record(self, entries: Iterable[tuple[str, str]]) -> int:
		"""批量记账 ``(归一键, 原样写法)``，只落盘一次；返回新增的键数。

		边界：本层只负责持久化（累加次数、维护首末时间、控制条数上限）。
		「什么算未识别」「键怎么归一 / 去重」由调用方决定——目前唯一调用方是
		``sources.tags.display_tags()``，键来自 ``sources.tags.normalize()``。
		"""
		now = utc_now_iso()
		added = 0
		touched = False
		with self._lock:
			self._maybe_reload()
			for key, text in entries:
				key = str(key or "")
				text = str(text or "")
				if not key or not text:
					continue
				item = self._items.get(key)
				if item is None:
					self._items[key] = JsonDict(
						text=text, count=1, first_seen=now, last_seen=now)
					added += 1
				else:
					item["count"] = _as_int(item.get("count")) + 1
					item["text"] = text
					item["last_seen"] = now
				touched = True
			if touched:
				self._persist()
		return added

	def top(self, limit: int = 50) -> list[JsonDict]:
		"""按次数从多到少返回（次数相同按写法排序）；``limit <= 0`` 返回全部。"""
		self._maybe_reload()
		with self._lock:
			items = [JsonDict.from_obj(item) for item in self._items.values()]
		items.sort(
			key=lambda item: (-_as_int(item.get("count")), str(item.get("text") or "")))
		return items[:limit] if limit > 0 else items

	def clear(self) -> int:
		"""清空（补完 aliases 后调用）；返回清掉的条数。"""
		with self._lock:
			self._maybe_reload()
			removed = len(self._items)
			if removed:
				self._items = JsonDict()
				self._persist()
		return removed

	def remove(self, texts: Iterable[str]) -> int:
		"""按写法删除（补完 aliases 后精确销账）；返回删掉的条数。

		``texts`` 里既可以是原样写法，也可以是 ``normalize()`` 后的写法。
		"""
		targets = {str(text).strip() for text in texts if str(text).strip()}
		if not targets:
			return 0
		with self._lock:
			self._maybe_reload()
			doomed = [
				key for key, item in self._items.items()
				if key in targets or str(item.get("text") or "") in targets
			]
			for key in doomed:
				del self._items[key]
			if doomed:
				self._persist()
		return len(doomed)

	def prune(self, limit: int = DEFAULT_PRUNE) -> int:
		"""人工瘦身：只留次数最多的 ``limit`` 条，返回删掉的条数。

		不做自动淘汰——没被人工判断过的写法不能悄悄消失；文件太大时再手动调。
		"""
		if limit <= 0:
			return 0
		with self._lock:
			self._maybe_reload()
			if len(self._items) <= limit:
				return 0
			kept = sorted(
				self._items.items(),
				key=lambda item: (-_as_int(item[1].get("count")), item[0]),
			)[:limit]
			removed = len(self._items) - len(kept)
			self._items = JsonDict(dict(kept))
			self._persist()
		return removed


_default_store: UnknownTagStore | None = None


def get_unknown_tags() -> UnknownTagStore:
	"""进程内共享的未识别标签表。"""
	global _default_store
	if _default_store is None:
		_default_store = UnknownTagStore()
	return _default_store
