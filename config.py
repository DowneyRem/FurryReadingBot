# config.py
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

FURRY_READING = os.environ.get("FURRY_READING", "").strip()
FURRY_NOVELS = os.environ.get("FURRY_NOVELS", "").strip()
TEST_CHANNEL = os.environ.get("TEST_CHANNEL", "").strip()
# 中转频道：存放待核验的申请作品。未配置 TRANSIT_CHANNEL 时暂时复用测试频道
TRANSIT_CHANNEL = os.environ.get("TRANSIT_CHANNEL", "").strip() or TEST_CHANNEL

FURRY_READING_NEW_GROUP = os.environ.get("FURRY_READING_NEW_GROUP", "").strip()
TEST_GROUP = os.environ.get("TEST_GROUP", "").strip()


# 分享模式：test 只发测试频道；prod 按评分分流到正式频道
SHARE_MODE = os.environ.get("SHARE_MODE", "test").strip().lower() or "test"
# prod 模式下，评分达到该值的作品同时发到兽人阅读和兽人小说；否则只发兽人小说
SHARE_SCORE_THRESHOLD = float(os.environ.get("SHARE_SCORE_THRESHOLD", 7))

# 分享冷却：同一部作品在该时间（天）内不会重复发送到频道
SHARE_COOLDOWN_DAYS = float(os.environ.get("SHARE_COOLDOWN_DAYS", 3))
# 文件缓存天数：file_id 在该时间内可直接复用，不再重新上传
FILE_CACHE_TTL_DAYS = float(os.environ.get("FILE_CACHE_TTL_DAYS", 7))