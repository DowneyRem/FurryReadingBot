"""分享业务：冷却、并发去重、缓存校验、频道选择、caption、上传与记录。

Telegram 相关部分留在 handlers：
  - 本模块不 import telegram；
  - 上传通过 `share(..., upload=...)` 注入；
  - handler 只负责解析 callback、渲染状态文案。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

from config import FURRY_READING, SHARE_COOLDOWN_DAYS, TEST_CHANNEL
from storage.file_cache import FileCacheStore, get_default_cache
from storage.share_records import ShareRecordStore
from utils.json import JsonDict


logger = logging.getLogger(__name__)

ShareStatus = Literal[
	"shared", "inflight", "cooldown", "cache_missing", "no_channel",
]


@dataclass(frozen=True)
class ShareRequest:
	kind: str
	item_id: str
	file_type: str = "txt"
	public: bool = True
	user_id: int | None = None
	user_name: str = ""


@dataclass(frozen=True)
class ShareArtifact:
	kind: str
	item_id: str
	file_type: str
	cache_key: str
	file_id: str
	filename: str
	channels: tuple[str, ...]
	caption: str
	public: bool


@dataclass(frozen=True)
class ShareResult:
	status: ShareStatus
	record: JsonDict | None = None
	remaining_seconds: float = 0.0
	channels: tuple[str, ...] = ()
	artifact: ShareArtifact | None = None


ShareUploadCallback = Callable[[ShareArtifact], Awaitable[None]]


_share_records: ShareRecordStore | None = None
# 正在发送中的作品 key，避免并发点击造成重复分享
_inflight: set[str] = set()


def get_share_records() -> ShareRecordStore:
	global _share_records
	if _share_records is None:
		_share_records = ShareRecordStore(cooldown_days=SHARE_COOLDOWN_DAYS)
	return _share_records


class ShareService:
	"""分享用例的统一入口。"""

	def __init__(
		self,
		cache: FileCacheStore | None = None,
		*,
		records: ShareRecordStore | None = None,
		channels: tuple[str, ...] | None = None,
		support_text: str | None = None,
	) -> None:
		self._cache = cache
		self._records = records
		self._channels = channels
		self._support_text = support_text


	@property
	def cache(self) -> FileCacheStore:
		if self._cache is None:
			self._cache = get_default_cache()
		return self._cache


	@property
	def records(self) -> ShareRecordStore:
		if self._records is None:
			self._records = get_share_records()
		return self._records


	@property
	def channels(self) -> tuple[str, ...]:
		if self._channels is None:
			self._channels = (TEST_CHANNEL,) if TEST_CHANNEL else ()
		return self._channels


	@property
	def support_text(self) -> str:
		if self._support_text is None:
			self._support_text = FURRY_READING
		return self._support_text


	async def share(
		self,
		request: ShareRequest,
		*,
		upload: ShareUploadCallback,
	) -> ShareResult:
		"""校验冷却 / 缓存 / 频道 -> 上传 -> 写分享记录。"""
		share_key = ShareRecordStore.make_key(request.kind, request.item_id)
		if share_key in _inflight:
			return ShareResult("inflight", channels=self.channels)

		remaining = self.records.remaining(share_key)
		if remaining > 0:
			return ShareResult(
				"cooldown",
				remaining_seconds=remaining,
				channels=self.channels,
			)

		cache_key = FileCacheStore.make_key(
			request.kind, request.item_id, request.file_type)
		cached = self.cache.get_valid(cache_key)
		if not cached:
			return ShareResult("cache_missing", channels=self.channels)

		channels = self.channels
		if not channels:
			return ShareResult("no_channel")

		caption = self._build_caption(request, cached)
		artifact = ShareArtifact(
			kind=request.kind,
			item_id=request.item_id,
			file_type=request.file_type,
			cache_key=cache_key,
			file_id=cached.file_id,
			filename=cached.file_name or "",
			channels=channels,
			caption=caption,
			public=request.public,
		)

		_inflight.add(share_key)
		try:
			await upload(artifact)
		except Exception:
			logger.exception("分享失败 %s", share_key)
			raise
		finally:
			_inflight.discard(share_key)

		title = (cached.caption or "").splitlines()[0] if cached.caption else ""
		record = self.records.record(
			share_key,
			kind=request.kind,
			item_id=request.item_id,
			title=title,
			user_id=request.user_id,
			user_name=request.user_name,
			chat_ids=channels,
			file_type=request.file_type,
			public=request.public,
		)
		logger.info("分享记录 %s %s", share_key, record.count)
		return ShareResult(
			"shared",
			record=record,
			channels=channels,
			artifact=artifact,
		)


	def _build_caption(self, request: ShareRequest, cached: JsonDict) -> str:
		caption = [cached.caption or "", ""]
		if request.public and request.user_name:
			caption.append(f"来自 {request.user_name} 的分享")
		else:
			caption.append("来自 匿名用户 的分享")
		caption.append(
			f"喜欢还请去Pixiv收藏或评论，以支持作者 {self.support_text}")
		return "\n".join(caption)
