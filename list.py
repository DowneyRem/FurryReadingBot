"""作者黑白名单：JSON 文件存储，支持增删查与热加载。"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
	return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")


class AuthorListStore:
	"""单个名单（白名单或黑名单）。"""

	def __init__(self, path: Path, label: str = "list") -> None:
		self.path = path
		self.label = label
		self._lock = threading.RLock()
		self._mtime: float = 0.0
		self._authors: dict[str, dict[str, str]] = {}
		self.path.parent.mkdir(parents=True, exist_ok=True)
		if not self.path.exists():
			self._write_empty()
		self.reload(force=True)
	
	def _write_empty(self) -> None:
		payload = {"updated_at": _utc_now_iso(), "authors": {}}
		self.path.write_text(
			json.dumps(payload, ensure_ascii=False, indent=2),
			encoding="utf-8",
		)
	
	def reload(self, force: bool = False) -> bool:
		"""文件有变更时重新加载。返回是否真的读了磁盘。"""
		with self._lock:
			if not self.path.exists():
				self._write_empty()
				return True
			mtime = self.path.stat().st_mtime
			if not force and mtime == self._mtime:
				return False
			data = json.loads(self.path.read_text(encoding="utf-8"))
			raw = data.get("authors") or {}
			authors: dict[str, dict[str, str]] = {}
			for aid, info in raw.items():
				aid = str(aid)
				if isinstance(info, dict):
					authors[aid] = {
						"name": str(info.get("name") or ""),
						"note": str(info.get("note") or ""),
					}
				else:
					authors[aid] = {"name": str(info), "note": ""}
			self._authors = authors
			self._mtime = mtime
			return True
	
	def _maybe_reload(self) -> None:
		if self.path.exists() and self.path.stat().st_mtime != self._mtime:
			self.reload(force=True)
	
	def contains(self, author_id: str | int) -> bool:
		self._maybe_reload()
		with self._lock:
			return str(author_id) in self._authors
	
	def get(self, author_id: str | int) -> dict[str, str] | None:
		self._maybe_reload()
		with self._lock:
			return self._authors.get(str(author_id))
	
	def all_ids(self) -> set[str]:
		self._maybe_reload()
		with self._lock:
			return set(self._authors.keys())
	
	def add(self, author_id: str | int, name: str = "", note: str = "") -> None:
		with self._lock:
			self._maybe_reload()
			self._authors[str(author_id)] = {
				"name": name or "",
				"note": note or "",
			}
			self._persist()
	
	def remove(self, author_id: str | int) -> bool:
		with self._lock:
			self._maybe_reload()
			key = str(author_id)
			if key not in self._authors:
				return False
			del self._authors[key]
			self._persist()
			return True
	
	def _persist(self) -> None:
		payload: dict[str, Any] = {
			"updated_at": _utc_now_iso(),
			"authors": {
				aid: self._authors[aid]
				for aid in sorted(self._authors.keys())
			},
		}
		self.path.write_text(
			json.dumps(payload, ensure_ascii=False, indent=2),
			encoding="utf-8",
		)
		self._mtime = self.path.stat().st_mtime


class ListManager:
	"""
	同时管理：白名单、黑名单、兽人作者名单。
	前期：兽人作者、黑名单
	后期：白名单、黑名单（授权转载）
	"""
	
	def __init__(self) -> None:
		data_dir = Path(__file__).resolve().parent / "data"
		data_dir.mkdir(parents=True, exist_ok=True)
		self.whitelist = AuthorListStore(
			data_dir / "white.json",
			label="whitelist",
		)
		self.blacklist = AuthorListStore(
			data_dir / "black.json",
			label="blacklist",
		)
		self.furrylist = AuthorListStore(
			data_dir / "furry.json",
		)
	
	def is_furryauthor(self, author_id: str | int) -> bool:
		return self.furrylist.contains(author_id)
	
	def is_whitelisted(self, author_id: str | int) -> bool:
		return self.whitelist.contains(author_id)
	
	def is_blacklisted(self, author_id: str | int) -> bool:
		return self.blacklist.contains(author_id)
	
	
	def add_furrylist(self, author_id: str | int, name: str = "", note: str = "") -> None:
		self.furrylist.add(author_id, name=name, note=note)
	
	def add_whitelist(self, author_id: str | int, name: str = "", note: str = "") -> None:
		self.blacklist.remove(author_id)
		self.whitelist.add(author_id, name=name, note=note)
	
	def add_blacklist(self, author_id: str | int, name: str = "", note: str = "") -> None:
		self.whitelist.remove(author_id)
		self.blacklist.add(author_id, name=name, note=note)
	
	
	def remove_furrylist(self, author_id: str | int, name: str = "", note: str = "") -> None:
		return self.furrylist.remove(author_id)
	
	def remove_whitelist(self, author_id: str | int) -> bool:
		return self.whitelist.remove(author_id)
	
	def remove_blacklist(self, author_id: str | int) -> bool:
		return self.blacklist.remove(author_id)