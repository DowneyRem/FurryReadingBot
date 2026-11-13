# config.py
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

FURRY_READING = os.environ.get("FURRY_READING", "").strip()
FURRY_NOVELS = os.environ.get("FURRY_NOVELS", "").strip()
TEST_CHANNEL = os.environ.get("TEST_CHANNEL", "").strip()

FURRY_READING_NEW_GROUP = os.environ.get("FURRY_READING_NEW_GROUP", "").strip()
TEST_GROUP = os.environ.get("TEST_GROUP", "").strip()


# 分享模式：test 只发测试频道；prod 按评分分流到正式频道
SHARE_MODES = ("test", "prod")
SHARE_MODE = os.environ.get("SHARE_MODE", "test").strip().lower() or "test"

# 中转频道：存放待核验的申请作品。test 模式未配置时复用测试频道，prod 必须单独配置
TRANSIT_CHANNEL = (
	os.environ.get("TRANSIT_CHANNEL", "").strip()
	or (TEST_CHANNEL if SHARE_MODE == "test" else "")
)
# prod 模式下，评分达到该值的作品同时发到兽人阅读和兽人小说；否则只发兽人小说
SHARE_SCORE_THRESHOLD = float(os.environ.get("SHARE_SCORE_THRESHOLD", 7))

# 分享冷却：同一部作品在该时间（天）内不会重复发送到频道
SHARE_COOLDOWN_DAYS = float(os.environ.get("SHARE_COOLDOWN_DAYS", 3))
# 文件缓存天数：file_id 在该时间内可直接复用，不再重新上传
FILE_CACHE_TTL_DAYS = float(os.environ.get("FILE_CACHE_TTL_DAYS", 7))

# update 并发数：1 = 串行处理；越高越容易撞 Telegram 限流，也会把磁盘和线程池打满。
# 注意 python-telegram-bot 的 concurrent_updates(True) 是 256，不适合本 Bot。
CONCURRENT_UPDATES = max(1, int(os.environ.get("CONCURRENT_UPDATES", "8") or 8))


def config_errors() -> list[str]:
	"""启动前检查必需配置，返回问题列表；为空表示可以启动。"""
	errors: list[str] = []
	if not BOT_TOKEN:
		errors.append("BOT_TOKEN 未配置")
	if SHARE_MODE not in SHARE_MODES:
		errors.append(f"SHARE_MODE 只能是 {' / '.join(SHARE_MODES)}，当前为 {SHARE_MODE!r}")
	required = {"test": ("TEST_CHANNEL",), "prod": ("FURRY_NOVELS", "FURRY_READING", "TRANSIT_CHANNEL")}
	for name in required.get(SHARE_MODE, ()):
		if not globals()[name]:
			errors.append(f"SHARE_MODE={SHARE_MODE} 时必须配置 {name}")
	return errors
