r"""从文本提取或通过本地浏览器登录获取 Pixiv ``PHPSESSID`` 的工具。

支持两种模式：
  1. 文本提取（默认）：支持完整 Cookie 串、JSON、curl、URL 编码、DevTools 表格 / ``cookies.txt``、裸值；
  2. 半自动登录（``--login``）：用独立的固定配置目录（默认 ``.pixiv-profile``）开无痕窗口，
     从 ``https://www.pixiv.net/`` 首页起步，你自行点「登录」并过验证码，脚本捕获 ``PHPSESSID`` 后关窗。

结果统一写入当前目录的 ``pixiv.env``（``PIXIV_COOKIE="值"``，多个账号换行分隔）：
文件已存在时先读取其中已有的账号，与本次结果合并去重后整体写回，可反复运行逐步累积。

说明：
  * 登录用的是**脚本自己的配置目录**，不是日常浏览器的 profile，所以不需要先退出 Chrome；
  * ``.pixiv-profile`` 会保留 ``device_token``，第一次手动过验证码后，后续登录一般不再弹；
  * 默认无痕窗口，无法从该配置目录继承登录态；想直接复用配置里已有的登录态可加 ``--no-incognito``。

用法示例（在项目根目录）:
# 1. 从日常 Chrome 的 Cookie 里提取（F12 → Application → Cookies 里复制 PHPSESSID）
.venv\Scripts\python.exe script/extract_phpsessid.py -t "PHPSESSID=123456_abcdefghijklmnop"
.venv\Scripts\python.exe script/extract_phpsessid.py cookies.txt

# 2. 用 Chrome 依次登录 5 个账号，结果合并进 pixiv.env
.venv\Scripts\python.exe script/extract_phpsessid.py --login --count 5

# 3. 换一个固定配置目录 / 单账号超时调到 10 分钟
.venv\Scripts\python.exe script/extract_phpsessid.py --login --profile-dir D:\pixiv-profile --timeout 600

# 4. 直接用常规窗口复用配置里已有的 Pixiv 登录态
.venv\Scripts\python.exe script/extract_phpsessid.py --login --no-incognito
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterator, Sequence

import aiohttp


# 结果固定写到当前目录的 pixiv.env（脚本专用文件，不放其它变量）
OUTPUT_FILE = Path("pixiv.env")
# 登录模式使用的独立配置目录（相对当前目录），会保留 device_token
DEFAULT_PROFILE_DIR = Path(".pixiv-profile")
# 登录模式从这里起步，由用户自己点「登录」，避免深链直达登录页触发风控
PIXIV_HOME_URL = "https://www.pixiv.net/"
# 已登录的 Pixiv PHPSESSID 形如 <正整数UID>_<16位以上字母数字>；未登录网页种下的是无下划线的 32 位游客串
_AUTH_PHPSESSID_RE = re.compile(r"^[1-9]\d*_[A-Za-z0-9]{16,}$")
_UID_PREFIX_RE = re.compile(r"^([1-9]\d*)_")


class BrowserStartupError(RuntimeError):
	"""浏览器没能在预期内提供调试端口（多为配置目录已被其他实例占用）。"""


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


def extract_phpsessids(text: str, *, strict: bool = False) -> list[str]:
	"""按出现顺序从文本中提取去重后的 ``PHPSESSID`` 值列表。

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
		if value in seen:
			continue
		seen.add(value)
		results.append(value)
	return results


def format_phpsessids(values: Sequence[str], fmt: str = "env") -> str:
	"""按指定格式渲染结果，默认 ``PIXIV_COOKIE="..."``（``.env`` 可直接使用）。"""
	if not values:
		return ""
	if fmt == "bare":
		return "\n".join(values)
	if fmt == "pipe":
		return " || ".join(values)
	if fmt == "env":
		joined = "\n".join(values)
		return f'PIXIV_COOKIE="{joined}"'
	raise ValueError(f"不支持的输出格式：{fmt}")


def read_existing_phpsessids(path: Path) -> list[str]:
	"""读取输出文件里已经存在的 ``PHPSESSID``（用于追加合并，而不是覆盖）。"""
	if not path.is_file():
		return []
	try:
		text = path.read_text(encoding="utf-8-sig")
	except OSError:
		return []
	return extract_phpsessids(text)


