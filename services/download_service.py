"""下载业务：链接检查、作者权限、缓存、抓取、保存与上传编排。

Telegram 相关的展示与上传适配留在 handlers：
  - 本模块不 import telegram；
  - 上传通过 `deliver(..., upload=...)` 注入，便于测试与替换；
  - handler 只负责把本模块返回的结构渲染成消息 / 按钮。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Literal

from sources import (
	fetch as sources_fetch,
	resolve_link as sources_resolve_link,
	resolve_source as sources_resolve_source,
	save as sources_save,
)
from sources.base import Author, Novel, NovelSource, Series
from storage.file_async import remove_file
from storage.file_cache import FileCacheStore, get_default_cache
from storage.list import ListManager
from utils.json import JsonDict
from utils.links import get_id, get_url


logger = logging.getLogger(__name__)

DownloadKind = Literal["novel", "series", "author"]
AccessStatus = Literal["allowed", "blacklisted", "needs_apply"]


class DownloadError(Exception):
	"""下载相关错误的基类，handler 可按类型给出不同提示。"""


class DownloadInvalidLinkError(DownloadError):
	"""消息里没有有效链接，或链接里解析不出作品 ID。"""


class DownloadUnsupportedLinkError(DownloadError):
	"""链接不属于任何已注册来源。"""


class DownloadUnsupportedActionError(DownloadError):
	"""callback 动作不在下载白名单里。"""


@dataclass(frozen=True)
class DownloadOffer:
	"""链接检查结果：handler 据此渲染作品信息和下载按钮。"""

	kind: DownloadKind
	link: str
	description: str
	author_id: str
	author_name: str
	author_url: str
	has_series: bool = False


@dataclass(frozen=True)
class AuthorAccess:
	"""作者维度的下载权限判定结果。"""

	status: AccessStatus
	author_id: str
	author_name: str


@dataclass(frozen=True)
class FormatChoice:
	"""系列 txt / zip 缓存同时存在时，要求用户先选择格式。"""

	link: str


@dataclass(frozen=True)
class DownloadArtifact:
	"""一次下载的产物：可能来自 file_id 缓存，也可能是本地文件。"""

	kind: DownloadKind
	item_id: str
	file_type: str
	target_link: str
	caption: str
	cache_key: str
	file_id: str | None = None
	path: Path | None = None
	filename: str | None = None
	cleanup: bool = False
	from_cache: bool = False


@dataclass(frozen=True)
class DownloadOutcome:
	"""`deliver` 的结果：要么已上传，要么需要用户选择格式。"""

	artifact: DownloadArtifact | None = None
	format_choice_link: str | None = None


UploadCallback = Callable[[DownloadArtifact], Awaitable[None]]


class DownloadService:
	"""下载用例的统一入口。"""

	_ACTIONS: dict[str, tuple[DownloadKind, str]] = {
		"dn": ("novel", "txt"),
		"ds": ("series", "auto"),
		"dst": ("series", "txt"),
		"dsz": ("series", "zip"),
		"dan": ("author", "zip"),
	}
	AUTO_CANDIDATES = ("txt", "zip")


	def __init__(
		self,
		cache: FileCacheStore | None = None,
		*,
		fetch_fn: Callable[[str], Awaitable[Novel | Series | Author]] | None = None,
		save_fn: Callable[[str, str], Awaitable[Path]] | None = None,
		resolve_link_fn: Callable[[str, str], Awaitable[str]] | None = None,
		resolve_source_fn: Callable[[str], NovelSource | None] | None = None,
		list_manager: ListManager | None = None,
	) -> None:
		self._cache = cache
		self._fetch = fetch_fn or sources_fetch
		self._save = save_fn or sources_save
		self._resolve_link = resolve_link_fn or sources_resolve_link
		self._resolve_source = resolve_source_fn or sources_resolve_source
		self._list_manager = list_manager


	@classmethod
	def supports_action(cls, action: str) -> bool:
		"""该 callback 动作是否属于下载。"""
		return action in cls._ACTIONS


	@property
	def cache(self) -> FileCacheStore:
		if self._cache is None:
			self._cache = get_default_cache()
		return self._cache


	@property
	def list_manager(self) -> ListManager:
		if self._list_manager is None:
			self._list_manager = ListManager()
		return self._list_manager


	async def inspect_text(self, text: str) -> DownloadOffer:
		"""从用户消息里提取唯一链接并检查。"""
		link = get_url(text)
		if not isinstance(link, str) or not link:
			raise DownloadInvalidLinkError("请发送一个有效的小说、系列或作者链接。")
		return await self.inspect_link(link)


	async def inspect_link(self, link: str) -> DownloadOffer:
		"""解析来源类型并拉取元信息，供 handler 展示下载菜单。"""
		source = self._resolve_source(link)
		if source is None:
			raise DownloadUnsupportedLinkError(f"暂不支持该链接：{link}")

		if source.is_novel_link(link):
			kind: DownloadKind = "novel"
		elif source.is_series_link(link):
			kind = "series"
		elif source.is_author_link(link):
			kind = "author"
		else:
			raise DownloadUnsupportedLinkError(f"暂不支持该链接：{link}")

		item = await self._fetch(link)
		return DownloadOffer(
			kind=kind,
			link=link,
			description=str(item),
			author_id=str(getattr(item, "author_id", "") or ""),
			author_name=str(getattr(item, "author_name", "") or ""),
			author_url=str(getattr(item, "author_url", "") or ""),
			has_series=bool(getattr(item, "series_id", "")),
		)


	def check_access(self, offer: DownloadOffer) -> AuthorAccess:
		"""按当前名单判断该作者能否下载。"""
		manager = self.list_manager
		author_id = offer.author_id
		if manager.is_blacklisted(author_id):
			name = offer.author_name or manager.blacklist.get_name(author_id)
			return AuthorAccess("blacklisted", author_id, name)
		if manager.is_furryauthor(author_id):
			return AuthorAccess("allowed", author_id, offer.author_name)
		return AuthorAccess("needs_apply", author_id, offer.author_name)


	async def prepare(
		self, action: str, link: str
	) -> FormatChoice | DownloadArtifact:
		"""缓存优先地准备下载产物；不负责上传。"""
		mapping = self._ACTIONS.get(action)
		if mapping is None:
			raise DownloadUnsupportedActionError(f"暂不支持该下载操作：{action}")
		kind, requested_type = mapping
		if not link:
			raise DownloadInvalidLinkError("下载链接为空。")

		# 单篇链接要求下载系列时，解析为其所属系列
		target_link = await self._resolve_link(link, kind)
		item_id = get_id(target_link)
		if not item_id:
			raise DownloadInvalidLinkError("无法从链接中解析作品 ID。")

		file_type = requested_type
		cache_key = FileCacheStore.make_key(kind, item_id, file_type)
		cached: JsonDict | None = None

		# 系列 auto：优先复用 txt / zip；两者都在时让用户选择
		if file_type == "auto" and kind == "series":
			hits = self._find_cached(kind, item_id)
			if len(hits) > 1:
				return FormatChoice(target_link)
			if hits:
				file_type, cache_key, cached = hits[0]
				logger.info("自动命中缓存 %s %s", cache_key, cached.file_name)
		else:
			cached = self.cache.get_valid(cache_key)

		logger.debug("prepare %s %s %s %s", action, kind, item_id, target_link)

		if cached:
			logger.info("命中缓存 %s %s", cache_key, cached.file_name)
			return DownloadArtifact(
				kind=kind,
				item_id=item_id,
				file_type=file_type,
				target_link=target_link,
				caption=cached.caption or "",
				cache_key=cache_key,
				file_id=cached.file_id,
				filename=cached.file_name or None,
				cleanup=False,
				from_cache=True,
			)

		item = await self._fetch(target_link)
		caption = f"{str(item)}\n{item.url}"
		path = Path(await self._save(target_link, file_type))

		if file_type == "auto":
			file_type = path.suffix.lstrip(".").lower() or "txt"
			cache_key = FileCacheStore.make_key(kind, item_id, file_type)
			cached = self.cache.get_valid(cache_key)
			if cached:
				# 保存期间其他人已完成上传，直接复用其 file_id
				if path.is_file():
					await remove_file(path)
				return DownloadArtifact(
					kind=kind,
					item_id=item_id,
					file_type=file_type,
					target_link=target_link,
					caption=caption,
					cache_key=cache_key,
					file_id=cached.file_id,
					filename=cached.file_name or path.name,
					cleanup=False,
					from_cache=True,
				)

		return DownloadArtifact(
			kind=kind,
			item_id=item_id,
			file_type=file_type,
			target_link=target_link,
			caption=caption,
			cache_key=cache_key,
			path=path,
			filename=path.name,
			cleanup=True,
		)


	async def deliver(
		self,
		action: str,
		link: str,
		*,
		upload: UploadCallback,
	) -> DownloadOutcome:
		"""准备产物 -> 调用上传适配器 -> 清理本地文件。"""
		prepared = await self.prepare(action, link)
		if isinstance(prepared, FormatChoice):
			return DownloadOutcome(format_choice_link=prepared.link)

		artifact = prepared
		try:
			await upload(artifact)
		finally:
			if artifact.cleanup and artifact.path is not None and artifact.path.is_file():
				await remove_file(artifact.path)
		return DownloadOutcome(artifact=artifact)


	def _find_cached(self, kind: str, item_id: str) -> list[tuple[str, str, JsonDict]]:
		"""查找有效缓存，返回 [(file_type, cache_key, cached), ...]。"""
		hits: list[tuple[str, str, JsonDict]] = []
		for candidate in self.AUTO_CANDIDATES:
			cache_key = FileCacheStore.make_key(kind, item_id, candidate)
			cached = self.cache.get_valid(cache_key)
			if cached:
				hits.append((candidate, cache_key, cached))
		return hits
