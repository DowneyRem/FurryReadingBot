"""Pixiv Web API 异步客户端：URL、Cookie/Header、body 解包与错误映射。"""

from __future__ import annotations

import asyncio

import pytest

import io
from dotenv import dotenv_values

import sources.pixiv.client as client_module
from infra.http import HttpError
from sources.pixiv.client import (
	PixivAccount,
	PixivClient,
	extract_csrf_token,
	parse_cookies,
)
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
	async def fake(url, headers=None, **kwargs):
		if calls is not None:
			calls.append((url, dict(headers or {})))
		return payload
	return fake


def _failing(status):
	async def fake(url, headers=None, **kwargs):
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


def test_parse_cookies_supports_multiline_and_separator() -> None:
	raw = """
	# 注释行应跳过
	111_aaa

	222_bbb || PHPSESSID=333_ccc; device_token=xyz,abc
	PHPSESSID=111_aaa
	"""
	assert parse_cookies(raw) == [
		"PHPSESSID=111_aaa",
		"PHPSESSID=222_bbb",
		"PHPSESSID=333_ccc; device_token=xyz,abc",
	]


def test_dotenv_multiline_cookie_parses_into_accounts() -> None:
	env_text = (
		'PIXIV_COOKIE="119908520_token1\n'
		'220011220_token2\n'
		'PHPSESSID=330011220_token3; device_token=xyz"\n'
	)
	parsed = dotenv_values(stream=io.StringIO(env_text))
	client = PixivClient(cookie=parsed["PIXIV_COOKIE"], min_interval=0)

	assert [acc.uid for acc in client.accounts] == ["119908520", "220011220", "330011220"]
	assert client.cookies == [
		"PHPSESSID=119908520_token1",
		"PHPSESSID=220011220_token2",
		"PHPSESSID=330011220_token3; device_token=xyz",
	]


def test_account_uid_label_and_csrf_headers() -> None:
	acc = PixivAccount(cookie="a=1; PHPSESSID=119908520_secret; b=2", csrf_token="f" * 32)
	assert acc.uid == "119908520"
	assert acc.label == "uid=119908520"
	assert "secret" not in acc.label

	no_csrf = acc.headers()
	assert "x-csrf-token" not in no_csrf
	with_csrf = acc.headers(include_csrf=True)
	assert with_csrf["x-csrf-token"] == "f" * 32
	assert with_csrf["Cookie"] == "a=1; PHPSESSID=119908520_secret; b=2"



def test_round_robin_rotates_accounts_and_concurrent_requests(monkeypatch) -> None:
	seen_cookies: list[str] = []

	async def fake(url, headers=None, **kwargs):
		seen_cookies.append((headers or {}).get("Cookie", ""))
		return {"error": False, "body": {"id": "1", "content": "ok"}}

	monkeypatch.setattr(client_module, "get_json", fake)
	client = PixivClient(cookies=["1_a", "2_b", "3_c"], min_interval=0)

	for _ in range(5):
		run(client.get_novel("1"))

	assert seen_cookies == [
		"PHPSESSID=1_a",
		"PHPSESSID=2_b",
		"PHPSESSID=3_c",
		"PHPSESSID=1_a",
		"PHPSESSID=2_b",
	]

	seen_cookies.clear()

	async def gather_three() -> None:
		await asyncio.gather(
			client.get_novel("1"),
			client.get_novel("2"),
			client.get_novel("3"),
		)

	run(gather_three())
	assert sorted(seen_cookies) == ["PHPSESSID=1_a", "PHPSESSID=2_b", "PHPSESSID=3_c"]