def merge_phpsessids(existing: Sequence[str], new: Sequence[str]) -> list[str]:
	"""把文件里已有的值与本次抓到的值合并：保持顺序、按值去重，已有在前。"""
	merged: list[str] = []
	seen: set[str] = set()
	for value in (*existing, *new):
		if value in seen:
			continue
		seen.add(value)
		merged.append(value)
	return merged



def _browser_candidates(kind: str) -> list[Path]:
	"""返回 Windows 上指定浏览器（chrome / edge）的候选可执行文件路径。"""
	if kind == "chrome":
		names = ("chrome", "chrome.exe")
		win_subdirs = (
			("Google", "Chrome", "Application", "chrome.exe"),
			("Chromium", "Application", "chrome.exe"),
		)
	elif kind == "edge":
		names = ("msedge", "msedge.exe")
		win_subdirs = (("Microsoft", "Edge", "Application", "msedge.exe"),)
	else:
		return []

	candidates = [Path(found) for name in names if (found := shutil.which(name))]
	for env_key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
		base = os.environ.get(env_key)
		if not base:
			continue
		candidates.extend(Path(base, *parts) for parts in win_subdirs)
	return candidates


def find_browser(browser: str = "auto") -> Path:
	"""查找本机可用的 Chrome（默认）或 Edge，都没有则报错。"""
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


def _build_login_command(
	browser_path: Path,
	profile_dir: Path,
	*,
	port: int,
	start_url: str = PIXIV_HOME_URL,
	incognito: bool = True,
) -> list[str]:
	"""拼装登录模式使用的浏览器启动参数（首页起步 + 可选无痕窗口）。"""
	cmd = [
		str(browser_path),
		f"--remote-debugging-port={port}",
		f"--user-data-dir={profile_dir}",
		"--no-first-run",
		"--no-default-browser-check",
		"--disable-default-apps",
	]
	if incognito:
		cmd.append("--incognito")
	cmd.append(start_url)
	return cmd


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


def _pick_free_port() -> int:
	"""挑一个本地空闲端口给 ``--remote-debugging-port`` 用。

	注意：浏览器使用默认配置目录时不会写 ``DevToolsActivePort``，因此不能靠它发现端口。
	"""
	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
		sock.bind(("127.0.0.1", 0))
		return int(sock.getsockname()[1])


async def _resolve_ws_url(session: aiohttp.ClientSession, port: int) -> str | None:
	"""轮询 ``/json/version`` 拿到浏览器级 CDP WebSocket 地址。"""
	url = f"http://127.0.0.1:{port}/json/version"
	try:
		async with session.get(url) as resp:
			data = await resp.json(content_type=None)
	except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError):
		return None
	if not isinstance(data, dict):
		return None
	ws_url = data.get("webSocketDebuggerUrl")
	return str(ws_url) if ws_url else None


# 无痕窗口与常规窗口的 Cookie 分属不同的存储上下文，按 URL 读取页面可见的全部 Cookie（含 HttpOnly）
_PIXIV_COOKIE_URLS = ("https://www.pixiv.net/", "https://accounts.pixiv.net/")


async def _cdp_call(
	ws: aiohttp.ClientWebSocketResponse,
	req_id: int,
	method: str,
	params: dict[str, Any] | None = None,
	*,
	session_id: str | None = None,
) -> dict[str, Any]:
	payload: dict[str, Any] = {"id": req_id, "method": method}
	if params:
		payload["params"] = params
	if session_id:
		payload["sessionId"] = session_id
	await ws.send_json(payload)
	while True:
		msg = await ws.receive_json(timeout=3.0)
		if msg.get("id") == req_id and msg.get("sessionId", session_id) == session_id:
			return msg


async def _attach_pixiv_page(
	ws: aiohttp.ClientWebSocketResponse,
	ids: Iterator[int],
) -> str | None:
	"""找到 Pixiv 页面目标并以 flatten 方式附加，返回可复用的 ``sessionId``。"""
	resp = await _cdp_call(ws, next(ids), "Target.getTargets")
	for info in (resp.get("result") or {}).get("targetInfos") or []:
		if info.get("type") != "page":
			continue
		if "pixiv" not in str(info.get("url") or "").lower():
			continue
		target_id = info.get("targetId")
		if not target_id:
			continue
		attached = await _cdp_call(
			ws,
			next(ids),
			"Target.attachToTarget",
			{"targetId": target_id, "flatten": True},
		)
		session_id = (attached.get("result") or {}).get("sessionId")
		if not session_id:
			continue
		try:
			await _cdp_call(ws, next(ids), "Network.enable", session_id=session_id)
		except (aiohttp.ClientError, asyncio.TimeoutError):
			pass
		return session_id
	return None


