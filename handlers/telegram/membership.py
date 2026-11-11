"""中转频道成员状态查询：管理员判定的 Telegram 适配器。

管理员身份只来自 Telegram——`TRANSIT_CHANNEL` 的 `creator` / `administrator`。
查询结果缓存 60 秒，避免每次点审核按钮都打一次 API；
权限撤销的生效延迟最多也就是这个 TTL。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from config import TRANSIT_CHANNEL
from policy.admin import AdminPolicy


logger = logging.getLogger(__name__)

CACHE_TTL = 60.0
_cache: dict[str, tuple[float, str | None]] = {}


async def get_transit_member_status(bot: Any, user_id: str | int) -> str | None:
	"""返回用户在中转频道的成员状态；未配置频道 / 查询失败返回 None。"""
	if bot is None or not TRANSIT_CHANNEL:
		return None

	key = str(user_id)
	if not key.isdigit():
		return None

	now = time.monotonic()
	cached = _cache.get(key)
	if cached is not None and cached[0] > now:
		return cached[1]

	try:
		member = await bot.get_chat_member(TRANSIT_CHANNEL, int(key))
	except Exception:
		# 查询失败不缓存，避免一次抖动把管理员锁在外面 60 秒
		logger.warning(
			"查询中转频道成员失败 chat=%s user=%s",
			TRANSIT_CHANNEL, key, exc_info=True)
		return None

	status = str(getattr(member, "status", "") or "") or None
	_cache[key] = (now + CACHE_TTL, status)
	return status


def transit_admin_policy(bot: Any) -> AdminPolicy:
	"""构造以中转频道成员状态为准的 `AdminPolicy`。"""
	return AdminPolicy(lambda user_id: get_transit_member_status(bot, user_id))


def clear_membership_cache() -> None:
	"""清空成员状态缓存；测试或手动改权限后立即生效用。"""
	_cache.clear()
