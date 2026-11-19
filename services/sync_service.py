"""数据同步业务：调用 `script/` 下的同步脚本把运营数据提交到私有仓库。

分工：
  - 脚本负责 git add / commit / pull --rebase / push，并在内部加锁串行，
    所以定时任务和 `/sync` 不会同时改同一个仓库；
  - 本模块只负责选脚本、限时、收集输出，并把结果翻译成 handler 能用的结构。

`/sync` 会传 `import_author=True`：先抓 Linpx 推荐作者合并进兽人作者名单，
再跑脚本提交；服务器定时任务直接调脚本（`script/sync_data.sh`），不经过这里，
所以自动同步不会联网抓推荐作者。

平台差异只在「脚本」和「解释器」两处：
  - Linux：`script/sync_data.sh` + `/bin/bash`（服务器上的定时任务也用它）；
  - Windows：`script/sync_data.ps1` + `powershell.exe`（与 .sh 契约一致：
    退出码 / 锁 / 提示，只是把 flock 换成独占锁文件）。

不 import telegram，便于单测。
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

from services.import_author_service import ImportAuthorResult, import_authors


logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
IS_WINDOWS = os.name == "nt"

if IS_WINDOWS:
	SYNC_SCRIPT = ROOT / "script" / "sync_data.ps1"
	SYNC_SHELL = (
		"powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
	)
else:
	SYNC_SCRIPT = ROOT / "script" / "sync_data.sh"
	SYNC_SHELL = ("/bin/bash",)

# 要大于脚本里 flock -w 的 60 秒，避免排队时被 Python 先杀掉
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
	"""一次数据同步的结果；handler 据此回复。

	`linpx` 只在请求了推荐作者合并时才有值（`/sync` 手动触发）；
	自动同步脚本不联网，保持 None。
	"""

	ok: bool
	output: str = ""
	returncode: int = 0
	timed_out: bool = False
	skipped: bool = False
	linpx: ImportAuthorResult | None = None


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
	继续握着仓库锁，所以先用 `taskkill /T` 清掉整棵进程树；
	POSIX 上脚本以独立会话启动，直接杀掉整个进程组。
	"""
	pid = getattr(process, "pid", None)
	if pid and IS_WINDOWS:
		subprocess.run(
			["taskkill", "/F", "/T", "/PID", str(pid)],
			stdout=subprocess.DEVNULL,
			stderr=subprocess.DEVNULL,
			check=False,
		)
	elif pid and hasattr(os, "killpg"):
		try:
			os.killpg(pid, signal.SIGKILL)
		except (ProcessLookupError, PermissionError):
			pass
	try:
		process.kill()
	except ProcessLookupError:  # 已经被 taskkill / killpg 结束
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
		# POSIX 上单独成组，超时才能连同 git 子进程一起杀掉
		**({} if IS_WINDOWS else {"start_new_session": True}),
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

	async def sync(self, *, import_author: bool = False) -> SyncResult:
		"""跑一次同步脚本；失败、超时、脚本缺失都返回结果而不是抛异常。

		`import_author=True` 时先把 Linpx 推荐作者合并进兽人作者名单，再提交。
		推荐作者抓取失败不阻止提交：本地已有的运营数据仍然要上传，
		失败原因放在 `result.linpx` 里让 handler 提示。
		"""
		path = self.script
		if not path.is_file():
			logger.error("数据同步脚本不存在：%s", path)
			return SyncResult(False, f"同步脚本不存在：{path}")

		async with _lock():
			# 与脚本共用同一把锁：连点 /sync 时排队执行，顺序固定为「先合并名单，再提交」
			linpx = await import_authors() if import_author else None
			try:
				code, output = await run_script(path, timeout=self._timeout)
			except SyncTimeoutError as exc:
				logger.warning("数据同步超时：%s（%s 秒）", path, exc.timeout)
				return SyncResult(
					False, exc.output, timed_out=True, linpx=linpx)
			except OSError as exc:
				logger.exception("启动数据同步脚本失败：%s", path)
				return SyncResult(
					False, f"无法执行同步脚本：{exc}", linpx=linpx)

		skipped = code == 0 and any(hint in output for hint in SKIPPED_HINTS)
		if code == 0:
			logger.info("数据同步完成：%s（skipped=%s）", path, skipped)
		else:
			logger.warning("数据同步失败：%s（退出码 %s）\n%s", path, code, output)
		return SyncResult(
			code == 0, output, returncode=code, skipped=skipped, linpx=linpx)
