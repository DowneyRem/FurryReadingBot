"""Linpx 单篇：解析 + 真实 API 拉取。

运行（在项目根目录）:
	PYTHONPATH=. python test/test_linpx.py
或:
	PYTHONPATH=. python -m pytest test/test_linpx.py -v
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
	sys.path.insert(0, str(ROOT))

from sources import fetch_novel, resolve_source
from sources.linpx import LinpxSource, parse
from sources.linpx.client import get_novel


SAMPLE_ID = "18012577"
SAMPLE_LINPX = f"https://linpx.ink/pixiv/novel/{SAMPLE_ID}"
SAMPLE_PN = f"https://linpx.ink/pn/{SAMPLE_ID}"
SAMPLE_PIXIV = f"https://www.pixiv.net/novel/show.php?id={SAMPLE_ID}"


class TestParse:
	def test_extract_linpx_url(self):
		assert parse.extract_novel_id(SAMPLE_LINPX) == SAMPLE_ID

	def test_extract_pn_url(self):
		assert parse.extract_novel_id(SAMPLE_PN) == SAMPLE_ID

	def test_extract_pixiv_url(self):
		assert parse.extract_novel_id(SAMPLE_PIXIV) == SAMPLE_ID

	def test_extract_plain_id(self):
		assert parse.extract_novel_id(SAMPLE_ID) == SAMPLE_ID

	def test_extract_in_sentence(self):
		text = f"请下载这篇 {SAMPLE_LINPX} 谢谢"
		assert parse.extract_novel_id(text) == SAMPLE_ID

	def test_extract_invalid(self):
		assert parse.extract_novel_id("hello world") is None
		assert parse.extract_novel_id("") is None

	def test_can_handle(self):
		src = LinpxSource()
		assert src.can_handle(SAMPLE_LINPX) is True
		assert src.can_handle(SAMPLE_PN) is True
		assert src.can_handle(SAMPLE_PIXIV) is True
		assert src.can_handle(SAMPLE_ID) is True
		assert src.can_handle("不是链接") is False

	def test_json_to_novel_minimal(self):
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
		novel = parse.json_to_novel(data)
		assert novel.id == "123"
		assert novel.title == "测试标题"
		assert novel.author_id == "456"
		assert novel.author_name == "测试作者"
		assert novel.content == "正文内容"
		assert novel.tags == ["兽人", "原创"]
		assert novel.series_id == "789"
		assert novel.series_title == "系列名"
		assert novel.source == "linpx"

	def test_json_to_novel_error(self):
		with pytest.raises(ValueError):
			parse.json_to_novel({"error": True})
		with pytest.raises(ValueError):
			parse.json_to_novel({})


class TestLinpxLive:
	@pytest.mark.asyncio
	async def test_client_get_novel(self):
		data = await get_novel(SAMPLE_ID)
		assert data.get("error") in (None, False)
		assert str(data.get("id")) == SAMPLE_ID
		assert data.get("title")
		assert data.get("content")
		assert data.get("userId")
		assert data.get("userName")

	@pytest.mark.asyncio
	async def test_fetch_via_source(self):
		src = LinpxSource()
		novel = await src.fetch(SAMPLE_LINPX)
		assert novel.id == SAMPLE_ID
		assert novel.title
		assert novel.author_id
		assert novel.author_name
		assert len(novel.content) > 0
		assert novel.source == "linpx"
		print(
			f"\n[live] title={novel.title!r} "
			f"author={novel.author_name}({novel.author_id}) "
			f"tags={novel.tags[:5]} content_len={len(novel.content)}"
		)

	@pytest.mark.asyncio
	async def test_fetch_via_registry(self):
		assert resolve_source(SAMPLE_PN) is not None
		novel = await fetch_novel(SAMPLE_PN)
		assert novel.id == SAMPLE_ID
		assert novel.content

	@pytest.mark.asyncio
	async def test_fetch_plain_id(self):
		novel = await fetch_novel(SAMPLE_ID)
		assert novel.id == SAMPLE_ID


def _run_manual():
	async def main():
		print("=== parse ===")
		for s in [SAMPLE_LINPX, SAMPLE_PN, SAMPLE_PIXIV, SAMPLE_ID]:
			print(f"  {s!r} -> {parse.extract_novel_id(s)}")

		print("=== live fetch ===")
		novel = await fetch_novel(SAMPLE_LINPX)
		print(f"  id: {novel.id}")
		print(f"  title: {novel.title}")
		print(f"  author: {novel.author_name} ({novel.author_id})")
		print(f"  tags: {novel.tags}")
		print(f"  series: {novel.series_id} {novel.series_title}")
		print(f"  content_len: {len(novel.content)}")
		print(f"  content preview: {novel.content[:120]!r}...")
		print("OK")

	asyncio.run(main())


if __name__ == "__main__":
	_run_manual()