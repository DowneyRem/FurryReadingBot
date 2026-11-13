"""bot.py 装配：并发有界 + `post_shutdown` 通过 builder 注册。

v20+ 的 `Application.post_shutdown` 是**构造属性**而不是 setter，
写成 `app.post_shutdown(cb)` 会静默失败（`None` 不可调用），这里守住这个坑。

运行（在项目根目录）:
	python -m pytest test/test_bot_wiring.py -q
"""

from __future__ import annotations

import asyncio

from telegram.ext import Application

import bot
from config import CONCURRENT_UPDATES


def make_app() -> Application:
	"""和 bot.main() 一样的装配方式（只是换成假 Token，不联网）。"""
	return (
		Application.builder()
		.token("123456:AAFakeTokenForWiringTest")
		.concurrent_updates(CONCURRENT_UPDATES)
		.post_shutdown(bot.post_shutdown)
		.build()
	)


def test_concurrent_updates_is_bounded() -> None:
	assert CONCURRENT_UPDATES >= 1
	assert make_app().update_processor.max_concurrent_updates == CONCURRENT_UPDATES


def test_post_shutdown_is_registered() -> None:
	app = make_app()

	assert app.post_shutdown is not None
	# 没有活跃会话时应安全空跑（close_http 按事件循环取会话）
	asyncio.run(app.post_shutdown(app))
