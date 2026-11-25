"""Pixiv Web API 异步客户端：URL、Cookie/Header、body 解包与错误映射。"""

from __future__ import annotations

import asyncio

import pytest

import sources.pixiv.client as client_module
from infra.http import HttpError
from sources.pixiv.client import PixivClient
from sources.pixiv.errors import (
	PixivAuthError,
	PixivNetworkError,
	PixivNotFoundError,
	PixivParseError,
	PixivRateLimitError,
)
from sources.pixiv.urls import (
	url_novel_data,
	url_series_data,
	url_series_novels_title,
	url_user_works_all,
)


def run(coro):
	return asyncio.run(coro)


def _client(**kwargs) -> PixivClient:
	return PixivClient(
		cookie=kwargs.pop("cookie", ""),
		min_interval=kwargs.pop("min_interval", 0),
		**kwargs,
	)


def _fake(payload, calls: list | None = None):
	async def fake(url, headers=None):
		if calls is not None:
			calls.append((url, dict(headers or {})))
		return payload
	return fake


def _failing(status):
	async def fake(url, headers=None):
		raise HttpError(url, status)
	return fake


def test_url_novel_data() -> None:
	assert url_novel_data(123) == "https://www.pixiv.net/ajax/novel/123"


def test_url_series_data() -> None:
	assert url_series_data(7) == "https://www.pixiv.net/ajax/novel/series/7"


def test_url_series_titles_and_author_all() -> None:
	assert url_series_novels_title(7).endswith("/ajax/novel/series/7/content_titles")
	assert url_user_works_all(42).endswith("/ajax/user/42/profile/all")


def test_headers_add_php_session_id() -> None:
	headers = _client(cookie="12345_abc").headers()
	assert headers["Cookie"] == "PHPSESSID=12345_abc"
	assert headers["Referer"] == "https://www.pixiv.net/"
	assert "Mozilla" in headers["User-Agent"]


def test_headers_keep_full_cookie_string() -> None:
	headers = _client(cookie="PHPSESSID=abc; device_token=xyz").headers()
	assert headers["Cookie"] == "PHPSESSID=abc; device_token=xyz"


def test_set_cookie_normalizes_and_clears() -> None:
	client = _client()
	client.set_cookie("new_token")
	assert client.cookie == "PHPSESSID=new_token"
	client.set_cookie("")
	assert client.has_cookie is False
	assert "Cookie" not in client.headers()


def test_cookie_from_env(monkeypatch) -> None:
	monkeypatch.setenv("PIXIV_COOKIE", "999_env")
	client = PixivClient(min_interval=0)
	assert client.cookie == "PHPSESSID=999_env"


def test_cookie_is_read_lazily_from_env(monkeypatch) -> None:
	"""构造时不读环境变量：`sources` 先于 `.env` 加载也能拿到 Cookie。"""
	monkeypatch.delenv("PIXIV_COOKIE", raising=False)
	client = PixivClient(min_interval=0)
	assert client.has_cookie is False

	monkeypatch.setenv("PIXIV_COOKIE", "late_token")
	assert client.cookie == "PHPSESSID=late_token"


def test_get_novel_returns_envelope(monkeypatch) -> None:
	"""client 只负责传输：`{error, message, body}` 外壳原样返回，解包交给解析层。"""
	calls: list = []
	payload = {"error": False, "message": "", "body": {"id": "1", "content": "正文"}}
	monkeypatch.setattr(client_module, "get_json", _fake(payload, calls))

	data = run(_client(cookie="abc").get_novel("1"))

	assert data.error is False
	assert data.body.id == "1"
	assert data.body.content == "正文"
	url, headers = calls[0]
	assert url == "https://www.pixiv.net/ajax/novel/1"
	assert headers["Cookie"] == "PHPSESSID=abc"


def test_empty_body_is_returned_as_is(monkeypatch) -> None:
	"""body 为空不在这里报错：解析层才知道这是「作品不存在」。"""
	monkeypatch.setattr(
		client_module, "get_json", _fake({"error": False, "body": None}))
	data = run(_client().get_novel("1"))
	assert data.body is None


@pytest.mark.parametrize(
	("status", "error"),
	[
		(404, PixivNotFoundError),
		(401, PixivAuthError),
		(403, PixivAuthError),
		(429, PixivRateLimitError),
		(500, PixivNetworkError),
		(None, PixivNetworkError),
	],
)
def test_http_errors_are_mapped(monkeypatch, status, error) -> None:
	monkeypatch.setattr(client_module, "get_json", _failing(status))
	with pytest.raises(error):
		run(_client().get_novel("1"))


def test_invalid_json_is_parse_error(monkeypatch) -> None:
	async def fake(url, headers=None):
		raise ValueError("not json")
	monkeypatch.setattr(client_module, "get_json", fake)
	with pytest.raises(PixivParseError):
		run(_client().get_novel("1"))


def test_get_series_titles(monkeypatch) -> None:
	calls: list = []
	payload = {
		"error": False,
		"body": [{"id": "1", "title": "A"}, {"id": "2", "title": "B"}],
	}
	monkeypatch.setattr(client_module, "get_json", _fake(payload, calls))

	titles = run(_client().get_series_titles(7))

	assert [title.id for title in titles] == ["1", "2"]
	assert [title.title for title in titles] == ["A", "B"]
	assert calls[0][0].endswith("/ajax/novel/series/7/content_titles")


def test_get_author_all(monkeypatch) -> None:
	calls: list = []
	payload = {
		"error": False,
		"body": {"novels": {"1": None}, "novelSeries": []},
	}
	monkeypatch.setattr(client_module, "get_json", _fake(payload, calls))

	data = run(_client().get_author_works(42))

	assert list(data.body.novels) == ["1"]
	assert calls[0][0].endswith("/ajax/user/42/profile/all")


def test_error_envelope_raises_not_found(monkeypatch) -> None:
	"""200 但 `error: true`：按「不存在」处理（以前这里会对 dict 取 .error 报 AttributeError）。"""
	monkeypatch.setattr(
		client_module, "get_json",
		_fake({"error": True, "message": "作品不存在", "body": None}))

	with pytest.raises(PixivNotFoundError):
		run(_client().get_novel("1"))


def test_r18_novel_without_cookie_raises_auth(monkeypatch) -> None:
	"""未登录时 R18 正文是空串（接口不报错）：必须拦成登录错误，不能产出空 txt。"""
	payload = {"error": False, "body": {"id": "1", "xRestrict": 1, "content": ""}}
	monkeypatch.setattr(client_module, "get_json", _fake(payload))

	with pytest.raises(PixivAuthError):
		run(_client().get_novel("1"))


def test_r18_novel_with_cookie_passes(monkeypatch) -> None:
	payload = {"error": False, "body": {"id": "1", "xRestrict": 1, "content": "正文"}}
	monkeypatch.setattr(client_module, "get_json", _fake(payload))

	data = run(_client(cookie="abc").get_novel("1"))

	assert data.body.content == "正文"


def test_r18_series_without_cookie_raises_auth(monkeypatch) -> None:
	"""未登录时 R18 系列的章节会打码 / 标成不可用，提前报登录错误。"""
	payload = {"error": False, "body": {"id": "9", "xRestrict": 2}}
	monkeypatch.setattr(client_module, "get_json", _fake(payload))

	with pytest.raises(PixivAuthError):
		run(_client().get_series("9"))

	# 配了 Cookie 就按正常系列返回
	series = run(_client(cookie="abc").get_series("9"))
	assert series.body.id == "9"