def test_401_marks_account_dead_and_fails_over(monkeypatch) -> None:
	attempts: list[str] = []

	async def fake(url, headers=None, **kwargs):
		cookie = (headers or {}).get("Cookie", "")
		attempts.append(cookie)
		if cookie == "PHPSESSID=1_dead":
			raise HttpError(url, 401)
		return {"error": False, "body": {"id": "1", "content": "ok"}}

	monkeypatch.setattr(client_module, "get_json", fake)
	client = PixivClient(cookies=["1_dead", "2_good"], min_interval=0)

	data = run(client.get_novel("1"))
	assert data.body.content == "ok"
	assert attempts == ["PHPSESSID=1_dead", "PHPSESSID=2_good"]
	assert client.accounts[0].dead is True
	assert client.accounts[1].dead is False

	attempts.clear()
	run(client.get_novel("2"))
	assert attempts == ["PHPSESSID=2_good"]

	# 仅剩的号也 401 后，再请求直接报错且不再打网络
	async def always_401(url, headers=None, **kwargs):
		attempts.append((headers or {}).get("Cookie", ""))
		raise HttpError(url, 401)

	attempts.clear()
	monkeypatch.setattr(client_module, "get_json", always_401)
	with pytest.raises(PixivAuthError):
		run(client.get_novel("3"))
	assert attempts == ["PHPSESSID=2_good"]

	attempts.clear()
	with pytest.raises(PixivAuthError):
		run(client.get_novel("4"))
	assert attempts == []


def test_403_only_kills_bad_account_when_backup_succeeds(monkeypatch) -> None:
	attempts: list[str] = []

	async def partial_403(url, headers=None, **kwargs):
		cookie = (headers or {}).get("Cookie", "")
		attempts.append(cookie)
		if cookie == "PHPSESSID=1_bad":
			raise HttpError(url, 403)
		return {"error": False, "body": {"id": "1", "content": "ok"}}

	monkeypatch.setattr(client_module, "get_json", partial_403)
	client = PixivClient(cookies=["1_bad", "2_good"], min_interval=0)

	assert run(client.get_novel("1")).body.content == "ok"
	assert client.accounts[0].dead is True

	# 目标作品全员 403（如仅好友可见）：不应把健康账号池全部标死
	async def all_403(url, headers=None, **kwargs):
		raise HttpError(url, 403)

	client2 = PixivClient(cookies=["1_ok", "2_ok"], min_interval=0)
	monkeypatch.setattr(client_module, "get_json", all_403)
	with pytest.raises(PixivAuthError):
		run(client2.get_novel("99"))
	assert all(not acc.dead for acc in client2.accounts)


def test_429_cools_down_account_switches_immediately_and_recovers(monkeypatch) -> None:
	now = [100.0]
	monkeypatch.setattr(client_module.time, "monotonic", lambda: now[0])

	calls: list[tuple[str, bool | None]] = []

	async def fake(url, headers=None, **kwargs):
		cookie = (headers or {}).get("Cookie", "")
		calls.append((cookie, kwargs.get("retry_on_429")))
		if cookie == "PHPSESSID=1_limit" and now[0] < 160.0:
			raise HttpError(url, 429)
		return {"error": False, "body": {"id": "1", "content": "ok"}}

	monkeypatch.setattr(client_module, "get_json", fake)
	client = PixivClient(
		cookies=["1_limit", "2_good"],
		min_interval=0,
		cooldown_seconds=60.0,
	)

	# 有多个候选号时应禁用底层 429 原地退避，立即切号
	data = run(client.get_novel("1"))
	assert data.body.content == "ok"
	assert calls == [
		("PHPSESSID=1_limit", False),
		("PHPSESSID=2_good", False),
	]

	# 冷却期内不再打 1_limit
	calls.clear()
	run(client.get_novel("2"))
	assert calls == [("PHPSESSID=2_good", None)]

	# 若全部账号都进入冷却，直接抛 PixivRateLimitError 且不打网络
	async def fail_429(url, headers=None, **kwargs):
		calls.append(((headers or {}).get("Cookie", ""), kwargs.get("retry_on_429")))
		raise HttpError(url, 429)

	calls.clear()
	monkeypatch.setattr(client_module, "get_json", fail_429)
	with pytest.raises(PixivRateLimitError):
		run(client.get_novel("3"))
	assert calls == [("PHPSESSID=2_good", None)]

	calls.clear()
	with pytest.raises(PixivRateLimitError):
		run(client.get_novel("4"))
	assert calls == []

	# 冷却期满后自动恢复轮换
	now[0] = 160.0
	calls.clear()
	monkeypatch.setattr(client_module, "get_json", fake)
	run(client.get_novel("5"))
	run(client.get_novel("6"))
	assert [cookie for cookie, _ in calls] == ["PHPSESSID=1_limit", "PHPSESSID=2_good"]


