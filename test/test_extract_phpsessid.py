"""script/extract_phpsessid.py：从文本或浏览器获取 Pixiv PHPSESSID 并合并写入 pixiv.env。

运行（在项目根目录）:
	.venv\\Scripts\\python.exe -m pytest test/test_extract_phpsessid.py -q
"""

from __future__ import annotations

import pytest

from script.extract_phpsessid import extract_phpsessids, format_phpsessids, main


def test_extract_from_full_cookie_string() -> None:
	raw = (
		'"pixivCookie": "privacy_policy_notification=0; _ga=GA1.1.123; '
		'PHPSESSID=119908520_tJKwi60P7fefHmhTRg8HwJk75SKE64gp; '
		'__cf_bm=JJsuIRjBMKOAB4; first_visit_datetime=2026-11-02"'
	)
	assert extract_phpsessids(raw) == ["119908520_tJKwi60P7fefHmhTRg8HwJk75SKE64gp"]


def test_extract_supports_json_tsv_url_encoded_and_bare_tokens() -> None:
	tok1 = "119908520_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	tok2 = "220011220_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	tok3 = "330011220_cccccccccccccccccccccccccccccccc"
	tok4 = "440011220_dddddddddddddddddddddddddddddddd"
	tok5 = "550011220_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"

	text = "\n".join([
		f"裸值行：{tok1}",
		f'{{"PHPSESSID": "{tok2}"}}',
		f".pixiv.net\tTRUE\t/\tTRUE\t1799999999\tPHPSESSID\t{tok3}",
		f"PHPSESSID\t{tok4}\t.pixiv.net\t/",
		f"Cookie%3A+PHPSESSID%3D{tok5}%3B+__cf_bm%3Dabc",
		f"other_cookie=999999999_zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz",
		f"重复值：{tok2}",
	])

	assert extract_phpsessids(text) == [tok1, tok2, tok3, tok4, tok5]
	assert extract_phpsessids(text, strict=True) == [tok2, tok3, tok4, tok5]


def test_format_phpsessids_outputs_expected_shapes() -> None:
	values = ["111_aaa", "222_bbb"]
	assert format_phpsessids(values, "bare") == "111_aaa\n222_bbb"
	assert format_phpsessids(values, "pipe") == "111_aaa || 222_bbb"
	assert format_phpsessids(values, "env") == 'PIXIV_COOKIE="111_aaa\n222_bbb"'
	assert format_phpsessids(["111_aaa"], "env") == 'PIXIV_COOKIE="111_aaa"'
	# 默认就是 env（写入 pixiv.env 用）
	assert format_phpsessids(values) == format_phpsessids(values, "env")
	with pytest.raises(ValueError):
		format_phpsessids(values, "kv")


def test_read_existing_phpsessids_supports_env_and_bare(tmp_path) -> None:
	from script.extract_phpsessid import read_existing_phpsessids

	a = "119908520_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	b = "220011220_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

	env_file = tmp_path / "old.env"
	env_file.write_text(f'PIXIV_COOKIE="{a}\n{b}"\n', encoding="utf-8")
	assert read_existing_phpsessids(env_file) == [a, b]

	raw = tmp_path / "raw.txt"
	raw.write_text(
		f"other_cookie=999999999_zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz\n{a}\n",
		encoding="utf-8",
	)
	assert read_existing_phpsessids(raw) == [a]

	assert read_existing_phpsessids(tmp_path / "missing.env") == []


def test_merge_phpsessids_keeps_existing_order() -> None:
	from script.extract_phpsessid import merge_phpsessids

	old = "119908520_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	new = "220011220_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	assert merge_phpsessids([old], [new, old]) == [old, new]


