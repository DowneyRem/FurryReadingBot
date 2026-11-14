"""services.sync_service：/sync 调用的脚本执行、超时与跳过判定。

用 monkeypatch 替换 `run_script`，不真的跑 git / bash，Windows 上也能测。

运行（在项目根目录）:
	python -m pytest test/test_sync_service.py -q
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from services import sync_service
from services.sync_service import (
	SyncDataService,
	SYNC_SCRIPT,
	SyncResult,
	SyncTimeoutError,
)


HERE = Path(__file__)


def run(coro):
	return asyncio.run(coro)


def patch_runner(monkeypatch, runner) -> None:
	monkeypatch.setattr(sync_service, "run_script", runner)


def test_sync_success(monkeypatch) -> None:
	async def fake_run(path, *, timeout):
		assert path == HERE
		return 0, "数据同步到私有仓库成功！"

	patch_runner(monkeypatch, fake_run)

	result = run(SyncDataService(HERE).sync())

	assert result == SyncResult(
		True, "数据同步到私有仓库成功！", returncode=0, skipped=False)


def test_sync_skipped_when_nothing_changed(monkeypatch) -> None:
	async def fake_run(path, *, timeout):
		return 0, "没有发现数据变动，跳过同步。"

	patch_runner(monkeypatch, fake_run)

	result = run(SyncDataService(HERE).sync())

	assert result.ok is True
	assert result.skipped is True


def test_sync_failure_keeps_output_and_code(monkeypatch) -> None:
	async def fake_run(path, *, timeout):
		return 128, "fatal: unable to access remote"

	patch_runner(monkeypatch, fake_run)

	result = run(SyncDataService(HERE).sync())

	assert result.ok is False
	assert result.returncode == 128
	assert "fatal" in result.output
	assert result.skipped is False


def test_sync_timeout_returns_partial_output(monkeypatch) -> None:
	async def fake_run(path, *, timeout):
		raise SyncTimeoutError(timeout, "等待其他同步任务超时")

	patch_runner(monkeypatch, fake_run)

	result = run(SyncDataService(HERE, timeout=5).sync())

	assert result.ok is False
	assert result.timed_out is True
	assert result.returncode == 0
	assert "等待其他同步任务超时" in result.output


def test_sync_script_missing_does_not_run(monkeypatch) -> None:
	calls: list = []

	async def fake_run(path, *, timeout):
		calls.append(path)
		return 0, ""

	patch_runner(monkeypatch, fake_run)

	result = run(SyncDataService(HERE / "no-such-sync.sh").sync())

	assert result.ok is False
	assert "同步脚本不存在" in result.output
	assert calls == []


def test_sync_oserror_is_reported(monkeypatch) -> None:
	async def fake_run(path, *, timeout):
		raise OSError("bash not found")

	patch_runner(monkeypatch, fake_run)

	result = run(SyncDataService(HERE).sync())

	assert result.ok is False
	assert "无法执行同步脚本" in result.output


def test_sync_runs_are_serialized(monkeypatch) -> None:
	"""连点 /sync：进程内锁保证同时只有一次脚本在跑。"""
	active = 0
	peak = 0

	async def fake_run(path, *, timeout):
		nonlocal active, peak
		active += 1
		peak = max(peak, active)
		await asyncio.sleep(0)
		active -= 1
		return 0, ""

	patch_runner(monkeypatch, fake_run)

	async def both() -> None:
		service = SyncDataService(HERE)
		await asyncio.gather(service.sync(), service.sync())

	run(both())

	assert peak == 1


def test_default_script_lives_in_data_dir() -> None:
	path = SYNC_SCRIPT

	assert path.name == "sync_data.sh"
	assert path.parent.name == "data"
	assert SyncDataService().script == path


class FakeProcess:
	def __init__(self, *, output: bytes = b"", returncode: int = 0, hang: bool = False) -> None:
		self._output = output
		self.returncode = returncode
		self._hang = hang
		self.killed = False

	async def communicate(self):
		if self._hang and not self.killed:
			await asyncio.sleep(3600)
		return self._output, None

	def kill(self) -> None:
		self.killed = True


def test_run_script_uses_configured_bash_and_collects_output(monkeypatch) -> None:
	captured: dict = {}

	async def fake_exec(*args, **kwargs):
		captured["args"] = args
		captured["kwargs"] = kwargs
		return FakeProcess(output="数据同步到私有仓库成功！\n".encode())

	monkeypatch.setattr(sync_service.asyncio, "create_subprocess_exec", fake_exec)

	code, output = run(sync_service.run_script(HERE, timeout=5))

	assert (code, output) == (0, "数据同步到私有仓库成功！")
	assert captured["args"] == (sync_service.SYNC_BASH, str(HERE))
	assert captured["kwargs"]["cwd"] == str(HERE.parent)
	assert captured["kwargs"]["stderr"] == asyncio.subprocess.STDOUT


def test_run_script_timeout_kills_process(monkeypatch) -> None:
	process = FakeProcess(hang=True)

	async def fake_exec(*args, **kwargs):
		return process

	monkeypatch.setattr(sync_service.asyncio, "create_subprocess_exec", fake_exec)

	with pytest.raises(SyncTimeoutError):
		run(sync_service.run_script(HERE, timeout=0.01))

	assert process.killed is True
