"""handlers.author：`/furryadd`、`/blackadd` 管理员快捷方式。

两条命令先强制校验中转频道管理员（`transit_admin_policy`，默认拒绝），
通过后不写申请记录、不要截图，直接写名单，并把回执留在中转频道。
名单用 tmp_path 里的真实 `ListManager`，断言落在 JSON 上。

运行（在项目根目录）:
	.venv\\Scripts\\python.exe -m pytest test/test_admin_author_command.py -q
"""

from __future__ import annotations

import asyncio
import importlib
import json

from handlers.author import (
	BLACK_NOTE,
	BLACK_REMOVE_FOOTER,
	FURRY_NOTE,
	FURRY_REMOVE_FOOTER,
	add_black,
	add_furry,
	remove_black,
	remove_furry,
)
from policy.admin import AdminDecision
from services.takedown_service import TakedownResult
from storage import ListManager


# handlers/__init__ 导出的 add_furry 是函数，需要 patch 模块属性时显式取模块
author_module = importlib.import_module("handlers.author")

AUTHOR_ID = "10809330"
AUTHOR_URL = f"https://www.pixiv.net/users/{AUTHOR_ID}"
LINPX_URL = f"https://linpx.ink/pixiv/user/{AUTHOR_ID}"


def run(coro):
	return asyncio.run(coro)


class FakeAuthor:
	def __init__(self, name: str) -> None:
		self.author_name = name


class FakeUser:
	id = 9
	first_name = "Admin"
	last_name = "User"


class FakeMessage:
	def __init__(self) -> None:
		self.replies: list[str] = []

	async def reply_text(self, text: str, **kwargs) -> None:
		self.replies.append(text)


class FakeUpdate:
	def __init__(self) -> None:
		self.effective_user = FakeUser()
		self.effective_message = FakeMessage()


class FakeContext:
	def __init__(self, *args: str) -> None:
		self.args = list(args)
		self.bot = object()


class FakeAdminPolicy:
	def __init__(self, *, allowed: bool, status: str | None) -> None:
		self.allowed = allowed
		self.status = status

	async def check(self, user_id):
		return AdminDecision(str(user_id), self.allowed, self.status)


def patch(
		monkeypatch, tmp_path,
		*,
		allowed: bool = True,
		status: str | None = "administrator",
		name: str = "某作者",
		fetch_error: Exception | None = None,
		takedown: TakedownResult | None = None,
) -> tuple[ListManager, list[tuple[str, object]], list[str]]:
	"""接线：名单用临时目录，其余外部依赖（抓取 / 中转 / 下架 / 管理员）换假实现。"""
	manager = ListManager(tmp_path)
	sent: list[tuple[str, object]] = []
	takedowns: list[str] = []

	async def fake_fetch(link: str):
		if fetch_error is not None:
			raise fetch_error
		return FakeAuthor(name)

	async def fake_send(context, text: str, *, reply_markup=None) -> bool:
		sent.append((text, reply_markup))
		return True

	async def fake_takedown(context, author_id):
		takedowns.append(str(author_id))
		return takedown if takedown is not None else TakedownResult(str(author_id))

	monkeypatch.setattr(author_module, "get_lists", lambda: manager)
	monkeypatch.setattr(author_module, "fetch", fake_fetch)
	monkeypatch.setattr(
		author_module, "transit_admin_policy",
		lambda bot: FakeAdminPolicy(allowed=allowed, status=status))
	monkeypatch.setattr(author_module, "send_transit_message", fake_send)
	monkeypatch.setattr(author_module, "takedown_history", fake_takedown)
	return manager, sent, takedowns


def authors(path) -> dict:
	"""读名单 JSON 的 `authors` 段（与生产格式一致）。"""
	return json.loads(path.read_text(encoding="utf-8"))["authors"]


def test_add_furry_requires_admin(monkeypatch, tmp_path) -> None:
	_, sent, _ = patch(monkeypatch, tmp_path, allowed=False, status="member")
	update = FakeUpdate()

	run(add_furry(update, FakeContext(AUTHOR_ID)))

	assert "仅中转频道管理员" in update.effective_message.replies[0]
	assert authors(tmp_path / "furry_authors.json") == {}
	assert sent == []


def test_add_black_requires_admin(monkeypatch, tmp_path) -> None:
	"""强制校验：非管理员连用法提示都拿不到。"""
	_, sent, takedowns = patch(
		monkeypatch, tmp_path, allowed=False, status="member")
	update = FakeUpdate()

	run(add_black(update, FakeContext()))

	assert "仅中转频道管理员" in update.effective_message.replies[0]
	assert authors(tmp_path / "black_authors.json") == {}
	assert takedowns == []
	assert sent == []


