"""services.import_author_service：把 Linpx 推荐作者合并进兽人作者名单。

抓取本身在 `sources.linpx.client.get_fav_users()`（这一层只拉数据、不落盘），
这里 monkeypatch 它；名单用 `tmp_path` 建独立实例，不碰真实 `data/`。

运行（在项目根目录）:
	python -m pytest test/test_import_author_service.py -q
"""

from __future__ import annotations

import asyncio
import json

import pytest

from infra.http import HttpError
from services import import_author_service
from services.import_author_service import (
	ImportAuthorResult,
	import_authors,
	merge_authors,
)
from sources.linpx import client
from sources.linpx.errors import LinpxNetworkError
from sources.linpx.urls import url_fav_user_data
from storage.author_list import ListManager


def run(coro):
	return asyncio.run(coro)


def saved_authors(tmp_path) -> dict:
	"""读回落盘的兽人作者名单，确认是真的持久化了。"""
	raw = json.loads((tmp_path / "furry_authors.json").read_text(encoding="utf-8"))
	return raw["authors"]


def test_merge_adds_new_authors(tmp_path) -> None:
	mgr = ListManager(tmp_path)

	result = merge_authors(
		[{"id": 1, "name": "甲"}, {"id": "2", "name": "乙"}], mgr)

	assert result.ok is True
	assert (result.total, result.added, result.skipped) == (2, 2, 0)
	assert result.new_authors == (("1", "甲"), ("2", "乙"))
	assert mgr.is_furryauthor(1)
	assert mgr.is_furryauthor("2")
	assert mgr.furrylist.get("1")["note"] == "Linpx"
	assert set(saved_authors(tmp_path)) == {"1", "2"}


def test_merge_skips_known_and_blacklisted(tmp_path) -> None:
	mgr = ListManager(tmp_path)
	mgr.add_furrylist("1", name="甲", note="兽人阅读")
	mgr.add_blacklist("2", name="乙")

	result = merge_authors(
		[{"id": "1", "name": "甲"}, {"id": "2", "name": "乙"}], mgr)

	assert (result.total, result.added, result.skipped) == (2, 0, 2)
	assert mgr.furrylist.get("1")["note"] == "兽人阅读"  # 不覆盖人工维护的 note
	assert not mgr.is_furryauthor("2")  # 黑名单不会被「推荐」加回可下载名单


def test_merge_ignores_bad_items_and_duplicates(tmp_path) -> None:
	mgr = ListManager(tmp_path)

	result = merge_authors(
		[{"id": ""}, {"name": "没有 ID"}, "x", {"id": 3}, {"id": "3", "name": "丙"}],
		mgr,
	)

	assert (result.total, result.added, result.skipped) == (2, 1, 1)
	assert result.new_authors == (("3", ""),)


def test_import_merges_fetched_authors(tmp_path, monkeypatch) -> None:
	mgr = ListManager(tmp_path)
	calls: list[bool] = []

	async def fake_get_fav_users():
		calls.append(True)
		return [{"id": 7, "name": "丙"}]

	monkeypatch.setattr(import_author_service, "get_fav_users", fake_get_fav_users)

	result = run(import_authors(mgr))

	assert calls == [True]
	assert (result.ok, result.total, result.added) == (True, 1, 1)
	assert mgr.is_furryauthor("7")


def test_import_reports_network_failure(tmp_path, monkeypatch) -> None:
	async def fake_get_fav_users():
		raise LinpxNetworkError("Linpx 暂时无法访问")

	monkeypatch.setattr(import_author_service, "get_fav_users", fake_get_fav_users)

	result = run(import_authors(ListManager(tmp_path)))

	assert result == ImportAuthorResult(False, error=import_author_service.FETCH_ERROR)


# ---- sources/linpx/client.get_fav_users：只拉数据，不落盘 ----


def test_client_get_fav_users_returns_json_list(monkeypatch) -> None:
	captured: dict = {}

	async def fake_get_json(url, headers=None):
		captured["url"] = url
		captured["headers"] = headers
		return [{"id": 1, "name": "甲"}]

	monkeypatch.setattr(client, "get_json", fake_get_json)

	data = run(client.get_fav_users())

	assert captured["url"] == url_fav_user_data()
	assert captured["headers"]
	assert data == [{"id": 1, "name": "甲"}]
	assert data[0].id == 1  # 已转成 JsonDict


def test_client_get_fav_users_404_is_empty(monkeypatch) -> None:
	async def fake_get_json(url, headers=None):
		raise HttpError(url, 404)

	monkeypatch.setattr(client, "get_json", fake_get_json)

	assert run(client.get_fav_users()) == []


def test_client_get_fav_users_rejects_non_list(monkeypatch) -> None:
	async def fake_get_json(url, headers=None):
		return {"id": 1}

	monkeypatch.setattr(client, "get_json", fake_get_json)

	assert run(client.get_fav_users()) == []


def test_client_get_fav_users_reports_network_error(monkeypatch) -> None:
	async def fake_get_json(url, headers=None):
		raise HttpError(url, 500)

	monkeypatch.setattr(client, "get_json", fake_get_json)

	with pytest.raises(LinpxNetworkError):
		run(client.get_fav_users())


if __name__ == "__main__":
	pytest.main([__file__, "-q"])
