"""管理员判定：以中转频道管理员身份为准，不维护任何 ID 名单。

管理员来源只有一个：Telegram 频道成员状态（由 handlers 注入查询函数）。

	creator / administrator  → 管理员
	member / restricted / left / kicked / 查不到 → 非管理员

**默认拒绝**：没有注入查询函数、查询失败、未配置频道，一律按非管理员处理。

这样加 / 删管理员只需要在 Telegram 里调整频道权限，代码与 `.env` 都不用改。
本模块不 import telegram，便于单测。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable


logger = logging.getLogger(__name__)
ADMIN_STATUSES = frozenset({"creator", "administrator"})
MemberStatusResolver = Callable[[str], Awaitable[str | None]]


def is_admin_status(status: str | None) -> bool:
	"""Telegram 成员状态是否代表管理员。"""
	return str(status or "") in ADMIN_STATUSES


@dataclass(frozen=True)
class AdminDecision:
	"""一次管理员判定的结果；`status` 便于日志定位原因。"""
	
	user_id: str
	allowed: bool
	status: str | None = None


class AdminPolicy:
	"""默认拒绝的管理员判定器。"""

	def __init__(self, resolve_status: MemberStatusResolver | None = None) -> None:
		self._resolve_status = resolve_status


	async def check(self, user_id: str | int) -> AdminDecision:
		"""查询用户在频道里的成员状态，据此判断是否管理员。"""
		key = str(user_id)
		if self._resolve_status is None:
			return AdminDecision(key, False)
		try:
			status = await self._resolve_status(key)
		except Exception:
			logger.warning("查询管理员身份失败 user=%s", key, exc_info=True)
			return AdminDecision(key, False)
		return AdminDecision(key, is_admin_status(status), status)
