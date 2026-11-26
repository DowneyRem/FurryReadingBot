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