def test_cli_writes_pixiv_env_with_merge(tmp_path, monkeypatch, capsys) -> None:
	monkeypatch.chdir(tmp_path)
	old = "119908520_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	new = "220011220_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	src = tmp_path / "raw.txt"
	src.write_text(f"PHPSESSID={new}\n", encoding="utf-8")

	out = tmp_path / "pixiv.env"
	out.write_text(f'PIXIV_COOKIE="{old}"\n', encoding="utf-8")

	assert main([str(src)]) == 0
	assert out.read_text(encoding="utf-8") == f'PIXIV_COOKIE="{old}\n{new}"\n'
	err = capsys.readouterr().err
	assert "已有的 1 个" in err
	assert "新增 1 个" in err

	# 幂等：重复运行不会重复追加
	assert main([str(src)]) == 0
	assert out.read_text(encoding="utf-8") == f'PIXIV_COOKIE="{old}\n{new}"\n'
	assert "新增 0 个" in capsys.readouterr().err


def test_cli_creates_pixiv_env_when_missing(tmp_path, monkeypatch, capsys) -> None:
	monkeypatch.chdir(tmp_path)
	token = "119908520_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

	assert main(["-t", f"PHPSESSID={token}"]) == 0
	assert (tmp_path / "pixiv.env").read_text(encoding="utf-8") == f'PIXIV_COOKIE="{token}"\n'
	assert token in capsys.readouterr().out


def test_cli_reads_non_utf8_file(tmp_path, monkeypatch) -> None:
	"""ANSI / GBK 文本不该崩栈，替换非法字节后仍能提取 ASCII 的 token。"""
	monkeypatch.chdir(tmp_path)
	token = "119908520_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	src = tmp_path / "gbk.txt"
	src.write_bytes(f"备注：PHPSESSID={token}".encode("gbk"))

	assert main([str(src)]) == 0
	assert token in (tmp_path / "pixiv.env").read_text(encoding="utf-8")


def test_cli_reports_when_nothing_found(tmp_path, monkeypatch, capsys) -> None:
	monkeypatch.chdir(tmp_path)
	src = tmp_path / "empty.txt"
	src.write_text("nothing here", encoding="utf-8")

	assert main([str(src)]) == 1
	assert "未提取到" in capsys.readouterr().err
	assert not (tmp_path / "pixiv.env").exists()

