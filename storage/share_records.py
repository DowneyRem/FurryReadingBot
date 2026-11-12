"""分享记录：作者 → 作品 → 频道 → 消息，四层结构，热加载。

一条 Telegram 消息就是一个数组元素：

	"12345":                                   作者 id
	└── "novel:1001":                          作品 key = kind:item_id
	    └── "history": {"-1001234567890": […] }  频道 id → 消息数组
	        └── {message_id, sent_at, user_id, user_name}

产品语义：
  - 下架按作者来（投诉 → 拉黑 → 删历史），所以作者是第一层 key；
  - ``share_count`` 是「用户分享次数」，一次点击只 +1，发几个频道都不再加；
  - ``first_shared_at`` / ``last_shared_at`` 由 history 派生，读盘时重算；
  - 记录按消息级 TTL 保留，30 天内可回溯下架。

旧格式（顶层 key 是 "novel:123"）会在读盘时被丢弃：作者 key 必须是纯数字。
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable

from storage.json_store import JsonStore
from utils.json import JsonDict
from utils.time import parse_iso, utc_now


# 作者 id 未知时的占位（升级前写入的 file_id 缓存里没有作者）
UNKNOWN_AUTHOR = "-"
# 允许的作品类型，与 FileCacheStore / DownloadService 的 kind 保持一致
WORK_KINDS = ("novel", "series", "author")
ISO_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def _as_str(value: str | int | None) -> str:
	return "" if value is None else str(value)


def _as_int(value: Any) -> int:
	try:
		return int(value)
	except (TypeError, ValueError):
		return 0


class ShareRecordStore(JsonStore):
	"""分享记录：按作者归档，冷却窗口与记录保留时间（TTL）相互独立。"""

	DATA_KEY = "shares"
	DEFAULT_COOLDOWN_DAYS = 7
	# 记录保留时间写死在代码里，不提供配置入口
	DEFAULT_TTL_DAYS = 30

	def __init__(
		self,
		path: Path | None = None,
		cooldown_days: float | None = None,
	) -> None:
		if path is None:
			path = Path(__file__).parent.parent.resolve() / "data" / "share_records.json"
		self.cooldown_days = (
			cooldown_days if cooldown_days is not None else self.DEFAULT_COOLDOWN_DAYS
		)
		super().__init__(path)

	# ----- key 规则 -----

	@staticmethod
	def make_key(kind: str, item_id: str | int) -> str:
		"""作品 key：kind:item_id，与 FileCacheStore 的 kind 保持同一套写法。"""
		return f"{kind}:{item_id}"

	@staticmethod
	def parse_key(key: str) -> tuple[str, str] | None:
		"""拆作品 key；kind 不在白名单里（旧格式 / 手写坏）返回 None。"""
		kind, sep, item_id = str(key).partition(":")
		if not sep or not item_id or kind not in WORK_KINDS:
			return None
		return kind, item_id

	# ----- JsonStore 钩子 -----

	def _normalize(self, info: Any) -> JsonDict | None:
		"""一层层下钻：作者 → 作品 → 频道 → 消息；非法 key / 空结构直接丢弃。"""
		if not isinstance(info, dict):
			return None
		author = JsonDict(author_name=str(info.get("author_name") or ""))
		for key, work in info.items():
			if key == "author_name":
				continue
			if self.parse_key(key) is None:
				continue
			normalized = self._normalize_work(work)
			if normalized is not None:
				author[str(key)] = normalized
		return author

	@staticmethod
	def _normalize_work(info: Any) -> JsonDict | None:
		if not isinstance(info, dict):
			return None
		raw_history = info.get("history")
		history = JsonDict()
		if isinstance(raw_history, dict):
			for chat_id, rows in raw_history.items():
				cleaned = [
					row for row in (
						ShareRecordStore._normalize_message(item) for item in rows or [])
					if row is not None
				]
				if cleaned:
					history[str(chat_id)] = cleaned
		if not history:
			return None
		first, last = ShareRecordStore._span(history)
		return JsonDict(
			title=str(info.get("title") or ""),
			share_count=_as_int(info.get("share_count")),
			first_shared_at=first,
			last_shared_at=last,
			history=history,
		)

	@staticmethod
	def _normalize_message(info: Any) -> JsonDict | None:
		if not isinstance(info, dict):
			return None
		sent_at = str(info.get("sent_at") or "")
		if parse_iso(sent_at) is None:
			return None
		return JsonDict(
			message_id=_as_int(info.get("message_id")),
			sent_at=sent_at,
			user_id=_as_str(info.get("user_id")),
			user_name=str(info.get("user_name") or ""),
		)

	@staticmethod
	def _span(history: JsonDict) -> tuple[str, str]:
		"""从 history 派生 first / last：手改 history 后读盘会自动纠正。"""
		stamps = [
			(parse_iso(row.sent_at), str(row.sent_at))
			for rows in history.values() for row in rows
		]
		stamps = [(moment, text) for moment, text in stamps if moment is not None]
		if not stamps:
			return "", ""
		first = min(stamps, key=lambda pair: pair[0])[1]
		last = max(stamps, key=lambda pair: pair[0])[1]
		return first, last

	def _prune(self) -> None:
		"""消息级 TTL：过期消息 → 空频道 → 空作品 → 空作者，逐级回收。

		读盘、写盘、查询前都会跑，保证内存里永远只有「TTL 天内」的数据。
		"""
		now = utc_now()
		ttl = timedelta(days=self.DEFAULT_TTL_DAYS)
		kept = JsonDict()
		for author_id, node in self._items.items():
			author_key = str(author_id)
			if author_key != UNKNOWN_AUTHOR and not author_key.isdigit():
				continue
			author = JsonDict(author_name=str(node.author_name or ""))
			for work_key, work in dict(node).items():
				if work_key == "author_name" or self.parse_key(work_key) is None:
					continue
				history = JsonDict()
				for chat_id, rows in dict(work.history or {}).items():
					fresh = [
						row for row in rows
						if (sent := parse_iso(row.sent_at)) is not None
						and now - sent < ttl
					]
					if fresh:
						history[str(chat_id)] = fresh
				if not history:
					continue
				first, last = self._span(history)
				author[work_key] = JsonDict(
					title=str(work.title or ""),
					share_count=_as_int(work.share_count),
					first_shared_at=first,
					last_shared_at=last,
					history=history,
				)
			if len(author) > 1:
				kept[author_key] = author
		self._items = kept

	# ----- 读 -----

	def work(
		self,
		author_id: str | int | None,
		kind: str,
		item_id: str | int,
	) -> JsonDict | None:
		"""读取一个作品节点（含 history），没有则返回 None。"""
		self._maybe_reload()
		with self._lock:
			self._prune()
			node = self._items.get(_as_str(author_id) or UNKNOWN_AUTHOR)
			if not node:
				return None
			return node.get(self.make_key(kind, item_id))

	def remaining(
		self,
		author_id: str | int | None,
		kind: str,
		item_id: str | int,
		*,
		cooldown_days: float | None = None,
	) -> float:
		"""距离冷却结束还剩多少秒；0 表示当前可以分享。"""
		work = self.work(author_id, kind, item_id)
		if not work:
			return 0.0
		last = parse_iso(work.last_shared_at)
		if last is None:
			return 0.0
		days = cooldown_days if cooldown_days is not None else self.cooldown_days
		left = (last + timedelta(days=days) - utc_now()).total_seconds()
		return max(0.0, left)

	def is_limited(
		self,
		author_id: str | int | None,
		kind: str,
		item_id: str | int,
		*,
		cooldown_days: float | None = None,
	) -> bool:
		return self.remaining(
			author_id, kind, item_id, cooldown_days=cooldown_days) > 0

	def by_author(self, author_id: str | int) -> list[JsonDict]:
		"""该作者名下所有消息，下架时逐条删除用（带 chat_id / message_id）。"""
		self._maybe_reload()
		with self._lock:
			self._prune()
			author_key = _as_str(author_id) or UNKNOWN_AUTHOR
			node = self._items.get(author_key)
			if not node:
				return []
			author_name = str(node.author_name or "")
			rows: list[JsonDict] = []
			for work_key, work in dict(node).items():
				parsed = self.parse_key(work_key)
				if parsed is None:
					continue
				kind, item_id = parsed
				for chat_id, messages in dict(work.history or {}).items():
					for message in messages:
						rows.append(JsonDict(
							author_id=author_key,
							author_name=author_name,
							kind=kind,
							item_id=item_id,
							title=str(work.title or ""),
							chat_id=str(chat_id),
							message_id=_as_int(message.message_id),
							sent_at=str(message.sent_at or ""),
							user_id=str(message.user_id or ""),
							user_name=str(message.user_name or ""),
						))
			return sorted(rows, key=lambda row: row.sent_at or "")

	# ----- 写 -----

	def record(
		self,
		*,
		author_id: str | int | None,
		kind: str,
		item_id: str | int,
		messages: Iterable[tuple[str | int, int]],
		author_name: str = "",
		title: str = "",
		user_id: str | int | None = None,
		user_name: str = "",
		shared_at: str | None = None,
	) -> JsonDict:
		"""写入一次用户分享：share_count +1，每个频道追加一条消息。"""
		author_key = _as_str(author_id) or UNKNOWN_AUTHOR
		work_key = self.make_key(kind, item_id)
		stamp = shared_at or utc_now().strftime(ISO_FORMAT)
		with self._lock:
			self._maybe_reload()
			author = self._items.get(author_key)
			if author is None:
				author = JsonDict(author_name="")
				self._items[author_key] = author
			if author_name:
				author["author_name"] = str(author_name)
			work = author.get(work_key) or JsonDict(
				title="",
				share_count=0,
				first_shared_at="",
				last_shared_at="",
				history=JsonDict(),
			)
			if title and not work.title:
				work["title"] = str(title)
			history = work["history"]
			for chat_id, message_id in messages:
				chat_key = str(chat_id)
				rows = [
					row for row in (history.get(chat_key) or [])
					if _as_int(row.message_id) != _as_int(message_id)
				]
				rows.append(JsonDict(
					message_id=_as_int(message_id),
					sent_at=stamp,
					user_id=_as_str(user_id),
					user_name=str(user_name or ""),
				))
				history[chat_key] = rows
			work["share_count"] = _as_int(work.share_count) + 1
			first, last = self._span(history)
			work["first_shared_at"] = first or stamp
			work["last_shared_at"] = last or stamp
			author[work_key] = work
			self._persist()
			return work

	def remove_message(
		self,
		author_id: str | int | None,
		kind: str,
		item_id: str | int,
		chat_id: str | int,
		message_id: int,
	) -> bool:
		"""下架单条消息；删空了自动回收频道 / 作品 / 作者。"""
		author_key = _as_str(author_id) or UNKNOWN_AUTHOR
		work_key = self.make_key(kind, item_id)
		with self._lock:
			self._maybe_reload()
			self._prune()
			author = self._items.get(author_key)
			work = author.get(work_key) if author else None
			if not work:
				return False
			history = work["history"]
			chat_key = str(chat_id)
			rows = history.get(chat_key) or []
			kept = [
				row for row in rows
				if _as_int(row.message_id) != _as_int(message_id)
			]
			if len(kept) == len(rows):
				return False
			if kept:
				history[chat_key] = kept
			else:
				history.pop(chat_key, None)
			if history:
				first, last = self._span(history)
				work["first_shared_at"] = first
				work["last_shared_at"] = last
			else:
				author.pop(work_key, None)
			self._persist()
			return True

	def drop_author(self, author_id: str | int) -> bool:
		"""整块删除一个作者（拉黑后下架完消息时调用）。"""
		author_key = _as_str(author_id) or UNKNOWN_AUTHOR
		with self._lock:
			self._maybe_reload()
			if self._items.pop(author_key, None) is None:
				return False
			self._persist()
			return True



_default_store: ShareRecordStore | None = None


def get_share_records() -> ShareRecordStore:
	"""进程内共享的分享记录；冷却天数由 config 控制。"""
	global _default_store
	if _default_store is None:
		from config import SHARE_COOLDOWN_DAYS

		_default_store = ShareRecordStore(cooldown_days=SHARE_COOLDOWN_DAYS)
	return _default_store

