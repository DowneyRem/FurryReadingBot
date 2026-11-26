"""script/extract_phpsessid.py：从多类文本中提取 Pixiv PHPSESSID。

运行（在项目根目录）:
\t.venv\\Scripts\\python.exe -m pytest test/test_extract_phpsessid.py -q
"""

from __future__ import annotations

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
	assert len(extract_phpsessids(text, dedup=False)) == 6


def test_format_phpsessids_outputs_expected_shapes() -> None:
	values = ["111_aaa", "222_bbb"]
	assert format_phpsessids(values, "bare") == "111_aaa\n222_bbb"
	assert format_phpsessids(values, "kv") == "PHPSESSID=111_aaa\nPHPSESSID=222_bbb"
	assert format_phpsessids(values, "pipe") == "111_aaa || 222_bbb"
	assert format_phpsessids(values, "env") == 'PIXIV_COOKIE="111_aaa\n222_bbb"'
	assert format_phpsessids(["111_aaa"], "env") == "PIXIV_COOKIE=111_aaa"


def test_cli_reads_file_and_writes_output(tmp_path, capsys) -> None:
	src = tmp_path / "raw.txt"
	out = tmp_path / "out.env"
	src.write_text(
		"a=1; PHPSESSID=111_aaa; b=2\nPHPSESSID=222_bbb\n",
		encoding="utf-8",
	)

	code = main([str(src), "--format", "env", "-o", str(out)])
	assert code == 0
	assert out.read_text(encoding="utf-8") == 'PIXIV_COOKIE="111_aaa\n222_bbb"\n'

	empty = tmp_path / "empty.txt"
	empty.write_text("nothing here", encoding="utf-8")
	assert main([str(empty)]) == 1
	assert "未提取到" in capsys.readouterr().err


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
	monkeypatch.setattr("script.extract_phpsessid._browser_candidates", lambda kind: [fake_chrome] if kind == "chrome" else [])
	assert find_browser("chrome") == fake_chrome


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


def test_cli_login_mode_formats_multi_account_output(tmp_path, monkeypatch, capsys) -> None:
	import script.extract_phpsessid as mod

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

	out = tmp_path / "pixiv.env"
	code = main(["--login", "--count", "2", "--format", "env", "-o", str(out)])
	assert code == 0
	assert out.read_text(encoding="utf-8") == (
		'PIXIV_COOKIE="111111_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n'
		'222222_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"\n'
	)
	assert main(["--login", "-t", "abc"]) == 2
	assert "不能与文件或 --text" in capsys.readouterr().err


def test_wait_for_login_cookie_incognito_ignores_browser_wide_cookies(monkeypatch) -> None:
	"""无痕模式下不能回落到浏览器级 Storage.getCookies，否则会误读常规窗口的登录态。"""
	import asyncio
	import pytest
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


def test_build_login_command_opens_home_page_in_incognito(tmp_path) -> None:
	from script.extract_phpsessid import PIXIV_HOME_URL, _build_login_command

	browser = tmp_path / "chrome.exe"
	cmd = _build_login_command(browser, tmp_path, port=9333)

	assert cmd[0] == str(browser)
	assert cmd[-1] == PIXIV_HOME_URL == "https://www.pixiv.net/"
	assert "--incognito" in cmd
	assert f"--user-data-dir={tmp_path}" in cmd
	assert "--new-window" not in cmd
	assert "--remote-debugging-port=9333" in cmd

	plain = _build_login_command(browser, tmp_path, port=9333, incognito=False)
	assert "--incognito" not in plain
	assert plain[-1] == PIXIV_HOME_URL


def test_default_user_data_dir_prefers_existing_profile(tmp_path, monkeypatch) -> None:
	import script.extract_phpsessid as mod

	monkeypatch.setattr(mod.sys, "platform", "linux")
	monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
	(tmp_path / "google-chrome").mkdir()

	assert mod.default_user_data_dir(tmp_path / "chrome") == tmp_path / "google-chrome"
	assert mod.default_user_data_dir(tmp_path / "msedge.exe") == tmp_path / "microsoft-edge"


