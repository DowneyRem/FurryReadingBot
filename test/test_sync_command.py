"""handlers.sync：/sync 的管理员校验、结果文案与消息编辑。

运行（在项目根目录）:
	python -m pytest test/test_sync_command.py -q
"""

from __future__ import annotations

import asyncio
import importlib

from handlers.sync import format_sync_result, sync as sync_command
from policy.admin import AdminDecision, AdminPolicy
from services import SyncResult
from services.import_author_service import ImportAuthorResult

# handlers/__init__ 导出的 sync 是函数，会遮住同名子模块，这里显式取模块
sync_module = importlib.import_module("handlers.sync")


def run(coro):
	return asyncio.run(coro)


class FakeUser:
	id = 42
	first_name = "Anyone"
	last_name = "User"


class FakeNotice:
	"""handler 先发「正在同步」，随后把同一条消息编辑成结果。"""

	def __init__(self) -> None:
		self.edits: list[tuple[str, dict]] = []
		self.fail = False

	async def edit_text(self, text: str, **kwargs) -> None:
		if self.fail:
			raise RuntimeError("message can't be edited")
		self.edits.append((text, kwargs))


class FakeMessage:
	def __init__(self) -> None:
		self.replies: list[tuple[str, dict]] = []
		self.notice = FakeNotice()

	async def reply_text(self, text: str, **kwargs):
		self.replies.append((text, kwargs))
		return self.notice if len(self.replies) == 1 else None


class FakeUpdate:
	def __init__(self) -> None:
		self.effective_user = FakeUser()
		self.effective_message = FakeMessage()


class FakeContext:
	bot = object()


class FakeService:
	"""记录被调用次数与 import_author：非管理员时不该有任何同步动作。"""

	def __init__(self, result: SyncResult) -> None:
		self._result = result
		self.calls = 0
		self.import_author: bool | None = None

	async def sync(self, *, import_author: bool = False) -> SyncResult:
		self.calls += 1
		self.import_author = import_author
		return self._result


class FakeAdminPolicy:
	def __init__(self, allowed: bool) -> None:
		self.allowed = allowed

	async def check(self, user_id):
		return AdminDecision(str(user_id), self.allowed)


def patch_service(monkeypatch, result: SyncResult, *, admin: bool = True) -> FakeService:
	"""替换同步服务与管理员判定；`admin=False` 用来测拒绝分支。"""
	service = FakeService(result)
	monkeypatch.setattr(sync_module, "SyncDataService", lambda: service)
	monkeypatch.setattr(
		sync_module, "transit_admin_policy", lambda bot: FakeAdminPolicy(admin))
	return service


def test_sync_command_reports_success(monkeypatch) -> None:
	patch_service(monkeypatch, SyncResult(True, "数据同步到私有仓库成功！"))
	update = FakeUpdate()

	run(sync_command(update, FakeContext()))

	assert update.effective_message.replies[0][0].startswith("⏳")
	text, kwargs = update.effective_message.notice.edits[-1]
	assert "已同步到私有仓库" in text
	assert "数据同步到私有仓库成功！" in text
	assert kwargs["parse_mode"] == "HTML"


def test_sync_command_reports_skipped(monkeypatch) -> None:
	patch_service(monkeypatch, SyncResult(True, "没有发现数据变动，跳过同步。", skipped=True))
	update = FakeUpdate()

	run(sync_command(update, FakeContext()))

	text, _ = update.effective_message.notice.edits[-1]
	assert "没有数据变动" in text


def test_sync_command_reports_failure(monkeypatch) -> None:
	patch_service(monkeypatch, SyncResult(False, "fatal: unable to access", returncode=128))
	update = FakeUpdate()

	run(sync_command(update, FakeContext()))

	text, _ = update.effective_message.notice.edits[-1]
	assert "退出码 128" in text
	assert "fatal: unable to access" in text


