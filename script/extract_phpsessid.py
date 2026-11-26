r"""从文本提取或通过本地浏览器登录获取 Pixiv ``PHPSESSID`` 的工具。

支持两种模式：
  1. 文本提取（默认）：支持完整 Cookie 串、JSON、curl、URL 编码、DevTools 表格 / ``cookies.txt``、裸值；
  2. 半自动登录（``--login``）：使用独立临时配置启动本机 Chrome（默认，可选 ``--browser edge|auto``），
     用户手工完成登录与人机验证后，脚本通过 CDP 自动捕获 ``PHPSESSID``（含 ``HttpOnly``）并关窗清理。

用法示例（在项目根目录）:
# 1. 默认用 Chrome 登录 1 个账号，直接输出裸 PHPSESSID
.venv\Scripts\python.exe script/extract_phpsessid.py --login

# 2. 用 Chrome 依次登录 5 个账号，输出每行一个裸值（可直接贴进 GitHub Secret PIXIV_COOKIE）
.venv\Scripts\python.exe script/extract_phpsessid.py --login --count 5

# 3. 依次登录 5 个账号，直接输出为 .env 格式并写入文件
.venv\Scripts\python.exe script/extract_phpsessid.py --login --count 5 --format env -o pixiv.env

# 4. 如需改用 Edge 或单账号超时调大到 10 分钟
.venv\Scripts\python.exe script/extract_phpsessid.py --login --browser edge --timeout 600
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

import aiohttp


PIXIV_LOGIN_URL = "https://accounts.pixiv.net/login"
# 已登录的 Pixiv PHPSESSID 形如 <正整数UID>_<16位以上字母数字>；未登录网页种下的是无下划线的 32 位游客串
_AUTH_PHPSESSID_RE = re.compile(r"^[1-9]\d*_[A-Za-z0-9]{16,}$")
_UID_PREFIX_RE = re.compile(r"^([1-9]\d*)_")


# 显式 PHPSESSID 键值对（Cookie 串、JSON、curl、URL 编码、.env）
_EXPLICIT_KV_RE = re.compile(
	r"""["']?\bPHPSESSID["']?\s*(?:=|%3[Dd]|:)\s*["']?([^\s;"'`,&\]()}\\<>]+)"""
)
# Chrome DevTools 表格复制 / Netscape cookies.txt 导出（Tab 分隔列）
_TSV_ROW_RE = re.compile(r"""(?m)(?:^|\t)PHPSESSID\t+([^\s\t;"'`,]+)""")
# 裸 Pixiv PHPSESSID 形态：<数字UID>_<16位以上字母数字>，排除前面紧跟 '=' 的其他 Cookie 值
_BARE_TOKEN_RE = re.compile(r"""(?<![A-Za-z0-9_=.-])(\d{4,}_[A-Za-z0-9]{16,})(?![A-Za-z0-9_.-])""")


def _clean_value(raw: str) -> str:
	value = raw.strip()
	# 若来自 URL 编码的 Cookie 串（PHPSESSID%3Dxxx%3B...），截掉编码分号之后的内容
	encoded_semi = re.search(r"%3[Bb]", value)
	if encoded_semi:
		value = value[:encoded_semi.start()]
	return value.strip()


def extract_phpsessids(
	text: str,
	*,
	strict: bool = False,
	dedup: bool = True,
) -> list[str]:
	"""按出现顺序从文本中提取 ``PHPSESSID`` 值列表。

	``strict=True`` 时只匹配显式 ``PHPSESSID`` 键；``strict=False`` 时额外匹配裸 ``<uid>_<token>``。
	"""
	if not text:
		return []

	hits: list[tuple[int, int, str]] = []
	occupied: list[tuple[int, int]] = []

	for pattern in (_EXPLICIT_KV_RE, _TSV_ROW_RE):
		for match in pattern.finditer(text):
			value = _clean_value(match.group(1))
			if not value:
				continue
			span = match.span(1)
			hits.append((match.start(), 0, value))
			occupied.append(span)

	if not strict:
		for match in _BARE_TOKEN_RE.finditer(text):
			start, end = match.span(1)
			if any(not (end <= s or start >= e) for s, e in occupied):
				continue
			hits.append((start, 1, match.group(1)))

	hits.sort(key=lambda item: (item[0], item[1]))

	results: list[str] = []
	seen: set[str] = set()
	for _, _, value in hits:
		if dedup and value in seen:
			continue
		seen.add(value)
		results.append(value)
	return results


def format_phpsessids(values: Sequence[str], fmt: str = "bare") -> str:
	"""按指定格式渲染提取结果，方便直接粘贴到 GitHub Secrets 或 ``.env``。"""
	if not values:
		return ""
	if fmt == "bare":
		return "\n".join(values)
	if fmt == "kv":
		return "\n".join(f"PHPSESSID={item}" for item in values)
	if fmt == "pipe":
		return " || ".join(values)
	if fmt == "env":
		if len(values) == 1:
			return f"PIXIV_COOKIE={values[0]}"
		joined = "\n".join(values)
		return f'PIXIV_COOKIE="{joined}"'
	raise ValueError(f"不支持的输出格式：{fmt}")



def _browser_candidates(kind: str) -> list[Path]:
	"""按平台返回指定浏览器（chrome / edge）的候选可执行文件路径。"""
	candidates: list[Path] = []
	if kind == "chrome":
		names = ("chrome", "chrome.exe", "google-chrome", "google-chrome-stable", "chromium")
		win_subdirs = (
			("Google", "Chrome", "Application", "chrome.exe"),
			("Chromium", "Application", "chrome.exe"),
		)
		mac_paths = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",)
		linux_paths = (
			"/usr/bin/google-chrome",
			"/usr/bin/google-chrome-stable",
			"/usr/bin/chromium",
			"/usr/bin/chromium-browser",
		)
		reg_name = "chrome.exe"
	elif kind == "edge":
		names = ("msedge", "msedge.exe", "microsoft-edge")
		win_subdirs = (("Microsoft", "Edge", "Application", "msedge.exe"),)
		mac_paths = ("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",)
		linux_paths = ("/usr/bin/microsoft-edge", "/usr/bin/microsoft-edge-stable")
		reg_name = "msedge.exe"
	else:
		return candidates

	for name in names:
		found = shutil.which(name)
		if found:
			candidates.append(Path(found))

	if sys.platform.startswith("win"):
		for env_key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
			base = os.environ.get(env_key)
			if not base:
				continue
			for parts in win_subdirs:
				candidates.append(Path(base, *parts))
		try:
			import winreg
		except ImportError:
			winreg = None  # type: ignore[assignment]
		if winreg is not None:
			for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
				subkey = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{reg_name}"
				try:
					with winreg.OpenKey(root, subkey) as key:
						value, _ = winreg.QueryValueEx(key, "")
						if value:
							candidates.append(Path(str(value)))
				except OSError:
					continue
	elif sys.platform == "darwin":
		candidates.extend(Path(p) for p in mac_paths)
	else:
		candidates.extend(Path(p) for p in linux_paths)
	return candidates


def find_browser(browser: str = "chrome") -> Path:
	"""查找本机可用的 Chrome 或 Edge 可执行文件。"""
	order = ("chrome", "edge") if browser == "auto" else (browser,)
	for kind in order:
		for path in _browser_candidates(kind):
			if path.is_file():
				return path
	if browser == "chrome":
		raise FileNotFoundError("未找到 Chrome 浏览器，请确认已安装 Chrome 或改用 --browser edge")
	if browser == "edge":
		raise FileNotFoundError("未找到 Edge 浏览器，请确认已安装 Edge 或改用 --browser chrome")
	raise FileNotFoundError("未找到可用的 Chrome 或 Edge 浏览器")



def extract_auth_phpsessid_from_cdp_cookies(cookies: Sequence[dict[str, Any]]) -> str | None:
	"""从 CDP ``Storage.getCookies`` / ``Network.getCookies`` 结果中筛选已登录的 Pixiv ``PHPSESSID``。"""
	for cookie in cookies:
		if cookie.get("name") != "PHPSESSID":
			continue
		domain = str(cookie.get("domain") or "").lstrip(".").lower()
		if domain != "pixiv.net" and not domain.endswith(".pixiv.net"):
			continue
		value = str(cookie.get("value") or "").strip()
		if _AUTH_PHPSESSID_RE.fullmatch(value):
			return value
	return None



def read_devtools_endpoint(user_data_dir: Path) -> tuple[int, str] | None:
	"""读取临时目录里的 ``DevToolsActivePort``，返回 ``(port, ws_path)``。"""
	port_file = user_data_dir / "DevToolsActivePort"
	if not port_file.is_file():
		return None
	try:
		lines = port_file.read_text(encoding="utf-8").splitlines()
	except OSError:
		return None
	if len(lines) < 2:
		return None
	port_text, ws_path = lines[0].strip(), lines[1].strip()
	if not port_text.isdigit() or not ws_path.startswith("/"):
		return None
	return int(port_text), ws_path


async def _cdp_call(
	ws: aiohttp.ClientWebSocketResponse,
	req_id: int,
	method: str,
	params: dict[str, Any] | None = None,
) -> dict[str, Any]:
	payload: dict[str, Any] = {"id": req_id, "method": method}
	if params:
		payload["params"] = params
	await ws.send_json(payload)
	while True:
		msg = await ws.receive_json(timeout=3.0)
		if msg.get("id") == req_id:
			return msg


async def _wait_for_login_cookie(
	proc: subprocess.Popen[bytes],
	user_data_dir: Path,
	*,
	timeout: float = 300.0,
	poll_interval: float = 0.5,
) -> str:
	deadline = time.monotonic() + max(1.0, timeout)
	endpoint: tuple[int, str] | None = None
	while time.monotonic() < deadline:
		if proc.poll() is not None:
			raise RuntimeError("浏览器已关闭，登录已取消")
		endpoint = read_devtools_endpoint(user_data_dir)
		if endpoint is not None:
			break
		await asyncio.sleep(0.1)

	if endpoint is None:
		raise TimeoutError("等待浏览器调试端口就绪超时")

	port, ws_path = endpoint
	ws_url = f"ws://127.0.0.1:{port}{ws_path}"
	req_id = 1
	async with aiohttp.ClientSession() as session:
		async with session.ws_connect(ws_url, heartbeat=15.0) as ws:
			while time.monotonic() < deadline:
				if proc.poll() is not None:
					raise RuntimeError("浏览器已关闭，登录已取消")
				try:
					resp = await _cdp_call(ws, req_id, "Storage.getCookies")
					req_id += 1
				except (aiohttp.ClientError, asyncio.TimeoutError, TypeError) as exc:
					if proc.poll() is not None:
						raise RuntimeError("浏览器已关闭，登录已取消") from exc
					await asyncio.sleep(poll_interval)
					continue

				cookies = resp.get("result", {}).get("cookies") or []
				token = extract_auth_phpsessid_from_cdp_cookies(cookies)
				if token:
					try:
						await _cdp_call(ws, req_id, "Browser.close")
					except (aiohttp.ClientError, asyncio.TimeoutError, TypeError, ValueError):
						pass
					return token
				await asyncio.sleep(poll_interval)

	raise TimeoutError(f"等待 Pixiv 登录超时（{timeout:.0f} 秒）")


def _stop_browser(proc: subprocess.Popen[bytes]) -> None:
	if proc.poll() is not None:
		return
	proc.terminate()
	try:
		proc.wait(timeout=3.0)
	except subprocess.TimeoutExpired:
		proc.kill()
		try:
			proc.wait(timeout=2.0)
		except subprocess.TimeoutExpired:
			pass



def login_and_capture(
	browser_path: Path,
	*,
	count: int = 1,
	timeout: float = 300.0,
	dedup: bool = True,
	login_url: str = PIXIV_LOGIN_URL,
) -> list[str]:
	"""依次弹出临时隔离浏览器窗口，人工登录 Pixiv 后自动捕获 ``PHPSESSID``。"""
	if count < 1:
		raise ValueError("count 必须大于等于 1")

	values: list[str] = []
	seen: set[str] = set()
	for index in range(1, count + 1):
		print(
			f"[{index}/{count}] 正在打开 {browser_path.name}，请在窗口中完成 Pixiv 登录……",
			file=sys.stderr,
		)
		with tempfile.TemporaryDirectory(prefix="pixiv-login-", ignore_cleanup_errors=True) as tmp_dir:
			profile_dir = Path(tmp_dir)
			cmd = [
				str(browser_path),
				"--remote-debugging-port=0",
				f"--user-data-dir={profile_dir}",
				"--no-first-run",
				"--no-default-browser-check",
				"--disable-default-apps",
				"--new-window",
				login_url,
			]
			proc = subprocess.Popen(
				cmd,
				stdout=subprocess.DEVNULL,
				stderr=subprocess.DEVNULL,
			)
			try:
				token = asyncio.run(
					_wait_for_login_cookie(proc, profile_dir, timeout=timeout)
				)
			except (RuntimeError, TimeoutError) as exc:
				if values:
					print(
						f"[{index}/{count}] {exc}；将保留前面已捕获的 {len(values)} 个账号。",
						file=sys.stderr,
					)
					break
				raise
			finally:
				_stop_browser(proc)

		uid_match = _UID_PREFIX_RE.match(token)
		uid_hint = f"uid={uid_match.group(1)}" if uid_match else "account"
		if dedup and token in seen:
			print(f"[{index}/{count}] 捕获到重复账号（{uid_hint}），已跳过", file=sys.stderr)
			continue
		seen.add(token)
		values.append(token)
		print(f"[{index}/{count}] 已捕获 {uid_hint} 的 PHPSESSID", file=sys.stderr)

	return values


def _read_inputs(files: Sequence[str], text: str | None) -> str:
	chunks: list[str] = []
	if text is not None:
		chunks.append(text)
	for item in files:
		if item == "-":
			chunks.append(sys.stdin.read())
		else:
			chunks.append(Path(item).read_text(encoding="utf-8"))
	if not files and text is None:
		if sys.stdin.isatty():
			print(
				"请粘贴包含 Cookie / PHPSESSID 的文本（Windows 按 Ctrl+Z 回车，Linux/macOS 按 Ctrl+D 结束）：",
				file=sys.stderr,
			)
		chunks.append(sys.stdin.read())
	return "\n".join(chunks)



def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		description="从 Cookie 串、JSON、curl 或导出文本中提取 Pixiv PHPSESSID。",
	)
	parser.add_argument(
		"files",
		nargs="*",
		help="要读取的文本文件路径（传 '-' 或留空则从标准输入读取）",
	)
	parser.add_argument(
		"-t",
		"--text",
		help="直接传入待匹配的文本内容",
	)
	parser.add_argument(
		"-s",
		"--strict",
		action="store_true",
		help="严格模式：只匹配显式 PHPSESSID 键，不匹配裸 <uid>_<token>",
	)
	parser.add_argument(
		"--no-dedup",
		action="store_true",
		help="保留重复的 PHPSESSID（默认按出现顺序去重）",
	)
	parser.add_argument(
		"-f",
		"--format",
		choices=("bare", "kv", "env", "pipe"),
		default="bare",
		help='输出格式：bare=每行裸值（默认，可直接贴 GitHub Secret）；kv=PHPSESSID=值；env=PIXIV_COOKIE="..."；pipe=|| 拼接',
	)
	parser.add_argument(
		"-o",
		"--output",
		help="将输出结果写入指定文件（UTF-8）",
	)
	parser.add_argument(
		"-l",
		"--login",
		action="store_true",
		help="半自动登录模式：启动本地隔离浏览器手动登录，自动捕获 PHPSESSID",
	)
	parser.add_argument(
		"-c",
		"--count",
		type=int,
		default=1,
		help="登录模式下依次捕获的账号数量（默认 1，如 --count 5）",
	)
	parser.add_argument(
		"-b",
		"--browser",
		choices=("chrome", "edge", "auto"),
		default="chrome",
		help="登录模式使用的浏览器：chrome（默认）、edge 或 auto",
	)
	parser.add_argument(
		"--timeout",
		type=float,
		default=300.0,
		help="登录模式下等待单个账号完成登录的超时秒数（默认 300）",
	)
	return parser


