r"""从文本中提取 Pixiv ``PHPSESSID`` 的小工具。

支持完整 Cookie 串、JSON、curl、URL 编码、Chrome DevTools 表格 / Netscape ``cookies.txt``
以及裸 ``<uid>_<token>``；结果可以按裸值 / ``kv`` / ``.env`` / ``||`` 格式输出，
方便直接贴进 GitHub Secret 或 ``.env``。

用法示例（在项目根目录）:
# 1. 交互式粘贴 Cookie / PHPSESSID（Windows 按 Ctrl+Z 回车，Linux/macOS 按 Ctrl+D 结束）
.venv\Scripts\python.exe script/extract_phpsessid.py

# 2. 从文件读取并输出 .env 行
.venv\Scripts\python.exe script/extract_phpsessid.py cookies.txt --format env -o pixiv.env

# 3. 直接传文本
.venv\Scripts\python.exe script/extract_phpsessid.py -t "PHPSESSID=123456_abcdefghijklmnop"
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Sequence


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
	return parser


def main(argv: Sequence[str] | None = None) -> int:
	parser = build_parser()
	args = parser.parse_args(argv)

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
