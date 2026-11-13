"""Linpx 源：链接解析 / 数据转换单测；真实 API 用例默认跳过。

运行（在项目根目录）:
	.venv\\Scripts\\python.exe -m pytest test/test_linpx.py -q

需要真实网络时先设环境变量：
	$env:LINPX_LIVE = "1"
"""

from __future__ import annotations

import asyncio
import os

import pytest

from sources import fetch, resolve_source
from sources.linpx import LinpxSource
from infra.http import HttpError
from sources.linpx import client
from sources.linpx.client import get_novel
from sources.linpx.config import NOVEL_PATTERN
from sources.linpx.errors import LinpxNetworkError, LinpxNotFoundError
from sources.linpx.parse import json_to_novel
from sources.utils import get_id


SAMPLE_ID = "18012577"
SAMPLE_LINPX = f"https://linpx.ink/pixiv/novel/{SAMPLE_ID}"
SAMPLE_PN = f"https://linpx.ink/pn/{SAMPLE_ID}"

LIVE = os.getenv("LINPX_LIVE") == "1"
live = pytest.mark.skipif(not LIVE, reason="需要真实 Linpx API：LINPX_LIVE=1")


def run(coro):
	return asyncio.run(coro)


def test_extract_linpx_url() -> None:
	assert get_id(SAMPLE_LINPX, NOVEL_PATTERN) == SAMPLE_ID


def test_extract_pn_url() -> None:
	assert get_id(SAMPLE_PN, NOVEL_PATTERN) == SAMPLE_ID


def test_extract_in_sentence() -> None:
	assert get_id(f"请下载这篇 {SAMPLE_LINPX} 谢谢", NOVEL_PATTERN) == SAMPLE_ID


def test_extract_invalid() -> None:
	assert get_id("hello world", NOVEL_PATTERN) is None
	assert get_id("", NOVEL_PATTERN) is None


def test_can_handle() -> None:
	src = LinpxSource()
	assert src.can_handle(SAMPLE_LINPX) is True
	assert src.can_handle(SAMPLE_PN) is True
	assert src.can_handle(f"https://linpx.ink/pixiv/user/{SAMPLE_ID}") is True
	assert src.can_handle(SAMPLE_ID) is False  # 纯数字 ID 不是链接，先归一化再进来
	assert src.can_handle("不是链接") is False


def test_resolve_source() -> None:
	assert isinstance(resolve_source(SAMPLE_LINPX), LinpxSource)
	assert resolve_source("https://example.com/novel/1") is None


def test_json_to_novel_minimal() -> None:
	data = {
		"id": 123,
		"title": "测试标题",
		"userId": 456,
		"userName": "测试作者",
		"content": "正文内容",
		"tags": ["兽人", "原创"],
		"desc": "简介",
		"series": {"id": 789, "title": "系列名"},
	}
	novel = json_to_novel(data)
	assert str(novel.id) == "123"
	assert novel.title == "测试标题"
	assert str(novel.author_id) == "456"
	assert novel.author_name == "测试作者"
	assert novel.content == "正文内容"
	assert novel.tags == ["兽人", "原创"]
	assert str(novel.series_id) == "789"
	assert novel.series_title == "系列名"
	assert novel.source == "Linpx"


def test_json_to_novel_error() -> None:
	with pytest.raises(LinpxNotFoundError):
		json_to_novel({"error": True})
	with pytest.raises(LinpxNotFoundError):
		json_to_novel({})



def _failing_get_json(status):
	async def fake(url, headers=None):
		raise HttpError(url, status)
	return fake


def test_missing_work_reports_not_found(monkeypatch) -> None:
	monkeypatch.setattr(client, "get_json", _failing_get_json(404))
	with pytest.raises(LinpxNotFoundError):
		run(LinpxSource().fetch_novel(SAMPLE_LINPX))


@pytest.mark.parametrize("status", [None, 500])
def test_transient_failure_reports_network_error(monkeypatch, status) -> None:
	monkeypatch.setattr(client, "get_json", _failing_get_json(status))
	with pytest.raises(LinpxNetworkError):
		run(LinpxSource().fetch_novel(SAMPLE_LINPX))

@live
def test_client_get_novel() -> None:
	data = run(get_novel(SAMPLE_ID))
	assert data.get("error") in (None, False)
	assert str(data.get("id")) == SAMPLE_ID
	assert data.get("title")
	assert data.get("content")
	assert data.get("userId")
	assert data.get("userName")


@live
def test_fetch_via_source() -> None:
	novel = run(LinpxSource().fetch_novel(SAMPLE_LINPX))
	assert str(novel.id) == SAMPLE_ID
	assert novel.title
	assert novel.author_id
	assert novel.author_name
	assert len(novel.content) > 0
	assert novel.source == "Linpx"


@live
def test_fetch_via_registry() -> None:
	assert resolve_source(SAMPLE_PN) is not None
	novel = run(fetch(SAMPLE_PN))
	assert str(novel.id) == SAMPLE_ID
	assert novel.content


if __name__ == "__main__":
	print("请使用 pytest 运行：python -m pytest test/test_linpx.py -q")
