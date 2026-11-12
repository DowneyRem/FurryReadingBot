"""分享业务：冷却、并发去重、缓存校验、频道选择、caption、上传与记录。

Telegram 相关部分留在 handlers：
  - 本模块不 import telegram；
  - 上传通过 `share(..., upload=...)` 注入；
  - handler 只负责解析 callback、渲染状态文案。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal, Mapping

from config import (
	FURRY_NOVELS,
	FURRY_READING,
	SHARE_MODE,
	SHARE_SCORE_THRESHOLD,
	TEST_CHANNEL,
)
from storage.file_cache import FileCacheStore, get_file_cache
from storage.share_records import ShareRecordStore, get_share_records
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
	# 作者优先取请求里的，其次取 file_id 缓存（下载时写入）
	author_id: str = ""
	author_name: str = ""
	# 评分决定正式期的频道范围；None 表示还没评分，按低分处理
	score: float | None = None


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
	messages: tuple[JsonDict, ...] = ()
	share_count: int = 0
	remaining_seconds: float = 0.0
	channels: tuple[str, ...] = ()
	artifact: ShareArtifact | None = None


# 上传适配器：返回本次实际投递成功的 {chat_id: message_id}
ShareUploadCallback = Callable[
	[ShareArtifact], Awaitable[Mapping[int | str, int]]
]


# 正在发送中的作品 key，避免并发点击造成重复分享
_inflight: set[str] = set()


def _message_id(delivered: Mapping[int | str, int], chat_id: int | str) -> int:
	"""取出某个频道的 message_id；没拿到就记 0（冷却照常生效，只是无法下架）。"""
	if chat_id in delivered:
		return int(delivered[chat_id] or 0)
	return int(delivered.get(str(chat_id)) or 0)


class ShareService:
	"""分享用例的统一入口。"""

	def __init__(
		self,
		cache: FileCacheStore | None = None,
		*,
		records: ShareRecordStore | None = None,
		channels: tuple[str, ...] | None = None,
		support_text: str | None = None,
		mode: str | None = None,
		score_threshold: float | None = None,
	) -> None:
		self._cache = cache
		self._records = records
		self._channels = channels
		self._support_text = support_text
		self._mode = mode
		self._score_threshold = score_threshold


	@property
	def cache(self) -> FileCacheStore:
		if self._cache is None:
			self._cache = get_file_cache()
		return self._cache


	@property
	def records(self) -> ShareRecordStore:
		if self._records is None:
			self._records = get_share_records()
		return self._records


	@property
	def mode(self) -> str:
		if self._mode is None:
			self._mode = SHARE_MODE
		return self._mode


	@property
	def score_threshold(self) -> float:
		if self._score_threshold is None:
			self._score_threshold = SHARE_SCORE_THRESHOLD
		return self._score_threshold


	def channels(self, score: float | None = None) -> tuple[str, ...]:
		"""本次分享的目标频道。

		test：只发测试频道；
		prod：高分（score >= 阈值）发兽人阅读 + 兽人小说，低分 / 未评分只发兽人小说。
		"""
		if self._channels is not None:
			return self._channels
		if self.mode == "prod":
			if score is not None and score >= self.score_threshold:
				candidates = (FURRY_READING, FURRY_NOVELS)
			else:
				candidates = (FURRY_NOVELS,)
		else:
			candidates = (TEST_CHANNEL,)
		return tuple(chat_id for chat_id in candidates if chat_id)


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
		"""校验并发 / 缓存 / 冷却 / 频道 -> 上传 -> 逐频道写分享记录。"""
		share_key = ShareRecordStore.make_key(request.kind, request.item_id)
		channels = self.channels(request.score)
		if share_key in _inflight:
			return ShareResult("inflight", channels=channels)

		# 先查缓存：作者 id 记录在缓存里，冷却要按作者查
		cache_key = FileCacheStore.make_key(
			request.kind, request.item_id, request.file_type)
		cached = self.cache.get_valid(cache_key)
		if not cached:
			return ShareResult("cache_missing", channels=channels)

		author_id = str(request.author_id or cached.author_id or "")
		author_name = str(request.author_name or cached.author_name or "")

		remaining = self.records.remaining(
			author_id, request.kind, request.item_id)
		if remaining > 0:
			return ShareResult(
				"cooldown",
				remaining_seconds=remaining,
				channels=channels,
			)

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
			sent = await upload(artifact)
		except Exception:
			logger.exception("分享失败 %s", share_key)
			raise
		finally:
			_inflight.discard(share_key)

		delivered = sent if isinstance(sent, Mapping) else {}
		targets = [
			(chat_id, _message_id(delivered, chat_id))
			for chat_id in channels
		]
		title = (cached.caption or "").splitlines()[0] if cached.caption else ""
		work = self.records.record(
			author_id=author_id,
			author_name=author_name,
			kind=request.kind,
			item_id=request.item_id,
			messages=targets,
			title=title,
			user_id=request.user_id,
			user_name=request.user_name,
		)
		logger.info(
			"分享记录 %s 消息 %s 条，累计 %s 次",
			share_key, len(targets), work.share_count,
		)
		return ShareResult(
			"shared",
			messages=tuple(
				JsonDict(chat_id=str(chat_id), message_id=message_id)
				for chat_id, message_id in targets
			),
			share_count=int(work.share_count or 0),
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
