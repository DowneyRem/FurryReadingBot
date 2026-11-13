"""keyboards.py 产出的 action 必须能被 router 接住。

防止「改了键盘 callback_data 却忘了改 router / 忘了登记」这类漂移；
顺带守一下 Telegram 的 callback_data ≤ 64 字节限制。

运行（在项目根目录）:
	.venv\\Scripts\\python.exe -m pytest test/test_keyboard_routing.py -q
"""

from __future__ import annotations

from handlers.callbacks.router import CANCEL_ACTIONS, HANDLERS
from keyboards import (
	apply_author_keyboard,
	confirm_black_keyboard,
	confirm_furry_keyboard,
	down_author_keyboard,
	down_novel_keyboard,
	down_novel_series_keyboard,
	down_series_keyboard,
	import_to_legado_keyboard,
	review_black_keyboard,
	review_furry_keyboard,
	share_novel_keyboard,
)


AUTHOR_URL = "https://linpx.ink/pixiv/user/42"
NOVEL_URL = "https://linpx.ink/pixiv/novel/7"


def all_keyboards() -> list:
	"""当前真正会发出去的键盘（`check_novel_keyboard` 是 0 引用死代码，不计入）。"""
	return [
		apply_author_keyboard(AUTHOR_URL),
		confirm_furry_keyboard("42"),
		confirm_black_keyboard("42"),
		review_furry_keyboard("42"),
		review_black_keyboard("42"),
		down_novel_keyboard(NOVEL_URL),
		down_novel_series_keyboard(NOVEL_URL),
		down_series_keyboard(NOVEL_URL),
		down_author_keyboard(AUTHOR_URL),
		share_novel_keyboard("novel", "7"),
		import_to_legado_keyboard(NOVEL_URL),
	]


def all_callback_data() -> list[str]:
	data: list[str] = []
	for markup in all_keyboards():
		for row in markup.inline_keyboard:
			for button in row:
				if button.callback_data:
					data.append(button.callback_data)
	return data


def test_every_keyboard_action_is_routable() -> None:
	actions = {item.partition(";")[0] for item in all_callback_data()}
	unrouted = actions - set(HANDLERS) - CANCEL_ACTIONS
	assert unrouted == set(), f"这些 action 没有注册到 router：{sorted(unrouted)}"


def test_callback_data_fits_telegram_limit() -> None:
	too_long = [
		item for item in all_callback_data()
		if len(item.encode("utf-8")) > 64
	]
	assert too_long == []


def test_review_actions_use_r_prefix() -> None:
	actions = {item.partition(";")[0] for item in all_callback_data()}
	assert {"rfy", "rfn", "rby", "rbn"} <= actions
	assert not {"afa", "afr", "ablock", "abdeny"} & actions


def test_import_keyboard_carries_work_link() -> None:
	"""「添加本文至书架」按钮必须把作品链接拼进 legado 深链。"""
	markup = import_to_legado_keyboard(NOVEL_URL)
	urls = [button.url for row in markup.inline_keyboard for button in row if button.url]

	assert any("legado://import/addToBookshelf" in url for url in urls)
	assert any(NOVEL_URL in url for url in urls)
