"""keyboards.down_series_keyboard：系列卡片的 3 + 3 布局与「📄 下载首章」。

运行（在项目根目录）:
	.venv\\Scripts\\python.exe -m pytest test/test_series_keyboard.py -q
"""

from __future__ import annotations

from keyboards import down_series_keyboard


SERIES_URL = "https://www.pixiv.net/novel/series/16747997"


def callbacks(markup) -> list[list[str]]:
	"""按行返回 callback_data，方便直接断言按钮布局。"""
	return [
		[button.callback_data for button in row]
		for row in markup.inline_keyboard
	]


def test_series_keyboard_has_six_buttons() -> None:
	"""系列卡片凑满 6 个按钮，排成 3 + 3。"""
	rows = callbacks(down_series_keyboard(SERIES_URL))

	assert [len(row) for row in rows] == [3, 3]
	assert rows[0] == [f"dst;{SERIES_URL}", f"dsz;{SERIES_URL}", f"ds;{SERIES_URL}"]
	assert rows[1] == [f"dn;{SERIES_URL}", f"ba;{SERIES_URL}", "ignore"]


def test_format_choice_keyboard_has_five_buttons() -> None:
	"""格式选择卡片（auto=False）只留格式按钮：没有「自动选择」和「下载首章」。"""
	rows = callbacks(down_series_keyboard(SERIES_URL, auto=False))

	assert [len(row) for row in rows] == [2, 2]
	flat = [data for row in rows for data in row]
	assert not any(data.startswith(("ds;", "dn;")) for data in flat)
	assert f"ba;{SERIES_URL}" in flat


def test_callbacks_fit_telegram_limit() -> None:
	"""callback_data 必须 ≤ 64 字节：Pixiv 系列链接是最长的一种。"""
	rows = callbacks(down_series_keyboard(SERIES_URL))
	too_long = [
		data for row in rows for data in row if len(data.encode("utf-8")) > 64
	]

	assert too_long == []


if __name__ == "__main__":
	print("请使用 pytest 运行：python -m pytest test/test_series_keyboard.py -q")