async def _read_pixiv_cookies(
	ws: aiohttp.ClientWebSocketResponse,
	ids: Iterator[int],
	session_id: str | None,
	*,
	allow_browser_wide: bool,
) -> tuple[list[dict[str, Any]], str | None]:
	"""读取当前窗口的 Pixiv Cookie，返回 ``(cookies, 可复用的 sessionId)``。

	``allow_browser_wide=False``（无痕模式）时只用页面上下文读取，
	避免误读默认配置里已有的登录态。
	"""
	if session_id is None:
		session_id = await _attach_pixiv_page(ws, ids)
	if session_id is not None:
		resp = await _cdp_call(
			ws,
			next(ids),
			"Network.getCookies",
			{"urls": list(_PIXIV_COOKIE_URLS)},
			session_id=session_id,
		)
		if not resp.get("error"):
			return (resp.get("result") or {}).get("cookies") or [], session_id
		# 页面被关闭 / 会话失效：下一轮重新附加
		session_id = None
	if not allow_browser_wide:
		return [], session_id
	resp = await _cdp_call(ws, next(ids), "Storage.getCookies")
	return (resp.get("result") or {}).get("cookies") or [], session_id


async def _wait_for_login_cookie(
	proc: subprocess.Popen[bytes],
	port: int,
	*,
	timeout: float = 300.0,
	poll_interval: float = 0.5,
	allow_browser_wide: bool = True,
) -> str:
	deadline = time.monotonic() + max(1.0, timeout)
	ids = itertools.count(1)
	session_id: str | None = None
	async with aiohttp.ClientSession() as session:
		ws_url: str | None = None
		while time.monotonic() < deadline:
			if proc.poll() is not None:
				raise BrowserStartupError("浏览器已关闭，登录已取消")
			ws_url = await _resolve_ws_url(session, port)
			if ws_url:
				break
			await asyncio.sleep(0.1)

		if ws_url is None:
			raise BrowserStartupError("等待浏览器调试端口就绪超时")

		async with session.ws_connect(ws_url, heartbeat=15.0) as ws:
			while time.monotonic() < deadline:
				if proc.poll() is not None:
					raise BrowserStartupError("浏览器已关闭，登录已取消")
				try:
					cookies, session_id = await _read_pixiv_cookies(
						ws,
						ids,
						session_id,
						allow_browser_wide=allow_browser_wide,
					)
				except (aiohttp.ClientError, asyncio.TimeoutError, TypeError) as exc:
					if proc.poll() is not None:
						raise BrowserStartupError("浏览器已关闭，登录已取消") from exc
					session_id = None
					await asyncio.sleep(poll_interval)
					continue

				token = extract_auth_phpsessid_from_cdp_cookies(cookies)
				if token:
					try:
						await _cdp_call(ws, next(ids), "Browser.close")
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


def _capture_once(
	browser_path: Path,
	profile_dir: Path,
	*,
	start_url: str,
	incognito: bool,
	timeout: float,
) -> str:
	"""启动一次浏览器、等待人工登录完成并返回捕获到的 ``PHPSESSID``。"""
	port = _pick_free_port()
	proc = subprocess.Popen(
		_build_login_command(
			browser_path,
			profile_dir,
			port=port,
			start_url=start_url,
			incognito=incognito,
		),
		stdout=subprocess.DEVNULL,
		stderr=subprocess.DEVNULL,
	)
	try:
		return asyncio.run(
			_wait_for_login_cookie(
				proc,
				port,
				timeout=timeout,
				allow_browser_wide=not incognito,
			)
		)
	finally:
		_stop_browser(proc)


