"""handlers.sync：/sync 的结果文案、消息编辑与「不校验管理员」。

运行（在项目根目录）:
	python -m pytest test/test_sync_command.py -q
"""

from __future__ import annotations

import asyncio
import importlib

from handlers.sync import format_sync_result, sync as sync_command
from services import SyncResult

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
	def __init__(self, result: SyncResult) -> None:
		self._result = result

	async def sync(self) -> SyncResult:
		return self._result


def patch_service(monkeypatch, result: SyncResult) -> None:
	monkeypatch.setattr(sync_module, "SyncDataService", lambda: FakeService(result))


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


def test_sync_command_needs_no_admin(monkeypatch) -> None:
	"""暂时不校验管理员：FakeUpdate 没有 chat / 成员查询，命令也要照常跑完。"""
	patch_service(monkeypatch, SyncResult(True, "ok"))
	update = FakeUpdate()

	run(sync_command(update, FakeContext()))

	assert update.effective_message.notice.edits


def test_format_escapes_html_and_truncates() -> None:
	text = format_sync_result(SyncResult(True, "<b>boom</b>"))

	assert "&lt;b&gt;boom&lt;/b&gt;" in text
	assert "<b>boom</b>" not in text


def test_format_output_is_capped() -> None:
	text = format_sync_result(SyncResult(True, "x" * 5000))

	assert "已截断" in text
	assert len(text) < 5000
