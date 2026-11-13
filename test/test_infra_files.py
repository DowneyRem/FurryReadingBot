"""infra/files.py：报错约定。

- 只用内置异常：写失败**原样**抛 `OSError`，`errno` / `filename` / traceback 都保留；
- 日志统一「<动作>失败：<完整路径>」+ `exc_info`，不额外包装异常；
- 读失败沿用旧契约：返回 `""` / `None`。

运行（在项目根目录）:
	python -m pytest test/test_infra_files.py -q
"""

from __future__ import annotations

import asyncio
import json

import pytest

from infra.files import (
	read_json,
	read_txt,
	remove_file,
	save_json,
	save_text,
	save_text_sync,
)


def run(coro):
	return asyncio.run(coro)


def blocked_path(tmp_path):
	"""返回一个「父目录其实是普通文件」的路径，写它必然失败。"""
	blocker = tmp_path / "blocker"
	blocker.write_text("x", encoding="utf-8")
	return blocker / "a.txt"


def test_save_text_writes_utf8(tmp_path) -> None:
	path = tmp_path / "sub" / "a.txt"

	assert run(save_text(path, "你好")) == path
	assert path.read_text(encoding="utf-8") == "你好"
	assert run(read_txt(path)) == "你好"


def test_save_text_raises_builtin_oserror(tmp_path) -> None:
	path = blocked_path(tmp_path)

	with pytest.raises(OSError) as excinfo:
		save_text_sync(path, "data")

	# 抛的是标准 OSError：没有被包装成新类型，errno / filename 都还在
	assert type(excinfo.value) in (FileExistsError, NotADirectoryError)
	assert excinfo.value.errno is not None
	assert excinfo.value.filename is not None
	assert not path.exists()


def test_save_text_raises_on_failure(tmp_path) -> None:
	with pytest.raises(OSError):
		run(save_text(blocked_path(tmp_path), "data"))


def test_save_json_roundtrip_and_failure(tmp_path) -> None:
	path = tmp_path / "sub" / "a.json"

	run(save_json(path, {"k": "值"}))
	assert json.loads(path.read_text(encoding="utf-8")) == {"k": "值"}
	assert run(read_json(path)) == {"k": "值"}

	with pytest.raises(OSError):
		run(save_json(blocked_path(tmp_path), {"k": 1}))


def test_read_failures_return_empty_values(tmp_path) -> None:
	missing = tmp_path / "nope.txt"
	assert run(read_txt(missing)) == ""
	assert run(read_json(missing)) is None

	broken = tmp_path / "broken.json"
	broken.write_text("{not json", encoding="utf-8")
	assert run(read_json(broken)) is None


def test_remove_file_is_best_effort(tmp_path) -> None:
	path = tmp_path / "a.txt"
	path.write_text("x", encoding="utf-8")

	run(remove_file(path))
	assert not path.exists()
	run(remove_file(path))  # 已不存在也不抛