def test_r18_empty_content_fails_over_to_working_account(monkeypatch) -> None:
	attempts: list[str] = []

	async def fake(url, headers=None, **kwargs):
		cookie = (headers or {}).get("Cookie", "")
		attempts.append(cookie)
		if cookie == "PHPSESSID=1_no_r18":
			return {"error": False, "body": {"id": "1", "xRestrict": 1, "content": ""}}
		return {"error": False, "body": {"id": "1", "xRestrict": 1, "content": "R18正文"}}

	monkeypatch.setattr(client_module, "get_json", fake)
	client = PixivClient(cookies=["1_no_r18", "2_r18"], min_interval=0)

	data = run(client.get_novel("1"))
	assert data.body.content == "R18正文"
	assert attempts == ["PHPSESSID=1_no_r18", "PHPSESSID=2_r18"]
	assert client.accounts[0].dead is True


def test_per_account_throttle_does_not_delay_other_accounts(monkeypatch) -> None:
	now = [100.0]
	sleeps: list[float] = []
	monkeypatch.setattr(client_module.time, "monotonic", lambda: now[0])

	async def fake_sleep(delay: float) -> None:
		sleeps.append(delay)
		now[0] += delay

	async def fake_json(url, headers=None, **kwargs):
		return {"error": False, "body": {"id": "1", "content": "ok"}}

	monkeypatch.setattr(client_module.asyncio, "sleep", fake_sleep)
	monkeypatch.setattr(client_module, "get_json", fake_json)

	client = PixivClient(cookies=["1_a", "2_b"], min_interval=0.5)
	run(client.get_novel("1"))  # account 1 at 100.0
	run(client.get_novel("2"))  # account 2 at 100.0（不等待）
	assert sleeps == []

	run(client.get_novel("3"))  # 再次回到 account 1，应等待 0.5s
	assert sleeps == [pytest.approx(0.5)]


def test_env_change_refreshes_pool_and_clears_dead_state(monkeypatch) -> None:
	monkeypatch.setenv("PIXIV_COOKIE", "1_bad")
	client = PixivClient(min_interval=0)

	monkeypatch.setattr(client_module, "get_json", _failing(401))
	with pytest.raises(PixivAuthError):
		run(client.get_novel("1"))
	assert client.accounts[0].dead is True

	# 热更新环境变量后，新账号池恢复可用
	monkeypatch.setenv("PIXIV_COOKIE", "1_bad\n2_fresh")
	assert client.cookies == ["PHPSESSID=1_bad", "PHPSESSID=2_fresh"]
	assert all(not acc.dead for acc in client.accounts)


def test_extract_and_ensure_csrf_token(monkeypatch) -> None:
	token = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
	assert extract_csrf_token(f'{{"token":"{token}"}}') == token
	assert extract_csrf_token(f'token\\":\\"{token}\\"') == token
	assert extract_csrf_token("<html>no token</html>") is None

	calls: list[dict[str, str]] = []

	async def fake_get_text(url, headers=None, **kwargs):
		calls.append(dict(headers or {}))
		return f'<meta id="meta-global-data" content=\'{{"token":"{token}"}}\'>'

	monkeypatch.setattr(client_module, "get_text", fake_get_text)
	client = PixivClient(cookies=["119908520_secret"], min_interval=0)
	account = client.accounts[0]

	first = run(client.ensure_csrf_token(account))
	second = run(client.ensure_csrf_token(account))
	assert first == token
	assert second == token
	assert account.csrf_token == token
	assert len(calls) == 1
	assert calls[0]["Cookie"] == "PHPSESSID=119908520_secret"

	# 显式 refresh=True 时才重新拉取
	third = run(client.ensure_csrf_token(account, refresh=True))
	assert third == token
	assert len(calls) == 2

