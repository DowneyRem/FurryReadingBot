"""数据同步业务：调用 `data/` 下的同步脚本把运营数据提交到私有仓库。

分工：
  - 脚本负责 git add / commit / pull --rebase / push，并在内部加锁串行，
    所以定时任务和 `/sync` 不会同时改同一个仓库；
  - 本模块只负责选脚本、限时、收集输出，并把结果翻译成 handler 能用的结构。

平台差异只在「脚本」和「解释器」两处：
  - Linux / macOS：`data/sync_data.sh` + `/bin/bash`（服务器上的定时任务也用它）；
  - Windows：`data/sync_data.ps1` + `powershell.exe`（内容与 .sh 一一对应，
    只是把 flock 换成独占锁文件、路径换成相对于脚本自身）。

不 import telegram，便于单测。
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
IS_WINDOWS = os.name == "nt"

if IS_WINDOWS:
	SYNC_SCRIPT = ROOT / "data" / "sync_data.ps1"
	SYNC_SHELL = (
		"powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
	)
else:
	SYNC_SCRIPT = ROOT / "data" / "sync_data.sh"
	SYNC_SHELL = ("/bin/bash",)

# 要大于脚本里 flock -w 的 240 秒，避免排队时被 Python 先杀掉
SCRIPT_TIMEOUT = 300.0
# 超时杀掉脚本后，留给「把已经产生的输出收回来」的时间；收不到就不再等
TAIL_TIMEOUT = 5.0
# 脚本报告「没有数据变动」时的输出片段，用来把结果翻译成 skipped
SKIPPED_HINTS = ("没有发现数据变动", "跳过同步", "No changes")

# 脚本内部已有 flock；这里再加一把进程内锁，连点 /sync 时排队而不是同时拉起多个脚本。
# asyncio.Lock 绑定事件循环，所以按 loop 分组（测试里每个 asyncio.run 都是新 loop）。
_locks: dict[asyncio.AbstractEventLoop, asyncio.Lock] = {}


@dataclass(frozen=True)
class SyncResult:
	"""一次数据同步的结果；handler 据此回复。"""

	ok: bool
	output: str = ""
	returncode: int = 0
	timed_out: bool = False
	skipped: bool = False


class SyncTimeoutError(RuntimeError):
	"""同步脚本超时；`output` 是超时前已经产生的输出。"""

	def __init__(self, timeout: float, output: str = "") -> None:
		super().__init__(f"同步脚本超时（{timeout:g} 秒）")
		self.timeout = timeout
		self.output = output


def _lock() -> asyncio.Lock:
	"""取当前事件循环上的同步锁。"""
	loop = asyncio.get_running_loop()
	return _locks.setdefault(loop, asyncio.Lock())


def _kill_tree(process) -> None:
	"""杀掉脚本及其子进程。

	Windows 上 `Process.kill()` 只结束 powershell，`git` 子进程会留下来继续跑、
	继续握着仓库锁，所以先用 `taskkill /T` 清掉整棵进程树。
	"""
	pid = getattr(process, "pid", None)
	if IS_WINDOWS and pid:
		subprocess.run(
			["taskkill", "/F", "/T", "/PID", str(pid)],
			stdout=subprocess.DEVNULL,
			stderr=subprocess.DEVNULL,
			check=False,
		)
	try:
		process.kill()
	except ProcessLookupError:  # 已经被 taskkill 结束
		pass


def _decode(data: bytes) -> str:
	"""脚本输出统一按 UTF-8 解码（两个脚本都保证输出是 UTF-8）。"""
	return (data or b"").decode("utf-8", "replace").strip()


async def run_script(path: Path, *, timeout: float = SCRIPT_TIMEOUT) -> tuple[int, str]:
	"""执行同步脚本，返回 (退出码, 合并后的 stdout/stderr)；超时会杀掉脚本并抛异常。"""
	process = await asyncio.create_subprocess_exec(
		*SYNC_SHELL, str(path),
		cwd=str(path.parent),
		stdout=asyncio.subprocess.PIPE,
		stderr=asyncio.subprocess.STDOUT,
	)
	# 用 shield 保护 communicate()：Windows 上被 wait_for 取消后再调一次会等不到
	# EOF，`/sync` 会永久卡在锁上。超时后只再给 TAIL_TIMEOUT 秒回收部分输出。
	reading = asyncio.ensure_future(process.communicate())
	try:
		stdout, _ = await asyncio.wait_for(asyncio.shield(reading), timeout=timeout)
	except asyncio.TimeoutError:
		_kill_tree(process)
		try:
			stdout, _ = await asyncio.wait_for(reading, timeout=TAIL_TIMEOUT)
		except asyncio.TimeoutError:
			stdout = b""
		raise SyncTimeoutError(timeout, _decode(stdout)) from None
	return int(process.returncode or 0), _decode(stdout)


class SyncDataService:
	"""数据同步用例的统一入口。"""

	def __init__(
		self,
		script: str | Path | None = None,
		*,
		timeout: float = SCRIPT_TIMEOUT,
	) -> None:
		self._script = Path(script) if script is not None else None
		self._timeout = timeout

	@property
	def script(self) -> Path:
		return self._script or SYNC_SCRIPT

	async def sync(self) -> SyncResult:
		"""跑一次同步脚本；失败、超时、脚本缺失都返回结果而不是抛异常。"""
		path = self.script
		if not path.is_file():
			logger.error("数据同步脚本不存在：%s", path)
			return SyncResult(False, f"同步脚本不存在：{path}")

		async with _lock():
			try:
				code, output = await run_script(path, timeout=self._timeout)
			except SyncTimeoutError as exc:
				logger.warning("数据同步超时：%s（%s 秒）", path, exc.timeout)
				return SyncResult(
					False, exc.output, timed_out=True)
			except OSError as exc:
				logger.exception("启动数据同步脚本失败：%s", path)
				return SyncResult(False, f"无法执行同步脚本：{exc}")

		skipped = code == 0 and any(hint in output for hint in SKIPPED_HINTS)
		if code == 0:
			logger.info("数据同步完成：%s（skipped=%s）", path, skipped)
		else:
			logger.warning("数据同步失败：%s（退出码 %s）\n%s", path, code, output)
		return SyncResult(
			code == 0, output, returncode=code, skipped=skipped)