def test_cdp_cookie_filter_ignores_guest_phpsessid() -> None:
	from script.extract_phpsessid import extract_auth_phpsessid_from_cdp_cookies

	guest_cookies = [
		{"name": "PHPSESSID", "domain": ".pixiv.net", "value": "a1cdd6e3b94810293847561029384756"},
		{"name": "PHPSESSID", "domain": "example.com", "value": "119908520_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
	]
	assert extract_auth_phpsessid_from_cdp_cookies(guest_cookies) is None

	authed_cookies = [
		*guest_cookies,
		{"name": "PHPSESSID", "domain": ".pixiv.net", "value": "119908520_tJKwi60P7fefHmhTRg8HwJk75SKE64gp"},
	]
	assert (
		extract_auth_phpsessid_from_cdp_cookies(authed_cookies)
		== "119908520_tJKwi60P7fefHmhTRg8HwJk75SKE64gp"
	)


def test_pick_free_port_and_browser_lookup(tmp_path, monkeypatch) -> None:
	from script.extract_phpsessid import _pick_free_port, find_browser

	port = _pick_free_port()
	assert isinstance(port, int)
	assert 0 < port < 65536

	fake_chrome = tmp_path / "chrome.exe"
	fake_chrome.write_text("", encoding="utf-8")
	monkeypatch.setattr(
		"script.extract_phpsessid._browser_candidates",
		lambda kind: [fake_chrome] if kind == "chrome" else [],
	)
	assert find_browser("auto") == fake_chrome


def test_build_login_command_opens_home_page_in_incognito(tmp_path) -> None:
	from script.extract_phpsessid import PIXIV_HOME_URL, _build_login_command

	browser = tmp_path / "chrome.exe"
	cmd = _build_login_command(browser, tmp_path, port=9333)

	assert cmd[0] == str(browser)
	assert cmd[-1] == PIXIV_HOME_URL == "https://www.pixiv.net/"
	assert "--incognito" in cmd
	assert f"--user-data-dir={tmp_path}" in cmd
	assert "--remote-debugging-port=9333" in cmd

	plain = _build_login_command(browser, tmp_path, port=9333, incognito=False)
	assert "--incognito" not in plain
	assert plain[-1] == PIXIV_HOME_URL


def test_wait_for_login_cookie_via_mock_cdp_ws(monkeypatch) -> None:
	import asyncio
	import script.extract_phpsessid as mod

	class FakeProc:
		def poll(self):
			return None

	class FakeWS:
		def __init__(self) -> None:
			self.sent: list[dict] = []
			self.cookie_reads = 0

		async def __aenter__(self):
			return self

		async def __aexit__(self, *args):
			return False

		async def send_json(self, payload: dict) -> None:
			self.sent.append(payload)

		async def receive_json(self, timeout=None) -> dict:
			req = self.sent[-1]
			method = req["method"]
			result: dict = {}
			if method == "Target.getTargets":
				result = {
					"targetInfos": [
						{"type": "page", "targetId": "page-1", "url": "https://www.pixiv.net/"},
					]
				}
			elif method == "Target.attachToTarget":
				result = {"sessionId": "sess-1"}
			elif method == "Network.getCookies":
				self.cookie_reads += 1
				if self.cookie_reads == 1:
					cookies = [{"name": "PHPSESSID", "domain": ".pixiv.net", "value": "guest_no_uid_32chars_000000000000"}]
				else:
					cookies = [{"name": "PHPSESSID", "domain": ".pixiv.net", "value": "119908520_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}]
				result = {"cookies": cookies}
			resp: dict = {"id": req["id"], "result": result}
			if req.get("sessionId"):
				resp["sessionId"] = req["sessionId"]
			return resp

	fake_ws = FakeWS()

	class FakeResp:
		async def __aenter__(self):
			return self

		async def __aexit__(self, *args):
			return False

		async def json(self, **kwargs):
			return {"webSocketDebuggerUrl": "ws://127.0.0.1:14338/devtools/browser/abc"}

	class FakeSession:
		async def __aenter__(self):
			return self

		async def __aexit__(self, *args):
			return False

		def get(self, url, **kwargs):
			assert url == "http://127.0.0.1:14338/json/version"
			return FakeResp()

		def ws_connect(self, url, **kwargs):
			assert url == "ws://127.0.0.1:14338/devtools/browser/abc"
			return fake_ws

	monkeypatch.setattr(mod.aiohttp, "ClientSession", lambda: FakeSession())
	token = asyncio.run(
		mod._wait_for_login_cookie(
			FakeProc(),
			14338,
			timeout=5.0,
			poll_interval=0,
			allow_browser_wide=False,
		)
	)
	assert token == "119908520_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	assert [item["method"] for item in fake_ws.sent] == [
		"Target.getTargets",
		"Target.attachToTarget",
		"Network.enable",
		"Network.getCookies",
		"Network.getCookies",
		"Browser.close",
	]


def test_wait_for_login_cookie_incognito_ignores_browser_wide_cookies(monkeypatch) -> None:
	"""无痕模式下不能回落到浏览器级 Storage.getCookies，否则会误读常规窗口的登录态。"""
	import asyncio
	import script.extract_phpsessid as mod

	class FakeProc:
		def poll(self):
			return None

	class FakeWS:
		def __init__(self) -> None:
			self.sent: list[dict] = []

		async def __aenter__(self):
			return self

		async def __aexit__(self, *args):
			return False

		async def send_json(self, payload: dict) -> None:
			self.sent.append(payload)

		async def receive_json(self, timeout=None) -> dict:
			req = self.sent[-1]
			if req["method"] == "Storage.getCookies":
				result = {
					"cookies": [
						{
							"name": "PHPSESSID",
							"domain": ".pixiv.net",
							"value": "999999999_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
						}
					]
				}
			else:
				result = {"targetInfos": []}
			return {"id": req["id"], "result": result}

	fake_ws = FakeWS()

	class FakeResp:
		async def __aenter__(self):
			return self

		async def __aexit__(self, *args):
			return False

		async def json(self, **kwargs):
			return {"webSocketDebuggerUrl": "ws://127.0.0.1:14338/devtools/browser/abc"}

	class FakeSession:
		async def __aenter__(self):
			return self

		async def __aexit__(self, *args):
			return False

		def get(self, url, **kwargs):
			return FakeResp()

		def ws_connect(self, url, **kwargs):
			return fake_ws

	monkeypatch.setattr(mod.aiohttp, "ClientSession", lambda: FakeSession())

	with pytest.raises(TimeoutError):
		asyncio.run(
			mod._wait_for_login_cookie(
				FakeProc(),
				14338,
				timeout=1.0,
				poll_interval=0,
				allow_browser_wide=False,
			)
		)
	assert all(item["method"] != "Storage.getCookies" for item in fake_ws.sent)

	token = asyncio.run(
		mod._wait_for_login_cookie(
			FakeProc(),
			14338,
			timeout=1.0,
			poll_interval=0,
			allow_browser_wide=True,
		)
	)
	assert token == "999999999_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def test_login_and_capture_reuses_profile_dir_and_skips_duplicates(tmp_path, monkeypatch) -> None:
	import script.extract_phpsessid as mod

	seen: list[tuple] = []

	def fake_capture(browser_path, profile_dir, **kwargs):
		seen.append((profile_dir, kwargs))
		return "111111_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

	monkeypatch.setattr(mod, "_capture_once", fake_capture)
	profile = tmp_path / "profile"

	values = mod.login_and_capture(tmp_path / "chrome.exe", profile_dir=profile, count=2)

	assert values == ["111111_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]
	assert profile.is_dir()
	assert [str(item[0]) for item in seen] == [str(profile), str(profile)]
	assert seen[0][1]["incognito"] is True
	assert seen[0][1]["start_url"] == mod.PIXIV_HOME_URL


def test_login_and_capture_hints_when_browser_unavailable(tmp_path, monkeypatch) -> None:
	import script.extract_phpsessid as mod

	def boom(*args, **kwargs):
		raise mod.BrowserStartupError("浏览器已关闭，登录已取消")

	monkeypatch.setattr(mod, "_capture_once", boom)

	with pytest.raises(RuntimeError) as info:
		mod.login_and_capture(tmp_path / "chrome.exe", profile_dir=tmp_path / "p")
	assert "--profile-dir" in str(info.value)


def test_login_and_capture_keeps_plain_login_timeout(tmp_path, monkeypatch) -> None:
	import script.extract_phpsessid as mod

	def timeout(*args, **kwargs):
		raise TimeoutError("等待 Pixiv 登录超时（300 秒）")

	monkeypatch.setattr(mod, "_capture_once", timeout)

	with pytest.raises(TimeoutError) as info:
		mod.login_and_capture(tmp_path / "chrome.exe", profile_dir=tmp_path / "p")
	assert "--profile-dir" not in str(info.value)


def test_cli_login_mode_writes_pixiv_env(tmp_path, monkeypatch, capsys) -> None:
	import script.extract_phpsessid as mod

	monkeypatch.chdir(tmp_path)
	fake_browser = tmp_path / "chrome.exe"
	fake_browser.write_text("", encoding="utf-8")
	monkeypatch.setattr(mod, "find_browser", lambda browser: fake_browser)
	monkeypatch.setattr(
		mod,
		"login_and_capture",
		lambda browser_path, **kwargs: [
			"111111_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			"222222_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
		],
	)

	assert main(["--login", "--count", "2"]) == 0
	assert (tmp_path / "pixiv.env").read_text(encoding="utf-8") == (
		'PIXIV_COOKIE="111111_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n'
		'222222_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"\n'
	)
	captured = capsys.readouterr()
	assert "222222_bbbb" in captured.out
	assert "已提取 2 个" in captured.err

	assert main(["--login", "-t", "abc"]) == 2


def test_cli_login_mode_passes_options(tmp_path, monkeypatch) -> None:
	import script.extract_phpsessid as mod

	monkeypatch.chdir(tmp_path)
	fake_browser = tmp_path / "chrome.exe"
	fake_browser.write_text("", encoding="utf-8")
	defaults = dict(mod.login_and_capture.__kwdefaults__ or {})
	monkeypatch.setattr(mod, "find_browser", lambda browser: fake_browser)
	captured: dict = {}

	def fake_login(browser_path, **kwargs):
		captured.update(kwargs)
		return ["111111_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]

	monkeypatch.setattr(mod, "login_and_capture", fake_login)

	assert main(["--login"]) == 0
	assert captured["profile_dir"] == defaults["profile_dir"] == mod.DEFAULT_PROFILE_DIR
	assert str(captured["profile_dir"]) == ".pixiv-profile"
	assert captured["incognito"] is True
	assert defaults["start_url"] == mod.PIXIV_HOME_URL == "https://www.pixiv.net/"

	captured.clear()
	custom = tmp_path / "custom"
	assert main(["--login", "--profile-dir", str(custom), "--no-incognito"]) == 0
	assert captured["profile_dir"] == custom
	assert captured["incognito"] is False


def test_ensure_writable_dir_reports_unwritable(tmp_path) -> None:
	"""配置目录不可写时立刻报错，而不是让 Chrome 弹「无法创建数据目录」后干等。"""
	import script.extract_phpsessid as mod

	blocker = tmp_path / "not-a-dir"
	blocker.write_text("x", encoding="utf-8")

	with pytest.raises(mod.BrowserStartupError) as info:
		mod._ensure_writable_dir(blocker)
	assert "无法读写" in str(info.value)
	assert "--profile-dir" in str(info.value)

	ok = tmp_path / "profile"
	mod._ensure_writable_dir(ok)
	assert ok.is_dir()
	assert not (ok / ".write-probe").exists()


def test_wait_for_login_cookie_reports_missing_devtools_port(monkeypatch) -> None:
	import asyncio
	import script.extract_phpsessid as mod

	class FakeProc:
		def poll(self):
			return None

	class FakeResp:
		async def __aenter__(self):
			return self

		async def __aexit__(self, *args):
			return False

		async def json(self, **kwargs):
			return {}

	class FakeSession:
		async def __aenter__(self):
			return self

		async def __aexit__(self, *args):
			return False

		def get(self, url, **kwargs):
			return FakeResp()

	monkeypatch.setattr(mod.aiohttp, "ClientSession", lambda: FakeSession())

	with pytest.raises(mod.BrowserStartupError) as info:
		asyncio.run(
			mod._wait_for_login_cookie(
				FakeProc(),
				14338,
				timeout=0.4,
				startup_timeout=0.4,
				poll_interval=0,
			)
		)
	assert "没有提供调试端口" in str(info.value)


def test_read_stdin_decodes_utf8_bytes(monkeypatch) -> None:
	import io
	import script.extract_phpsessid as mod

	class FakeStdin:
		buffer = io.BytesIO("备注：PHPSESSID=119908520_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa".encode("utf-8"))

	monkeypatch.setattr(mod.sys, "stdin", FakeStdin())
	text = mod._read_stdin()
	assert "备注" in text
	assert "119908520_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" in text


def test_cli_warns_when_format_is_not_env(tmp_path, monkeypatch, capsys) -> None:
	monkeypatch.chdir(tmp_path)
	token = "119908520_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

	assert main(["-t", f"PHPSESSID={token}", "-f", "pipe"]) == 0
	assert (tmp_path / "pixiv.env").read_text(encoding="utf-8") == f"{token}\n"
	assert "不是 .env 格式" in capsys.readouterr().err