def test_add_black_unknown_admin_status_replies_retry(monkeypatch, tmp_path) -> None:
	"""查不到成员状态（频道没配 / 查询失败）时不要误报「不是管理员」。"""
	patch(monkeypatch, tmp_path, allowed=False, status=None)
	update = FakeUpdate()

	run(add_black(update, FakeContext(AUTHOR_ID)))

	assert "无法确认你的管理员身份" in update.effective_message.replies[0]


def test_add_furry_without_arg_sends_usage(monkeypatch, tmp_path) -> None:
	_, sent, _ = patch(monkeypatch, tmp_path)
	update = FakeUpdate()

	run(add_furry(update, FakeContext()))

	assert "/furryadd" in update.effective_message.replies[0]
	assert authors(tmp_path / "furry_authors.json") == {}
	assert sent == []


def test_add_furry_writes_json_and_posts_receipt(monkeypatch, tmp_path) -> None:
	_, sent, _ = patch(monkeypatch, tmp_path)
	update = FakeUpdate()

	run(add_furry(update, FakeContext(AUTHOR_ID)))

	assert authors(tmp_path / "furry_authors.json")[AUTHOR_ID] == {
		"name": "某作者", "note": FURRY_NOTE}
	text, markup = sent[0]
	assert "🐺 #兽人作者申请已通过" in text
	assert f"✅ 通过：某作者（#a{AUTHOR_ID}）" in text
	assert "👤 审核：Admin User（#u9）" in text
	assert "🈸" not in text  # 没有申请记录，回执不出现「申请」那行
	assert text.endswith(f"🛡 {FURRY_NOTE}")  # 尾注标明是管理员直接加的
	assert markup is None
	assert "中转频道已留下回执" in update.effective_message.replies[-1]


def test_add_furry_accepts_linpx_link(monkeypatch, tmp_path) -> None:
	"""参数解析与 `/furry` 一致：Linpx 作者链接归一化成 Pixiv 主页。"""
	patch(monkeypatch, tmp_path)
	fetched: list[str] = []

	async def fake_fetch(link: str):
		fetched.append(link)
		return FakeAuthor("某作者")

	monkeypatch.setattr(author_module, "fetch", fake_fetch)

	run(add_furry(FakeUpdate(), FakeContext(LINPX_URL)))

	assert fetched == [AUTHOR_URL]
	assert authors(tmp_path / "furry_authors.json")[AUTHOR_ID]["name"] == "某作者"


def test_add_furry_rejects_non_author_arg(monkeypatch, tmp_path) -> None:
	_, sent, _ = patch(monkeypatch, tmp_path)
	update = FakeUpdate()

	run(add_furry(update, FakeContext("https://linpx.ink/pixiv/novel/123")))

	assert "/furryadd" in update.effective_message.replies[0]
	assert authors(tmp_path / "furry_authors.json") == {}
	assert sent == []


def test_add_furry_existing_keeps_note_and_skips_receipt(monkeypatch, tmp_path) -> None:
	"""已在名单里：不重复写入、不覆盖人工 note，也不发中转回执。"""
	manager, sent, _ = patch(monkeypatch, tmp_path)
	manager.furrylist.add(AUTHOR_ID, name="某作者", note="兽人阅读")
	update = FakeUpdate()

	run(add_furry(update, FakeContext(AUTHOR_ID)))

	assert "已在兽人作者名单中" in update.effective_message.replies[-1]
	assert authors(tmp_path / "furry_authors.json")[AUTHOR_ID]["note"] == "兽人阅读"
	assert sent == []


def test_add_furry_blacklisted_is_refused(monkeypatch, tmp_path) -> None:
	"""黑名单优先：写进兽人名单也不会放行，直接拒绝。"""
	manager, sent, _ = patch(monkeypatch, tmp_path)
	manager.add_blacklist(AUTHOR_ID, name="某作者", note="作者本人申请下架")
	update = FakeUpdate()

	run(add_furry(update, FakeContext(AUTHOR_ID)))

	assert "已在黑名单中，未写入" in update.effective_message.replies[-1]
	assert authors(tmp_path / "furry_authors.json") == {}
	assert sent == []