def login_and_capture(
	browser_path: Path,
	*,
	count: int = 1,
	timeout: float = 300.0,
	start_url: str = PIXIV_HOME_URL,
	profile_dir: Path = DEFAULT_PROFILE_DIR,
	incognito: bool = True,
) -> list[str]:
	"""依次打开 Pixiv 首页，人工点「登录」后自动捕获 ``PHPSESSID``。

	配置目录默认是 ``.pixiv-profile``（会保留 ``device_token``，后续登录少弹验证码）；
	``incognito=False`` 改用常规窗口，可直接沿用该配置里已有的登录态。
	"""
	if count < 1:
		raise ValueError("count 必须大于等于 1")

	# Chrome 对相对路径的 --user-data-dir 处理异常（不开调试端口），这里统一转成绝对路径
	profile = Path(profile_dir).expanduser().resolve()
	profile.mkdir(parents=True, exist_ok=True)
	mode = "无痕窗口" if incognito else "常规窗口"

	values: list[str] = []
	seen: set[str] = set()
	for index in range(1, count + 1):
		print(
			f"[{index}/{count}] 正在打开 {browser_path.name}（{mode}，配置目录 {profile}），"
			"请在窗口里自行点击「登录」完成 Pixiv 登录……",
			file=sys.stderr,
		)
		try:
			token = _capture_once(
				browser_path,
				profile,
				start_url=start_url,
				incognito=incognito,
				timeout=timeout,
			)
		except (RuntimeError, TimeoutError) as exc:
			if values:
				print(
					f"[{index}/{count}] {exc}；将保留前面已捕获的 {len(values)} 个账号。",
					file=sys.stderr,
				)
				break
			if isinstance(exc, BrowserStartupError):
				raise RuntimeError(
					f"{exc}（请确认配置目录 {profile} 没有被其他浏览器实例占用，"
					"或换一个 --profile-dir 重试）"
				) from exc
			raise

		uid_match = _UID_PREFIX_RE.match(token)
		uid_hint = f"uid={uid_match.group(1)}" if uid_match else "account"
		if token in seen:
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
			# 兼容 ANSI / GBK 等非 UTF-8 文本：替换非法字节而不是崩栈
			chunks.append(Path(item).read_text(encoding="utf-8", errors="replace"))
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
		"-f",
		"--format",
		choices=("bare", "env", "pipe"),
		default="env",
		help='输出格式：env=PIXIV_COOKIE="..."（默认，写入 pixiv.env）；bare=每行裸值；pipe=|| 拼接',
	)
	parser.add_argument(
		"-l",
		"--login",
		action="store_true",
		help="半自动登录模式：用独立配置目录开无痕窗口打开 Pixiv 首页，自己登录后自动捕获 PHPSESSID",
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
		default="auto",
		help="登录模式使用的浏览器：auto（默认，先 Chrome 再 Edge）、chrome 或 edge",
	)
	parser.add_argument(
		"--timeout",
		type=float,
		default=300.0,
		help="登录模式下等待单个账号完成登录的超时秒数（默认 300）",
	)
	parser.add_argument(
		"--profile-dir",
		help="登录模式使用的浏览器配置目录（默认 .pixiv-profile，会保留 device_token）",
	)
	parser.add_argument(
		"--no-incognito",
		action="store_true",
		help="登录模式改用常规窗口（默认无痕）：会直接沿用配置里已有的 Pixiv 登录态",
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
				profile_dir=Path(args.profile_dir) if args.profile_dir else DEFAULT_PROFILE_DIR,
				incognito=not args.no_incognito,
			)
		except (FileNotFoundError, RuntimeError, TimeoutError, ValueError, OSError) as exc:
			print(f"登录获取失败：{exc}", file=sys.stderr)
			return 1
	else:
		try:
			content = _read_inputs(args.files, args.text)
		except (OSError, UnicodeError) as exc:
			print(f"读取输入失败：{exc}", file=sys.stderr)
			return 2
		values = extract_phpsessids(content, strict=args.strict)

	if not values:
		print("未提取到任何有效的 PHPSESSID。", file=sys.stderr)
		return 1

	# 固定写入 pixiv.env：先读取已有账号，合并去重后整体写回
	existing = read_existing_phpsessids(OUTPUT_FILE)
	merged = merge_phpsessids(existing, values)
	rendered = format_phpsessids(merged, args.format)
	try:
		OUTPUT_FILE.write_text(rendered + "\n", encoding="utf-8", newline="\n")
	except OSError as exc:
		print(f"写入 {OUTPUT_FILE} 失败：{exc}", file=sys.stderr)
		return 2

	if existing:
		print(
			f"已读取 {OUTPUT_FILE} 中已有的 {len(existing)} 个 PHPSESSID，"
			f"新增 {len(merged) - len(existing)} 个，共 {len(merged)} 个并写回 {OUTPUT_FILE}",
			file=sys.stderr,
		)
	else:
		print(f"已提取 {len(merged)} 个 PHPSESSID 并写入 {OUTPUT_FILE}", file=sys.stderr)
	print(rendered)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