def test_cli_login_mode_passes_window_options(tmp_path, monkeypatch) -> None:
	import script.extract_phpsessid as mod

	fake_browser = tmp_path / "chrome.exe"
	fake_browser.write_text("", encoding="utf-8")
	monkeypatch.setattr(mod, "find_browser", lambda browser: fake_browser)
	default_start_url = mod.login_and_capture.__kwdefaults__["start_url"]
	captured: dict = {}

	def fake_login(browser_path, **kwargs):
		captured.update(kwargs)
		return ["111111_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]

	monkeypatch.setattr(mod, "login_and_capture", fake_login)

	assert main(["--login"]) == 0
	assert captured["incognito"] is True
	assert captured["profile_dir"] is None
	assert captured["isolated"] is False
	assert default_start_url == mod.PIXIV_HOME_URL == "https://www.pixiv.net/"

	captured.clear()
	assert (
		main(
			[
				"--login",
				"--profile-dir",
				str(tmp_path / "cfg"),
				"--no-incognito",
				"--isolated",
			]
		)
		== 0
	)
	assert captured["profile_dir"] == tmp_path / "cfg"
	assert captured["incognito"] is False
	assert captured["isolated"] is True


def test_login_and_capture_hints_to_close_running_browser(tmp_path, monkeypatch) -> None:
	import pytest
	import script.extract_phpsessid as mod

	monkeypatch.setattr(mod, "default_user_data_dir", lambda browser: tmp_path)

	def boom(*args, **kwargs):
		raise mod.BrowserStartupError("浏览器已关闭，登录已取消")

	monkeypatch.setattr(mod, "_capture_once", boom)
	browser = tmp_path / "chrome.exe"

	with pytest.raises(RuntimeError) as info:
		mod.login_and_capture(browser)
	assert "--isolated" in str(info.value)
	assert "独占启动" in str(info.value)

	# isolated 模式不追加提示，保持原始错误
	with pytest.raises(RuntimeError) as isolated_info:
		mod.login_and_capture(browser, isolated=True)
	assert "--isolated" not in str(isolated_info.value)


def test_login_and_capture_keeps_plain_login_timeout(tmp_path, monkeypatch) -> None:
	"""用户自己超时不算配置目录被占用，不该追加「先退出浏览器」的提示。"""
	import pytest
	import script.extract_phpsessid as mod

	monkeypatch.setattr(mod, "default_user_data_dir", lambda browser: tmp_path)

	def timeout(*args, **kwargs):
		raise TimeoutError("等待 Pixiv 登录超时（300 秒）")

	monkeypatch.setattr(mod, "_capture_once", timeout)

	with pytest.raises(TimeoutError) as info:
		mod.login_and_capture(tmp_path / "chrome.exe")
	assert "--isolated" not in str(info.value)


def test_default_profile_link_shares_data_and_is_removed(tmp_path, monkeypatch) -> None:
	"""默认配置目录通过临时联接共享同一份数据，退出后只删联接本身。"""
	import script.extract_phpsessid as mod

	monkeypatch.setattr(mod, "default_user_data_dir", lambda browser: tmp_path)
	(tmp_path / "Local State").write_text("{}", encoding="utf-8")

	with mod._default_profile_link(tmp_path / "chrome.exe") as link:
		assert link != tmp_path
		assert (link / "Local State").is_file()
		(link / "from-link.txt").write_text("hi", encoding="utf-8")

	assert (tmp_path / "from-link.txt").read_text(encoding="utf-8") == "hi"
	assert not link.exists()


def test_login_and_capture_uses_linked_default_profile(tmp_path, monkeypatch) -> None:
	import script.extract_phpsessid as mod

	(tmp_path / "Local State").write_text("{}", encoding="utf-8")
	monkeypatch.setattr(mod, "default_user_data_dir", lambda browser: tmp_path)
	seen: list = []

	def fake_capture(browser_path, profile_dir, **kwargs):
		seen.append(profile_dir)
		assert (profile_dir / "Local State").is_file()
		return "111111_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

	monkeypatch.setattr(mod, "_capture_once", fake_capture)

	values = mod.login_and_capture(tmp_path / "chrome.exe")
	assert values == ["111111_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]
	assert seen
	assert seen[0] != tmp_path
	assert not seen[0].exists()


def test_merge_phpsessids_keeps_existing_order(tmp_path) -> None:
	from script.extract_phpsessid import merge_phpsessids, read_existing_phpsessids

	assert read_existing_phpsessids(tmp_path / "missing.env") == []

	old = "119908520_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	new = "220011220_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	assert merge_phpsessids([old], [new, old]) == [old, new]


def test_cli_output_appends_to_existing_file(tmp_path, capsys) -> None:
	old = "119908520_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	new = "220011220_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	out = tmp_path / "pixiv.env"
	out.write_text(f'PIXIV_COOKIE="{old}"\n', encoding="utf-8")
	src = tmp_path / "raw.txt"
	src.write_text(f"PHPSESSID={new}\n", encoding="utf-8")

	assert main([str(src), "--format", "env", "-o", str(out)]) == 0
	assert out.read_text(encoding="utf-8") == f'PIXIV_COOKIE="{old}\n{new}"\n'
	err = capsys.readouterr().err
	assert "已有的 1 个" in err
	assert "新增 1 个" in err

	# 反复运行不会重复追加
	assert main([str(src), "--format", "env", "-o", str(out)]) == 0
	assert out.read_text(encoding="utf-8") == f'PIXIV_COOKIE="{old}\n{new}"\n'
	assert "新增 0 个" in capsys.readouterr().err


def test_read_existing_phpsessids_supports_all_shapes(tmp_path) -> None:
	from script.extract_phpsessid import read_existing_phpsessids

	a = "119908520_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	b = "220011220_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

	single = tmp_path / "single.env"
	single.write_text(f"PIXIV_COOKIE={a}\n", encoding="utf-8")
	assert read_existing_phpsessids(single) == [a]

	multi = tmp_path / "multi.env"
	multi.write_text(f'PIXIV_COOKIE="{a}\n{b}"\n', encoding="utf-8")
	assert read_existing_phpsessids(multi) == [a, b]

	kv = tmp_path / "kv.txt"
	kv.write_text(f"PHPSESSID={a}\nPHPSESSID={b}\n", encoding="utf-8")
	assert read_existing_phpsessids(kv) == [a, b]

	raw = tmp_path / "raw.txt"
	raw.write_text(f"other_cookie=999999999_zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz\n{a}\n", encoding="utf-8")
	assert read_existing_phpsessids(raw) == [a]


def test_cli_output_appends_single_account_env(tmp_path) -> None:
	"""单账号时输出的是无引号的 ``PIXIV_COOKIE=裸值``，第二次运行也要能读回来合并。"""
	old = "119908520_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	new = "220011220_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	out = tmp_path / "pixiv.env"
	out.write_text(f"PIXIV_COOKIE={old}\n", encoding="utf-8")
	src = tmp_path / "raw.txt"
	src.write_text(f"PHPSESSID={new}\n", encoding="utf-8")

	assert main([str(src), "--format", "env", "-o", str(out)]) == 0
	assert out.read_text(encoding="utf-8") == f'PIXIV_COOKIE="{old}\n{new}"\n'


def test_cli_output_merges_across_formats(tmp_path) -> None:
	old = "119908520_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	new = "220011220_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	out = tmp_path / "cookies.txt"
	out.write_text(f"{old}\n", encoding="utf-8")
	src = tmp_path / "raw.txt"
	src.write_text(f"PHPSESSID={new}\n", encoding="utf-8")

	# 旧文件是裸值格式，本次要求 kv：合并后整体按 kv 重写
	assert main([str(src), "--format", "kv", "-o", str(out)]) == 0
	assert out.read_text(encoding="utf-8") == f"PHPSESSID={old}\nPHPSESSID={new}\n"


def test_cli_output_overwrites_file_without_tokens(tmp_path) -> None:
	new = "220011220_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	out = tmp_path / "other.env"
	out.write_text("SOMETHING_ELSE=1\n", encoding="utf-8")
	src = tmp_path / "raw.txt"
	src.write_text(f"PHPSESSID={new}\n", encoding="utf-8")

	assert main([str(src), "-o", str(out)]) == 0
	assert out.read_text(encoding="utf-8") == f"{new}\n"
