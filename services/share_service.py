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

from config import (
	FURRY_NOVELS,
	FURRY_READING,
	SHARE_MODE,
	SHARE_SCORE_THRESHOLD,
	TEST_CHANNEL,
)
from policy.author import AuthorPolicy
from sources import fetch as sources_fetch, work_url
from sources.base import Author, Novel, Series
from storage.file_cache import FileCacheStore, get_file_cache
from storage.share_records import ShareRecordStore, get_share_records
from utils.json import JsonDict


logger = logging.getLogger(__name__)

ShareStatus = Literal[
	"shared", "inflight", "cooldown", "cache_missing", "no_channel", "forbidden",
	# 所有频道都发送失败
	"failed",
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
	# 作品链接：分享到频道后「添加本文至书架」按钮要用
	link: str = ""


@dataclass(frozen=True)
class ShareResult:
	status: ShareStatus
	messages: tuple[JsonDict, ...] = ()
	share_count: int = 0
	remaining_seconds: float = 0.0
	channels: tuple[str, ...] = ()
	# 发送失败的频道：部分成功时 status 仍为 shared
	failed_channels: tuple[str, ...] = ()
	artifact: ShareArtifact | None = None
	# forbidden 时给展示层用
	author_status: str = ""
	author_name: str = ""


# 上传适配器：把产物发到一个频道，返回 message_id；失败抛异常
ShareUploadCallback = Callable[[ShareArtifact, str], Awaitable[int]]


# 正在发送中的作品 key，避免并发点击造成重复分享
_inflight: set[str] = set()


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
		policy: AuthorPolicy | None = None,
		fetch_fn: Callable[[str], Awaitable[Novel | Series | Author]] | None = None,
	) -> None:
		self._cache = cache
		self._policy = policy
		self._fetch = fetch_fn or sources_fetch
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
	def policy(self) -> AuthorPolicy:
		if self._policy is None:
			self._policy = AuthorPolicy()
		return self._policy


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
		"""校验并发 / 缓存 / 权限 / 冷却 / 频道 -> 逐频道发送 -> 记录发送成功的频道。

		单个频道失败不影响其他频道；只要有一个频道成功，就记录并进入冷却，
		避免用户重试时把已成功的频道再发一遍。
		"""
		share_key = ShareRecordStore.make_key(request.kind, request.item_id)
		channels = self.channels(request.score)
		if share_key in _inflight:
			return ShareResult("inflight", channels=channels)

		# 检查与发送之间有 await（补拉作者、上传），整段都要占住，避免连点重复发送
		_inflight.add(share_key)
		try:
			return await self._share(request, share_key, channels, upload)
		finally:
			_inflight.discard(share_key)


	async def _share(
		self,
		request: ShareRequest,
		share_key: str,
		channels: tuple[str, ...],
		upload: ShareUploadCallback,
	) -> ShareResult:
		# 先查缓存：作者 id 记录在缓存里，冷却要按作者查
		cache_key = FileCacheStore.make_key(
			request.kind, request.item_id, request.file_type)
		cached = self.cache.get_valid(cache_key)
		if not cached:
			return ShareResult("cache_missing", channels=channels)

		# 下载时把 target_link 写进了缓存；老数据没有就按 kind + item_id 拼
		link = str(cached.link or "") or work_url(request.kind, request.item_id)
		author_id = str(request.author_id or cached.author_id or "")
		author_name = str(request.author_name or cached.author_name or "")
		if not author_id:
			# 老缓存没记作者：补拉一次，权限判定与下架回溯都要靠作者 id
			item = await self._fetch(link)
			author_id, author_name = str(item.author_id), str(item.author_name)

		decision = self.policy.check(author_id, author_name)
		if not decision.can_download:
			return ShareResult(
				"forbidden",
				channels=channels,
				author_status=decision.status,
				author_name=decision.author_name,
			)

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
			link=link,
		)

		targets: list[tuple[str, int]] = []
		failed: list[str] = []
		for chat_id in channels:
			try:
				targets.append((chat_id, await upload(artifact, chat_id)))
			except Exception:
				logger.exception("分享到频道失败 %s chat=%s", share_key, chat_id)
				failed.append(chat_id)

		if not targets:
			return ShareResult(
				"failed", channels=channels, failed_channels=tuple(failed))

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
			channels=tuple(chat_id for chat_id, _ in targets),
			failed_channels=tuple(failed),
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