def test_add_furry_writes_even_if_name_fetch_fails(monkeypatch, tmp_path) -> None:
	"""写名单不依赖抓取：抓不到名字就只记 ID，并提示操作人。"""
	_, sent, _ = patch(monkeypatch, tmp_path, fetch_error=RuntimeError("linpx down"))
	update = FakeUpdate()

	run(add_furry(update, FakeContext(AUTHOR_ID)))

	assert authors(tmp_path / "furry_authors.json")[AUTHOR_ID] == {
		"name": "", "note": FURRY_NOTE}
	assert f"✅ 通过：{AUTHOR_ID}（#a{AUTHOR_ID}）" in sent[0][0]
	assert "没抓到作者名" in update.effective_message.replies[-1]


def test_add_black_writes_json_and_takedowns(monkeypatch, tmp_path) -> None:
	manager, sent, takedowns = patch(
		monkeypatch, tmp_path,
		takedown=TakedownResult(AUTHOR_ID, deleted=2))
	manager.add_furrylist(AUTHOR_ID, name="某作者", note="兽人作者申请通过")
	update = FakeUpdate()

	run(add_black(update, FakeContext(AUTHOR_ID)))

	assert authors(tmp_path / "furry_authors.json") == {}
	assert authors(tmp_path / "black_authors.json")[AUTHOR_ID] == {
		"name": "某作者", "note": BLACK_NOTE}
	assert takedowns == [AUTHOR_ID]

	text, markup = sent[0]
	assert "🈲 #作者下架申请已通过" in text
	assert f"🚫 已下架：某作者（#a{AUTHOR_ID}）" in text
	assert "🗑️ 已删除：2 条历史分享" in text
	assert "👤 审核人：Admin User（#u9）" in text
	assert "🈸" not in text  # 没有申请记录，回执不出现「申请人」那行
	assert text.endswith(f"🛡 {BLACK_NOTE}")  # 尾注标明是管理员直接拉黑的
	assert markup is None
	assert "🗑️ 已删除：2 条历史分享" in update.effective_message.replies[-1]


def test_add_black_failed_takedown_offers_retry(monkeypatch, tmp_path) -> None:
	_, sent, _ = patch(
		monkeypatch, tmp_path,
		takedown=TakedownResult(AUTHOR_ID, failed=1, errors=("boom",)))
	update = FakeUpdate()

	run(add_black(update, FakeContext(AUTHOR_ID)))

	text, markup = sent[0]
	assert "1 条删除失败" in text
	assert markup.inline_keyboard[0][0].callback_data == f"rbt;{AUTHOR_ID}"
	assert "1 条删除失败" in update.effective_message.replies[-1]


def test_add_black_existing_skips_takedown_and_receipt(monkeypatch, tmp_path) -> None:
	manager, sent, takedowns = patch(monkeypatch, tmp_path)
	manager.add_blacklist(AUTHOR_ID, name="某作者", note="作者本人申请下架")
	update = FakeUpdate()

	run(add_black(update, FakeContext(AUTHOR_ID)))

	assert "已在黑名单中" in update.effective_message.replies[-1]
	assert authors(tmp_path / "black_authors.json")[AUTHOR_ID]["note"] == "作者本人申请下架"
	assert takedowns == []
	assert sent == []


def test_remove_furry_requires_admin(monkeypatch, tmp_path) -> None:
	manager, sent, _ = patch(monkeypatch, tmp_path, allowed=False, status="member")
	manager.add_furrylist(AUTHOR_ID, name="某作者", note="兽人阅读")
	update = FakeUpdate()

	run(remove_furry(update, FakeContext(AUTHOR_ID)))

	assert "仅中转频道管理员" in update.effective_message.replies[0]
	assert manager.is_furryauthor(AUTHOR_ID)
	assert sent == []


def test_remove_furry_not_in_list(monkeypatch, tmp_path) -> None:
	_, sent, _ = patch(monkeypatch, tmp_path)
	update = FakeUpdate()

	run(remove_furry(update, FakeContext(AUTHOR_ID)))

	assert "不在兽人作者名单中" in update.effective_message.replies[-1]
	assert sent == []


