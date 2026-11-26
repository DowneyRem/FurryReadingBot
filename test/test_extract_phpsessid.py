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


def test_read_devtools_endpoint_and_browser_lookup(tmp_path, monkeypatch) -> None:
	from script.extract_phpsessid import find_browser, read_devtools_endpoint

	assert read_devtools_endpoint(tmp_path) is None
	(tmp_path / "DevToolsActivePort").write_text("14338\n/devtools/browser/abc\n", encoding="utf-8")
	assert read_devtools_endpoint(tmp_path) == (14338, "/devtools/browser/abc")

	fake_chrome = tmp_path / "chrome.exe"
	fake_chrome.write_text("", encoding="utf-8")
	monkeypatch.setattr("script.extract_phpsessid._browser_candidates", lambda kind: [fake_chrome] if kind == "chrome" else [])
	assert find_browser("chrome") == fake_chrome


def test_wait_for_login_cookie_via_mock_cdp_ws(tmp_path, monkeypatch) -> None:
	import asyncio
	import script.extract_phpsessid as mod

	(tmp_path / "DevToolsActivePort").write_text("14338\n/devtools/browser/abc\n", encoding="utf-8")

	class FakeProc:
		def poll(self):
			return None

	class FakeWS:
		def __init__(self) -> None:
			self.sent: list[dict] = []
			self.calls = 0

		async def __aenter__(self):
			return self

		async def __aexit__(self, *args):
			return False

		async def send_json(self, payload: dict) -> None:
			self.sent.append(payload)

		async def receive_json(self, timeout=None) -> dict:
			req = self.sent[-1]
			if req["method"] == "Storage.getCookies":
				self.calls += 1
				if self.calls == 1:
					cookies = [{"name": "PHPSESSID", "domain": ".pixiv.net", "value": "guest_no_uid_32chars_000000000000"}]
				else:
					cookies = [{"name": "PHPSESSID", "domain": ".pixiv.net", "value": "119908520_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}]
				return {"id": req["id"], "result": {"cookies": cookies}}
			return {"id": req["id"], "result": {}}

	fake_ws = FakeWS()

	class FakeSession:
		async def __aenter__(self):
			return self

		async def __aexit__(self, *args):
			return False

		def ws_connect(self, url, **kwargs):
			assert url == "ws://127.0.0.1:14338/devtools/browser/abc"
			return fake_ws

	monkeypatch.setattr(mod.aiohttp, "ClientSession", lambda: FakeSession())
	token = asyncio.run(mod._wait_for_login_cookie(FakeProc(), tmp_path, timeout=5.0, poll_interval=0))
	assert token == "119908520_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	assert [item["method"] for item in fake_ws.sent] == [
		"Storage.getCookies",
		"Storage.getCookies",
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

