"""数据同步业务：调用 `data/sync_data.sh` 把运营数据提交到私有仓库。

分工：
  - 脚本负责 git add / commit / pull --rebase / push，并在内部用 flock 串行，
    所以定时任务和 `/sync` 不会同时改同一个仓库；
  - 本模块只负责选脚本、限时、收集输出，并把结果翻译成 handler 能用的结构。

不 import telegram，便于单测。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path


logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
SYNC_SCRIPT = ROOT / "data" / "sync_data.sh"
SYNC_BASH = "/bin/bash"
# 要大于脚本里 flock -w 的 240 秒，避免排队时被 Python 先杀掉
SCRIPT_TIMEOUT = 300.0
# 脚本报告「没有数据变动」时的输出片段，用来把结果翻译成 skipped
SKIPPED_HINTS = ("没有发现数据变动", "跳过同步", "No changes")

# 脚本内部已有 flock；这里再加一把进程内锁，连点 /sync 时排队而不是同时拉起多个 bash。
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


async def run_script(path: Path, *, timeout: float = SCRIPT_TIMEOUT) -> tuple[int, str]:
	"""执行同步脚本，返回 (退出码, 合并后的 stdout/stderr)；超时会杀掉脚本并抛异常。"""
	process = await asyncio.create_subprocess_exec(
		SYNC_BASH, str(path),
		cwd=str(path.parent),
		stdout=asyncio.subprocess.PIPE,
		stderr=asyncio.subprocess.STDOUT,
	)
	try:
		stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
	except asyncio.TimeoutError:
		process.kill()
		stdout, _ = await process.communicate()
		raise SyncTimeoutError(
			timeout, stdout.decode("utf-8", "replace").strip()) from None
	return int(process.returncode or 0), stdout.decode("utf-8", "replace").strip()


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
