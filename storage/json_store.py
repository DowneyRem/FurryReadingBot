"""JSON 文件存储基类：原子写、mtime 热加载、进程内锁、prune 钩子。

各业务 Store（authors / furry_request / black_request / file_cache / share_records）
只需要声明数据键、实现 ``_normalize``（必要时 ``_prune``），
其余读写与并发细节全部复用这里。
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from utils.json import JsonDict
from utils.time import utc_now_iso

logger = logging.getLogger(__name__)


class JsonStore:
	"""单个 JSON 文件的最小存储骨架。"""

	# 业务数据在 JSON 顶层的键名，例如 "authors" / "furrylist" / "blacklist"
	DATA_KEY = "items"

	def __init__(self, path: str | Path, *, data_key: str | None = None) -> None:
		self.path = Path(path)
		self._data_key = data_key or self.DATA_KEY
		self._lock = threading.RLock()
		self._mtime: float = 0.0
		self._items: JsonDict = JsonDict()
		self.path.parent.mkdir(parents=True, exist_ok=True)
		if not self.path.exists():
			self._write_empty()
		self.reload(force=True)

	# ----- 子类必须/可选覆写 -----
	def _normalize(self, info: Any) -> JsonDict | None:
		"""把一条记录转换成统一结构；返回 None 表示丢弃。"""
		if isinstance(info, dict):
			return JsonDict.from_obj(info)
		return None

	def _prune(self) -> None:
		"""丢弃过期记录；子类按需覆写。"""
		return None

	# ----- 内部工具 -----
	def _snapshot(self) -> JsonDict:
		return JsonDict({k: self._items[k] for k in sorted(self._items.keys())})

	def _payload(self) -> JsonDict:
		return JsonDict(
			updated_at=utc_now_iso(),
			**{self._data_key: self._snapshot()},
		)

	def _write_payload(self, payload: JsonDict) -> None:
		"""原子写：同目录临时文件 + os.replace，避免半个 JSON。"""
		self.path.parent.mkdir(parents=True, exist_ok=True)
		text = json.dumps(payload, ensure_ascii=False, indent=4)
		fd, tmp_name = tempfile.mkstemp(
			prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
		try:
			with os.fdopen(fd, "w", encoding="utf-8") as f:
				f.write(text)
				f.flush()
				os.fsync(f.fileno())
			os.replace(tmp_name, self.path)
		except Exception:
			try:
				os.unlink(tmp_name)
			except OSError:
				pass
			raise
		self._mtime = self.path.stat().st_mtime

	def _write_empty(self) -> None:
		self._write_payload(self._payload())

	# ----- 读写 -----
	def reload(self, force: bool = False) -> bool:
		"""文件有变更时重新加载。返回是否真的读了磁盘。"""
		with self._lock:
			if not self.path.exists():
				self._write_empty()
				return True
			mtime = self.path.stat().st_mtime
			if not force and mtime == self._mtime:
				return False
			try:
				data = JsonDict.from_obj(
					json.loads(self.path.read_text(encoding="utf-8")))
			except Exception:
				logger.exception("读取 JSON 存储失败：%s", self.path)
				raise
			if not isinstance(data, dict):
				raise ValueError(f"JSON 存储顶层不是对象：{self.path}")

			raw = data.get(self._data_key) or {}
			items = JsonDict()
			if isinstance(raw, dict):
				for key, info in raw.items():
					normalized = self._normalize(info)
					if normalized is not None:
						items[str(key)] = normalized
			self._items = items
			self._mtime = mtime
			self._prune()
			return True

	def _maybe_reload(self) -> None:
		try:
			if self.path.exists() and self.path.stat().st_mtime != self._mtime:
				self.reload(force=True)
		except OSError:
			logger.debug("检查 JSON 存储变更失败：%s", self.path, exc_info=True)

	def _persist(self) -> None:
		with self._lock:
			self._prune()
			self._write_payload(self._payload())
