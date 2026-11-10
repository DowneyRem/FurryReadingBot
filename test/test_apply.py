"""handlers.callbacks.apply：callback_data 解析、申请文案。

运行（在项目根目录）:
	python -m pytest test/test_apply.py -v
"""

from __future__ import annotations

from handlers.callbacks.apply import apply_notice, guess_kind, parse_apply_data


def test_parse_apply_data() -> None:
	link, author_id = parse_apply_data(
		"af;https://linpx.ink/pixiv/novel/29577253;119908520")
	assert link == "https://linpx.ink/pixiv/novel/29577253"
	assert author_id == "119908520"

	link, author_id = parse_apply_data("afy;https://api.linpx.ink/pixiv/series/16181401;100259032")
	assert link == "https://api.linpx.ink/pixiv/series/16181401"
	assert author_id == "100259032"


def test_parse_apply_data_incomplete() -> None:
	assert parse_apply_data("af") == ("", "")
	assert parse_apply_data("afy;仅链接") == ("仅链接", "")


def test_parse_apply_data_keeps_url_colons() -> None:
	"""callback_data 用 ';' 分隔，URL 里的 ':' '//' '?' 都不能被拆坏。"""
	link, author_id = parse_apply_data("af;https://linpx.ink/pn/18012577?id=1;42")
	assert link == "https://linpx.ink/pn/18012577?id=1"
	assert author_id == "42"


def test_guess_kind() -> None:
	assert guess_kind("https://linpx.ink/pixiv/novel/1") == "novel"
	assert guess_kind("https://linpx.ink/pn/1") == "novel"
	assert guess_kind("https://api.linpx.ink/pixiv/series/1") == "series"
	assert guess_kind("https://linpx.ink/pixiv/user/1") == "author"
	assert guess_kind("https://linpx.ink/pu/1") == "author"
	assert guess_kind("") == ""


def test_apply_notice() -> None:
	text = apply_notice("某作者", "123")
	assert "某作者" in text
	assert "123" in text
	# 必须明确告知后果：可能被分享、可投诉下架、需人工核验
	assert "分享" in text
	assert "下架" in text
	assert "核验" in text
	assert "确认发起申请吗" in text


if __name__ == "__main__":
	print("请使用 pytest 运行：python -m pytest test/test_apply.py -v")