def test_sync_command_reports_missing_script_without_fake_code(monkeypatch) -> None:
	"""脚本缺失时 returncode 是 0：不能回「退出码 0」这种自相矛盾的话。"""
	patch_service(
		monkeypatch, SyncResult(False, "同步脚本不存在：/tmp/sync_data.sh"))
	update = FakeUpdate()

	run(sync_command(update, FakeContext()))

	text, _ = update.effective_message.notice.edits[-1]
	assert "数据同步失败" in text
	assert "退出码" not in text
	assert "同步脚本不存在" in text


def test_sync_command_reports_timeout(monkeypatch) -> None:
	patch_service(
		monkeypatch,
		SyncResult(False, "等待其他同步任务超时", timed_out=True))
	update = FakeUpdate()

	run(sync_command(update, FakeContext()))

	text, _ = update.effective_message.notice.edits[-1]
	assert "超时" in text


def test_sync_command_falls_back_when_edit_fails(monkeypatch) -> None:
	patch_service(monkeypatch, SyncResult(True, "ok"))
	update = FakeUpdate()
	update.effective_message.notice.fail = True

	run(sync_command(update, FakeContext()))

	assert len(update.effective_message.replies) == 2
	assert "已同步到私有仓库" in update.effective_message.replies[-1][0]


def test_sync_command_requires_admin(monkeypatch) -> None:
	"""非管理员：只回一句拒绝，不发「⏳」、也不碰同步服务。"""
	service = patch_service(monkeypatch, SyncResult(True, "ok"), admin=False)
	update = FakeUpdate()

	run(sync_command(update, FakeContext()))

	assert len(update.effective_message.replies) == 1
	assert "仅中转频道管理员" in update.effective_message.replies[0][0]
	assert update.effective_message.notice.edits == []
	assert service.calls == 0


def test_sync_command_denies_when_status_unknown(monkeypatch) -> None:
	"""默认拒绝：用真实 AdminPolicy，成员状态查不到（返回 None）也按非管理员处理。"""
	service = patch_service(monkeypatch, SyncResult(True, "ok"))

	async def no_status(user_id: str) -> None:
		return None

	monkeypatch.setattr(
		sync_module, "transit_admin_policy", lambda bot: AdminPolicy(no_status))
	update = FakeUpdate()

	run(sync_command(update, FakeContext()))

	assert "仅中转频道管理员" in update.effective_message.replies[0][0]
	assert service.calls == 0


def test_sync_command_merges_linpx_authors(monkeypatch) -> None:
	"""手动 /sync 会要求先合并推荐作者，并把新增数写进回复。"""
	linpx = ImportAuthorResult(
		True, total=10, skipped=7,
		new_authors=(("1", "甲"), ("2", "乙"), ("3", "丙")))
	service = patch_service(
		monkeypatch, SyncResult(True, "数据同步到私有仓库成功！", linpx=linpx))
	update = FakeUpdate()

	run(sync_command(update, FakeContext()))

	text, _ = update.effective_message.notice.edits[-1]
	assert service.import_author is True
	assert "共 10 个" in text
	assert "新增 3 个" in text


def test_sync_command_reports_linpx_failure(monkeypatch) -> None:
	"""推荐作者抓不到：仍然报告数据已提交，但明确提示抓取失败。"""
	linpx = ImportAuthorResult(False, error="Linpx 暂时无法访问")
	patch_service(
		monkeypatch, SyncResult(True, "数据同步到私有仓库成功！", linpx=linpx))
	update = FakeUpdate()

	run(sync_command(update, FakeContext()))

	text, _ = update.effective_message.notice.edits[-1]
	assert "Linpx 推荐作者抓取失败" in text
	assert "Linpx 暂时无法访问" in text
	assert "已同步到私有仓库" in text


def test_format_escapes_html_and_truncates() -> None:
	text = format_sync_result(SyncResult(True, "<b>boom</b>"))

	assert "&lt;b&gt;boom&lt;/b&gt;" in text
	assert "<b>boom</b>" not in text


def test_format_output_is_capped() -> None:
	text = format_sync_result(SyncResult(True, "x" * 5000))

	assert "已截断" in text
	assert len(text) < 5000