def test_remove_furry_removes_and_posts_receipt(monkeypatch, tmp_path) -> None:
	manager, sent, _ = patch(monkeypatch, tmp_path)
	manager.add_furrylist(AUTHOR_ID, name="某作者", note="兽人阅读")
	update = FakeUpdate()

	run(remove_furry(update, FakeContext(AUTHOR_ID)))

	assert not manager.is_furryauthor(AUTHOR_ID)
	assert authors(tmp_path / "furry_authors.json") == {}
	# 不拉黑、不删历史：黑名单与分享都不该被碰
	assert authors(tmp_path / "black_authors.json") == {}

	text, markup = sent[0]
	assert "🐺 #兽人作者名单已移除" in text
	assert f"➖ 已移除：某作者（#a{AUTHOR_ID}）" in text
	assert "👤 操作：Admin User（#u9）" in text
	assert text.endswith(FURRY_REMOVE_FOOTER)
	assert markup is None
	assert f"✅ 已移出兽人作者名单：某作者（#a{AUTHOR_ID}）" in update.effective_message.replies[-1]


def test_remove_furry_keeps_blacklist_and_says_so(monkeypatch, tmp_path) -> None:
	"""黑名单优先：移出兽人名单只是清理数据，作者依然不能下载 / 分享。"""
	manager, _, _ = patch(monkeypatch, tmp_path)
	manager.add_furrylist(AUTHOR_ID, name="某作者", note="兽人阅读")
	manager.add_blacklist(AUTHOR_ID, name="某作者", note="作者本人申请下架")
	update = FakeUpdate()

	run(remove_furry(update, FakeContext(AUTHOR_ID)))

	assert not manager.is_furryauthor(AUTHOR_ID)
	assert manager.is_blacklisted(AUTHOR_ID)
	assert "仍在黑名单中" in update.effective_message.replies[-1]


def test_remove_black_not_in_list(monkeypatch, tmp_path) -> None:
	_, sent, takedowns = patch(monkeypatch, tmp_path)
	update = FakeUpdate()

	run(remove_black(update, FakeContext(AUTHOR_ID)))

	assert "不在黑名单中" in update.effective_message.replies[-1]
	assert takedowns == []  # 不在黑名单就不碰历史分享
	assert sent == []


def test_remove_black_retries_takedown_then_unblacklists(monkeypatch, tmp_path) -> None:
	manager, sent, takedowns = patch(
		monkeypatch, tmp_path,
		takedown=TakedownResult(AUTHOR_ID, deleted=2))
	manager.add_blacklist(AUTHOR_ID, name="某作者", note="作者本人申请下架")
	update = FakeUpdate()

	run(remove_black(update, FakeContext(AUTHOR_ID)))

	assert takedowns == [AUTHOR_ID]  # 解除前先把历史分享删一遍
	assert not manager.is_blacklisted(AUTHOR_ID)
	assert authors(tmp_path / "black_authors.json") == {}
	assert not manager.is_furryauthor(AUTHOR_ID)  # 解除拉黑不会自动加回兽人名单

	text, markup = sent[0]
	assert "🈲 #作者黑名单已解除" in text
	assert f"➖ 已移除：某作者（#a{AUTHOR_ID}）" in text
	assert "🗑️ 已删除：2 条历史分享" in text
	assert "👤 操作：Admin User（#u9）" in text
	assert text.endswith(BLACK_REMOVE_FOOTER)
	assert markup is None

	reply = update.effective_message.replies[-1]
	assert f"✅ 已解除拉黑：某作者（#a{AUTHOR_ID}）" in reply
	assert "历史分享不会恢复" in reply


def test_remove_black_without_records_skips_takedown_line(monkeypatch, tmp_path) -> None:
	"""没有历史分享记录时不显示「🗑️ 已删除：0 条」。"""
	manager, sent, _ = patch(monkeypatch, tmp_path)
	manager.add_blacklist(AUTHOR_ID, name="某作者", note="作者本人申请下架")

	run(remove_black(FakeUpdate(), FakeContext(AUTHOR_ID)))

	assert "🗑️" not in sent[0][0]


def test_remove_black_blocked_when_takedown_fails(monkeypatch, tmp_path) -> None:
	"""还有删不掉的历史分享：不解除拉黑，否则「重试删除」按钮会失效。"""
	manager, sent, _ = patch(
		monkeypatch, tmp_path,
		takedown=TakedownResult(AUTHOR_ID, deleted=1, failed=1, errors=("boom",)))
	manager.add_blacklist(AUTHOR_ID, name="某作者", note="作者本人申请下架")
	update = FakeUpdate()

	run(remove_black(update, FakeContext(AUTHOR_ID)))

	assert manager.is_blacklisted(AUTHOR_ID)
	assert authors(tmp_path / "black_authors.json")[AUTHOR_ID]["note"] == "作者本人申请下架"
	assert sent == []

	reply = update.effective_message.replies[-1]
	assert "未解除拉黑" in reply
	assert "1 条删除失败" in reply
	assert "/blackremove" in reply
