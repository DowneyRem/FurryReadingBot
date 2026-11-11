"""缩进守门测试：全仓 .py 必须用 Tab 缩进。

约定见仓库根目录 `.editorconfig` 与 `docs/04-如何改代码.md` 第 5.4 节：
本项目所有 Python 代码用 Tab 缩进（Tab = 4 列），不允许用空格缩进代码块。

实现方式：走 `tokenize`，只检查真正产生 token 的代码行；
docstring / 多行字符串内部的排版缩进（不产生 token）不受限制。

运行：.venv\\Scripts\\python.exe -m pytest test/test_style.py -q
"""

from __future__ import annotations

import io
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 不参与检查的目录（虚拟环境、IDE、缓存）
SKIP_DIRS = {".venv", ".idea", "__pycache__", ".pytest_cache", ".git"}

# 这些 token 不落在真正的代码行首，跳过
IGNORED_TOKENS = {
	tokenize.NEWLINE,
	tokenize.NL,
	tokenize.INDENT,
	tokenize.DEDENT,
	tokenize.ENDMARKER,
	tokenize.ENCODING,
}


def iter_python_files() -> list[Path]:
	"""返回仓库内所有需要检查的 .py 文件。"""
	files: list[Path] = []
	for path in sorted(ROOT.rglob("*.py")):
		if SKIP_DIRS & set(path.relative_to(ROOT).parts):
			continue
		files.append(path)
	return files


def space_indented_lines(path: Path) -> list[int]:
	"""返回该文件中「行首缩进含空格」的代码行号（1 基）。"""
	lines = path.read_text(encoding="utf-8").splitlines()
	try:
		tokens = tokenize.generate_tokens(io.StringIO("\n".join(lines)).readline)
		rows: list[int] = []
		for token in tokens:
			if token.type in IGNORED_TOKENS:
				continue
			row, col = token.start
			prefix = lines[row - 1][:col]
			if prefix.strip():
				continue  # 行内 token，不是行首缩进
			if " " in prefix:
				rows.append(row)
	except (tokenize.TokenError, IndentationError) as exc:  # pragma: no cover
		raise AssertionError(f"{path} 无法解析，请先修语法错误：{exc}") from exc
	return sorted(set(rows))


def test_python_files_use_tabs() -> None:
	"""任何 .py 出现空格缩进就算失败，并打印文件与行号。"""
	offenders: dict[str, list[int]] = {}
	for path in iter_python_files():
		rows = space_indented_lines(path)
		if rows:
			offenders[str(path.relative_to(ROOT))] = rows
	assert offenders == {}, (
		"以下文件用空格缩进代码，请改成 Tab（Tab = 4 列，见 .editorconfig）：\n"
		+ "\n".join(f"  {name}: 第 {rows} 行" for name, rows in offenders.items())
	)


if __name__ == "__main__":
	for file in iter_python_files():
		bad = space_indented_lines(file)
		print(f"{file.relative_to(ROOT)}: {'OK' if not bad else bad}")
