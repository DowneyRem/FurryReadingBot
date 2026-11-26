"""Pixiv Web API 异步客户端。

只负责：URL 请求、多账号 Cookie 轮换与冷却、浏览器 Header、单号限流、HTTP 错误映射。
响应解析与模型转换留给 `parse.py`（下一步），这样 client 可以独立测试。
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from infra.http import HttpError, drop_cached_json, get_json, get_text
from sources.pixiv.config import (
	COOKIE_SEPARATOR,
	ENV_COOKIE,
	GLOBAL_MIN_INTERVAL,
	HEADERS,
	LANG,
	MAX_REQUESTS_PER_ACCOUNT,
	MIN_INTERVAL,
	RATE_LIMIT_COOLDOWN,
	REFERER,
	REQUEST_JITTER,
)
from sources.pixiv.errors import (
	PixivAuthError,
	PixivNetworkError,
	PixivNotFoundError,
	PixivParseError,
	PixivRateLimitError,
)
from sources.pixiv.urls import (
	url_novel_data,
	url_series_data,
	url_series_novels_title,
	url_user_data,
	url_user_works_all,
)
from utils.json import JsonDict


logger = logging.getLogger(__name__)

_UID_RE = re.compile(r"(?:^|;\s*)PHPSESSID=(\d+)_")
_CSRF_RE = re.compile(r'token\\*"\s*:\s*\\*"([a-z0-9]{32})')


def _normalize_cookie(value: str | None) -> str:
	"""完整 Cookie 串原样保留；只给 PHPSESSID 的值时自动补键名。"""
	text = (value or "").strip()
	if not text:
		return ""
	if "=" in text:
		return text
	return f"PHPSESSID={text}"


def parse_cookies(value: str | None) -> list[str]:
	"""把单个、``||`` 分隔或多行 ``PIXIV_COOKIE`` 解析为去重后的标准 Cookie 列表。"""
	if not value:
		return []
	cookies: list[str] = []
	seen: set[str] = set()
	for raw_line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
		line = raw_line.strip()
		if not line or line.startswith("#"):
			continue
		for part in line.split(COOKIE_SEPARATOR):
			normalized = _normalize_cookie(part)
			if normalized and normalized not in seen:
				seen.add(normalized)
				cookies.append(normalized)
	return cookies


def extract_csrf_token(html: str) -> str | None:
	"""从 Pixiv 首页 HTML 提取与当前会话绑定的 32 位 ``x-csrf-token``。"""
	if not html:
		return None
	match = _CSRF_RE.search(html)
	return match.group(1) if match else None


@dataclass
class PixivAccount:
	"""单个 Pixiv 账号的会话凭据、CSRF Token 与运行时风控状态。"""

	cookie: str
	csrf_token: str | None = None
	uid: str | None = None
	last_used: float | None = None
	cooldown_until: float = 0.0
	dead: bool = False

	def __post_init__(self) -> None:
		self.cookie = _normalize_cookie(self.cookie)
		if not self.uid and self.cookie:
			match = _UID_RE.search(self.cookie)
			if match:
				self.uid = match.group(1)
		if self.csrf_token is not None:
			self.csrf_token = self.csrf_token.strip() or None

	@property
	def is_authenticated(self) -> bool:
		return bool(self.cookie)

	@property
	def label(self) -> str:
		"""用于日志的安全标识，绝不输出敏感 Cookie 原文。"""
		if self.uid:
			return f"uid={self.uid}"
		return "account" if self.cookie else "anonymous"

	def is_available(self, now: float | None = None) -> bool:
		if self.dead:
			return False
		current = time.monotonic() if now is None else now
		return current >= self.cooldown_until

	def headers(
		self,
		base_headers: dict[str, str] | None = None,
		*,
		include_csrf: bool = False,
	) -> dict[str, str]:
		result = dict(HEADERS if base_headers is None else base_headers)
		if self.cookie:
			result["Cookie"] = self.cookie
		if include_csrf and self.csrf_token:
			result["x-csrf-token"] = self.csrf_token
		return result


def _accounts_from_cookies(cookies: Iterable[str | PixivAccount]) -> list[PixivAccount]:
	accounts: list[PixivAccount] = []
	seen: set[str] = set()
	for item in cookies:
		if isinstance(item, PixivAccount):
			account = item
		else:
			account = PixivAccount(cookie=item)
		if not account.cookie or account.cookie in seen:
			continue
		seen.add(account.cookie)
		accounts.append(account)
	return accounts


class PixivClient:
	"""Pixiv Web API（www.pixiv.net/ajax）的异步客户端，支持多账号轮换与冷却。"""

	def __init__(
		self,
		cookie: str | None = None,
		*,
		cookies: Iterable[str | PixivAccount] | None = None,
		min_interval: float | None = None,
		global_min_interval: float | None = None,
		jitter: float | None = None,
		cooldown_seconds: float | None = None,
		rotate_every: int | None = None,
		random_start: bool = True,
		lang: str = LANG,
	) -> None:
		self.min_interval = MIN_INTERVAL if min_interval is None else max(0.0, min_interval)
		if global_min_interval is not None:
			self.global_min_interval = max(0.0, global_min_interval)
		elif min_interval is not None and self.min_interval == 0.0:
			# 显式传入 min_interval=0（测试关闭限流）时，同步关闭全局间隔与抖动
			self.global_min_interval = 0.0
		else:
			self.global_min_interval = GLOBAL_MIN_INTERVAL
		if jitter is not None:
			self.jitter = max(0.0, jitter)
		elif min_interval is not None and self.min_interval == 0.0:
			self.jitter = 0.0
		else:
			self.jitter = REQUEST_JITTER
		self.cooldown_seconds = (
			RATE_LIMIT_COOLDOWN if cooldown_seconds is None else max(0.0, cooldown_seconds)
		)
		self.rotate_every = (
			MAX_REQUESTS_PER_ACCOUNT if rotate_every is None else max(1, int(rotate_every))
		)
		self.random_start = random_start
		self.lang = lang or LANG

		# 按事件循环存放锁：asyncio.Lock 不能跨 loop 复用（测试里每个 asyncio.run 都是新 loop）。
		self._rate_locks: dict[asyncio.AbstractEventLoop, asyncio.Lock] = {}
		self._anon_account = PixivAccount(cookie="")
		self._last_request_at: float | None = None
		self._cursor = 0
		self._current_uses = 0
		self._last_env_raw: str | None = None

		if cookies is not None:
			self._explicit_source = True
			self._accounts = _accounts_from_cookies(cookies)
			self._reset_cursor()
		elif cookie is not None:
			self._explicit_source = True
			self._accounts = _accounts_from_cookies(parse_cookies(cookie))
			self._reset_cursor()
		else:
			# 懒读取：首次用到时再读 PIXIV_COOKIE，避免依赖「.env 先于 sources 加载」的导入顺序
			self._explicit_source = False
			self._accounts = []


	def _reset_cursor(self) -> None:
		self._current_uses = 0
		if self.random_start and len(self._accounts) > 1:
			self._cursor = random.randrange(len(self._accounts))
		else:
			self._cursor = 0


	def _loop_lock(self) -> asyncio.Lock:
		loop = asyncio.get_running_loop()
		lock = self._rate_locks.get(loop)
		if lock is None:
			lock = asyncio.Lock()
			self._rate_locks[loop] = lock
		return lock


	def _sync_env(self) -> None:
		if self._explicit_source:
			return
		raw_env = os.environ.get(ENV_COOKIE, "")
		if raw_env == self._last_env_raw:
			return
		self._last_env_raw = raw_env
		self._accounts = _accounts_from_cookies(parse_cookies(raw_env))
		self._reset_cursor()


	@property
	def accounts(self) -> list[PixivAccount]:
		"""全部已配置的 ``PixivAccount``（环境变量变动时自动刷新）。"""
		self._sync_env()
		return list(self._accounts)


	@property
	def cookies(self) -> list[str]:
		"""全部已配置的规范化 Cookie 列表。"""
		return [account.cookie for account in self.accounts]


	@property
	def cookie(self) -> str:
		"""向后兼容：返回当前首选可用账号的 Cookie（无账号时返回空串）。"""
		accounts = self.accounts
		if not accounts:
			return ""
		now = time.monotonic()
		n = len(accounts)
		start = self._cursor % n
		for offset in range(n):
			account = accounts[(start + offset) % n]
			if account.is_available(now):
				return account.cookie
		return accounts[0].cookie


	@property
	def has_cookie(self) -> bool:
		"""没有 Cookie 也能读公开作品；R18 正文需要登录态。"""
		return bool(self.accounts)


	def set_cookie(self, cookie: str | None) -> None:
		"""热替换 Cookie（支持单值、``||`` 或多行字符串）；传空则清空为匿名。"""
		self._explicit_source = True
		self._last_env_raw = None
		self._accounts = _accounts_from_cookies(parse_cookies(cookie))
		self._reset_cursor()


	def set_cookies(self, cookies: Iterable[str | PixivAccount] | None) -> None:
		"""按列表热替换账号池；传 ``None`` 恢复从环境变量懒读取。"""
		if cookies is None:
			self._explicit_source = False
			self._last_env_raw = None
			self._accounts = []
			self._cursor = 0
			self._current_uses = 0
			return
		self._explicit_source = True
		self._last_env_raw = None
		self._accounts = _accounts_from_cookies(cookies)
		self._reset_cursor()


	def headers(
		self,
		account: PixivAccount | None = None,
		*,
		include_csrf: bool = False,
	) -> dict[str, str]:
		if account is not None:
			return account.headers(HEADERS, include_csrf=include_csrf)
		headers = dict(HEADERS)
		cookie = self.cookie
		if cookie:
			headers["Cookie"] = cookie
		return headers


	def _pick_candidates(self, url: str) -> list[PixivAccount]:
		self._sync_env()
		if not self._accounts:
			return [self._anon_account]

		now = time.monotonic()
		n = len(self._accounts)
		start = self._cursor % n
		ordered = [self._accounts[(start + offset) % n] for offset in range(n)]

		ready = [account for account in ordered if account.is_available(now)]
		if ready:
			chosen = ready[0]
			chosen_idx = self._accounts.index(chosen)
			# 当前游标账号不可用（冷却/失效）而顺延到下一个号时，重新从 0 计该账号的连续次数
			if chosen_idx != start:
				self._cursor = chosen_idx
				self._current_uses = 0
			self._current_uses += 1
			if self._current_uses >= self.rotate_every:
				self._cursor = (chosen_idx + 1) % n
				self._current_uses = 0
			return ready

		alive = [account for account in ordered if not account.dead]
		if not alive:
			raise PixivAuthError(
				"Pixiv 登录态已全部失效或无权限，请更新 PIXIV_COOKIE",
				raw=url,
			)
		raise PixivRateLimitError(
			"Pixiv 请求过于频繁（所有账号均在冷却中），请稍后重试",
			raw=url,
		)


	async def _select_candidates(self, url: str) -> list[PixivAccount]:
		async with self._loop_lock():
			return self._pick_candidates(url)


	async def _record_fallback(self, account: PixivAccount) -> None:
		"""首选号失败、故障转移到备用号并成功后，把游标与连续计数对齐到接替成功的号。"""
		if not account.is_authenticated:
			return
		async with self._loop_lock():
			if account not in self._accounts:
				return
			idx = self._accounts.index(account)
			n = len(self._accounts)
			if self._cursor == idx:
				self._current_uses += 1
			else:
				self._cursor = idx
				self._current_uses = 1
			if self._current_uses >= self.rotate_every:
				self._cursor = (idx + 1) % n
				self._current_uses = 0


	async def _acquire_slot(self, account: PixivAccount) -> None:
		"""同时约束单账号间隔、单 IP 全局间隔与随机抖动，锁外睡眠以支持并发错开。"""
		if self.min_interval <= 0 and self.global_min_interval <= 0 and self.jitter <= 0:
			return
		async with self._loop_lock():
			now = time.monotonic()
			account_ready = (
				now if account.last_used is None
				else account.last_used + self.min_interval
			)
			global_ready = (
				now if self._last_request_at is None
				else self._last_request_at + self.global_min_interval
			)
			extra = random.uniform(0.0, self.jitter) if self.jitter > 0 else 0.0
			target = max(now, account_ready, global_ready) + extra
			account.last_used = target
			self._last_request_at = target
		delay = target - time.monotonic()
		if delay > 0:
			await asyncio.sleep(delay)


	@staticmethod
	async def _fetch_json_for_account(
		url: str,
		account: PixivAccount,
		*,
		retry_on_429: bool,
	) -> object:
		headers = account.headers(HEADERS)
		if retry_on_429:
			return await get_json(url, headers=headers)
		return await get_json(url, headers=headers, retry_on_429=False)


	async def _get(
		self,
		url: str,
		*,
		check_payload: Callable[[JsonDict], Exception | None] | None = None,
	) -> JsonDict:
		"""轮换账号请求并统一成 ``JsonDict``，支持 401/403/429 及 R18 隐性失效自动切号。"""
		candidates = await self._select_candidates(url)
		retry_on_429 = len(candidates) <= 1
		last_error: Exception | None = None
		suspect_auth_accounts: list[PixivAccount] = []

		for index, account in enumerate(candidates):
			await self._acquire_slot(account)
			try:
				data = await self._fetch_json_for_account(
					url,
					account,
					retry_on_429=retry_on_429,
				)
			except HttpError as e:
				if e.status == 404:
					raise PixivNotFoundError("Pixiv 上不存在该作品", raw=url) from e
				if e.status == 401:
					if account.is_authenticated:
						account.dead = True
						logger.warning("Pixiv 账号 %s 返回 401，已标记失效并尝试切换", account.label)
					last_error = PixivAuthError(
						"Pixiv 登录态失效或无权限，请更新 PIXIV_COOKIE",
						raw=url,
					)
					if account.is_authenticated and index + 1 < len(candidates):
						continue
					raise last_error from e
				if e.status == 403:
					last_error = PixivAuthError(
						"Pixiv 登录态失效或无权限，请更新 PIXIV_COOKIE",
						raw=url,
					)
					if account.is_authenticated and index + 1 < len(candidates):
						# 先暂记疑似异常：若后续账号成功则剔除它；若全员 403 则多为目标作品受限，不误杀账号池
						suspect_auth_accounts.append(account)
						logger.warning("Pixiv 账号 %s 返回 403，尝试切换下一个账号", account.label)
						continue
					raise last_error from e
				if e.status == 429:
					if account.is_authenticated and self.cooldown_seconds > 0:
						account.cooldown_until = time.monotonic() + self.cooldown_seconds
						logger.warning(
							"Pixiv 账号 %s 触发 429，冷却 %.0fs",
							account.label,
							self.cooldown_seconds,
						)
					last_error = PixivRateLimitError(
						"Pixiv 请求过于频繁，请稍后重试",
						raw=url,
					)
					if account.is_authenticated and index + 1 < len(candidates):
						continue
					raise last_error from e
				raise PixivNetworkError("Pixiv 暂时无法访问，请稍后重试", raw=url) from e
			except ValueError as e:
				raise PixivParseError("Pixiv 返回的数据不是合法 JSON", raw=url) from e

			envelope = JsonDict.from_obj(data)
			if check_payload is not None:
				payload_error = check_payload(envelope)
				if payload_error is not None:
					last_error = payload_error
					if account.is_authenticated and index + 1 < len(candidates):
						suspect_auth_accounts.append(account)
						logger.warning(
							"Pixiv 账号 %s 未能读取受限内容，尝试切换下一个账号",
							account.label,
						)
						continue
					raise payload_error

			for bad in suspect_auth_accounts:
				bad.dead = True
				logger.warning("Pixiv 账号 %s 因鉴权失败已在故障转移后标记失效", bad.label)
			if index > 0:
				await self._record_fallback(account)
			return envelope

		assert last_error is not None
		raise last_error


	async def ensure_csrf_token(
		self,
		account: PixivAccount,
		*,
		refresh: bool = False,
	) -> str:
		"""为指定账号懒获取并绑定 ``x-csrf-token``（用于未来 POST 写接口）。"""
		if account.csrf_token and not refresh:
			return account.csrf_token
		if not account.is_authenticated:
			raise PixivAuthError("需要配置 PIXIV_COOKIE 才能获取 x-csrf-token", raw=REFERER)

		await self._acquire_slot(account)
		try:
			html = await get_text(REFERER, headers=account.headers(HEADERS))
		except HttpError as e:
			if e.status in (401, 403):
				raise PixivAuthError(
					"Pixiv 登录态失效或无权限，无法获取 x-csrf-token",
					raw=REFERER,
				) from e
			if e.status == 429:
				raise PixivRateLimitError("Pixiv 请求过于频繁，请稍后重试", raw=REFERER) from e
			raise PixivNetworkError("Pixiv 暂时无法访问，请稍后重试", raw=REFERER) from e

		token = extract_csrf_token(html)
		if not token:
			raise PixivAuthError(
				"未能从 Pixiv 页面提取 x-csrf-token，请检查 PIXIV_COOKIE 是否有效",
				raw=REFERER,
			)
		account.csrf_token = token
		return token


	async def get_novel(self, novel_id: str | int) -> JsonDict:
		"""小说详情（含正文 `content`；R18 需要 Cookie）。"""

		def _check_r18_novel(payload: JsonDict) -> Exception | None:
			if not payload or payload.error:
				return None
			detail = payload.body
			if detail is not None and not detail.content:
				if int(detail.xRestrict or 0) >= 1 or detail.isLoginOnly:
					# 这份空正文不能留在请求缓存里，否则之后配好 Cookie 还会拿到它
					drop_cached_json(url_novel_data(novel_id))
					return PixivAuthError(
						"该作品是 R18，需要配置 PIXIV_COOKIE 才能读取正文",
						raw=detail,
					)
			return None

		envelope = await self._get(url_novel_data(novel_id), check_payload=_check_r18_novel)
		if not envelope or envelope.error:
			raise PixivNotFoundError(f"Pixiv 上不存在小说 {novel_id}")
		return envelope


	async def get_series(self, series_id: str | int) -> JsonDict:
		"""系列详情（元信息，不含章节正文）。"""
		envelope = await self._get(url_series_data(series_id))
		detail = envelope.body if envelope else None
		if not detail:
			raise PixivNotFoundError(f"Pixiv 上不存在系列 {series_id}")
		# 未登录时 R18 系列的章节会被打码（标题 `-----`、available=false），
		# 提前报登录错误，而不是产出一个缺章 / 标题损坏的文件
		if int(detail.xRestrict or 0) >= 1 and not self.has_cookie:
			# 打码的元信息不能留在请求缓存里，否则之后配好 Cookie 还会拿到它
			drop_cached_json(url_series_data(series_id))
			raise PixivAuthError(
				"该系列是 R18，需要配置 PIXIV_COOKIE 才能读取", raw=detail)
		return envelope


	async def get_series_titles(self, series_id: str | int) -> list[JsonDict]:
		"""系列全部章节 ID + 标题，一次拿完，比逐页拉 content 更省。"""
		payload = await self._get(url_series_novels_title(series_id))
		# 外壳异常或 error: true 时按「没有章节」处理，交给上层决定要不要报错
		if not payload or payload.error:
			return []
		items = payload.get("body") or []
		if not isinstance(items, list):
			return []
		titles = [JsonDict.from_obj(item) for item in items if isinstance(item, dict)]
		# 未登录时部分章节 available=false：缓存下来会让之后带 Cookie 的请求继续缺章
		if not self.has_cookie and any(item.available is False for item in titles):
			drop_cached_json(url_series_novels_title(series_id))
		return titles


	async def get_author(self, user_id: str | int) -> JsonDict:
		"""作者资料：名字、头像；不含作品列表。"""
		body = await self._get(url_user_data(user_id))
		if not body or body.error:
			raise PixivNotFoundError(f"Pixiv 上不存在作者 {user_id}")
		return body


	async def get_author_works(self, user_id: str | int) -> JsonDict:
		"""作者全部作品 ID + 全部系列对象（`novels` / `novelSeries`）。"""
		body = await self._get(url_user_works_all(user_id))
		if not body or body.error:
			raise PixivNotFoundError(f"Pixiv 上不存在作者 {user_id}")
		return body