def main(argv: Sequence[str] | None = None) -> int:
	parser = build_parser()
	args = parser.parse_args(argv)

	if args.login:
		if args.files or args.text is not None:
			print("--login 模式不能与文件或 --text 参数同时使用。", file=sys.stderr)
			return 2
		if args.count < 1:
			print("--count 必须大于等于 1。", file=sys.stderr)
			return 2
		try:
			browser_path = find_browser(args.browser)
			values = login_and_capture(
				browser_path,
				count=args.count,
				timeout=args.timeout,
				dedup=not args.no_dedup,
			)
		except (FileNotFoundError, RuntimeError, TimeoutError, ValueError, OSError) as exc:
			print(f"登录获取失败：{exc}", file=sys.stderr)
			return 1
	else:
		try:
			content = _read_inputs(args.files, args.text)
		except OSError as exc:
			print(f"读取输入失败：{exc}", file=sys.stderr)
			return 2
		values = extract_phpsessids(content, strict=args.strict, dedup=not args.no_dedup)

	if not values:
		print("未提取到任何有效的 PHPSESSID。", file=sys.stderr)
		return 1

	rendered = format_phpsessids(values, args.format)
	if args.output:
		Path(args.output).write_text(rendered + "\n", encoding="utf-8")
		print(f"已提取 {len(values)} 个 PHPSESSID 并写入 {args.output}", file=sys.stderr)
	else:
		print(rendered)
		print(f"# 共提取 {len(values)} 个 PHPSESSID", file=sys.stderr)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
