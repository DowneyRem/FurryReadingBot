"""作者黑白名单：JSON 文件存储，支持增删查与热加载。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from storage.json_store import JsonStore
from utils.json import JsonDict


class AuthorListStore(JsonStore):
	"""单个名单（白名单 / 黑名单 / 兽人作者名单）。"""

	DATA_KEY = "authors"

	def __init__(self, path: Path, label: str = "list") -> None:
		self.label = label
		super().__init__(path)

	def _normalize(self, info: Any) -> JsonDict | None:
		if isinstance(info, dict):
			return JsonDict(
				name=str(info.get("name") or ""),
				note=str(info.get("note") or ""),
			)
		return JsonDict(name=str(info), note="")

	def contains(self, author_id: str | int) -> bool:
		self._maybe_reload()
		with self._lock:
			return str(author_id) in self._items

	def get(self, author_id: str | int) -> JsonDict:
		self._maybe_reload()
		with self._lock:
			return self._items.get(str(author_id)) or JsonDict()

	def get_name(self, author_id: str | int) -> str:
		info = self.get(author_id)
		return info.name if info else ""

	def all_ids(self) -> set[str]:
		self._maybe_reload()
		with self._lock:
			return set(self._items.keys())

	def add(self, author_id: str | int, name: str = "", note: str = "") -> None:
		with self._lock:
			self._maybe_reload()
			self._items[str(author_id)] = JsonDict(
				name=name or "",
				note=note or "",
			)
			self._persist()

	def remove(self, author_id: str | int) -> bool:
		with self._lock:
			self._maybe_reload()
			key = str(author_id)
			if key not in self._items:
				return False
			del self._items[key]
			self._persist()
			return True


class ListManager:
	"""
	同时管理：白名单、黑名单、兽人作者名单。
	前期：兽人作者、黑名单
	后期：白名单、黑名单（授权转载）
	"""

	def __init__(self, data_dir: Path | None = None) -> None:
		if data_dir is None:
			data_dir = Path(__file__).parent.parent.resolve() / "data"
		data_dir.mkdir(parents=True, exist_ok=True)
		self.whitelist = AuthorListStore(
			data_dir / "white_authors.json",
			label="whitelist",
		)
		self.blacklist = AuthorListStore(
			data_dir / "black_authors.json",
			label="blacklist",
		)
		self.furrylist = AuthorListStore(
			data_dir / "furry_authors.json",
			label="furrylist",
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

	def remove_furrylist(self, author_id: str | int) -> bool:
		return self.furrylist.remove(author_id)

	def remove_whitelist(self, author_id: str | int) -> bool:
		return self.whitelist.remove(author_id)

	def remove_blacklist(self, author_id: str | int) -> bool:
		return self.blacklist.remove(author_id)
