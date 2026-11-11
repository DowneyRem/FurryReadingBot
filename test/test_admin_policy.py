"""AdminPolicy：以 Telegram 频道管理员身份为准的管理员判定。

运行（在项目根目录）:
	python -m pytest test/test_admin_policy.py -q

产品语义：管理员不维护 ID 名单，只看 `TRANSIT_CHANNEL` 的 Telegram 身份。
	creator / administrator → 管理员
	其他 / 查不到 / 查询失败 → 非管理员
"""

from __future__ import annotations

import asyncio

from policy.admin import AdminPolicy, is_admin_status


def run(coro):
	return asyncio.run(coro)


def policy_for(status: str | None) -> AdminPolicy:
	async def resolve(user_id: str) -> str | None:
		return status

	return AdminPolicy(resolve)


def test_is_admin_status() -> None:
	assert is_admin_status("creator") is True
	assert is_admin_status("administrator") is True
	assert is_admin_status("member") is False
	assert is_admin_status("restricted") is False
	assert is_admin_status("left") is False
	assert is_admin_status("kicked") is False
	assert is_admin_status(None) is False


def test_channel_admin_allowed() -> None:
	decision = run(policy_for("administrator").check(42))

	assert decision.allowed is True
	assert decision.user_id == "42"
	assert decision.status == "administrator"


def test_channel_creator_allowed() -> None:
	assert run(policy_for("creator").check("42")).allowed is True


def test_plain_member_denied() -> None:
	decision = run(policy_for("member").check(42))

	assert decision.allowed is False
	assert decision.status == "member"


def test_missing_status_denied() -> None:
	assert run(policy_for(None).check(42)).allowed is False


def test_resolver_failure_denied() -> None:
	async def boom(user_id: str) -> str | None:
		raise RuntimeError("telegram down")

	decision = run(AdminPolicy(boom).check(42))

	assert decision.allowed is False


def test_no_resolver_denied() -> None:
	assert run(AdminPolicy().check(42)).allowed is False
