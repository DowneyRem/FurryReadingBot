# config.py
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
# P 站小说不能只取公开内容：登录态是启动必填项（见 config_errors()）
PIXIV_COOKIE = os.environ.get("PIXIV_COOKIE", "").strip()


# Telegram 频道
FURRY_READING = os.environ.get("FURRY_READING", "").strip()
FURRY_NOVELS = os.environ.get("FURRY_NOVELS", "").strip()
TEST_CHANNEL = os.environ.get("TEST_CHANNEL", "").strip()
TRANSIT_CHANNEL = os.environ.get("TRANSIT_CHANNEL", "").strip()
if not TRANSIT_CHANNEL:
	TRANSIT_CHANNEL = TEST_CHANNEL

# Telegram 群组：分享时同时发这里（prod 用 FURRY_READING_NEW_GROUP，test 用 TEST_GROUP）
FURRY_READING_NEW_GROUP = os.environ.get("FURRY_READING_NEW_GROUP", "").strip()
TEST_GROUP = os.environ.get("TEST_GROUP", "").strip()


# 分享模式：test 只发测试频道；prod 按评分分流到正式频道
SHARE_MODES = ("test", "prod")
SHARE_MODE = "prod"
# prod 模式下，评分达到该值的作品同时发到兽人阅读和兽人小说；否则只发兽人小说
SHARE_SCORE_THRESHOLD = 6.5


# update 并发数：1 = 串行处理；越高越容易撞 Telegram 限流，也会把磁盘和线程池打满。
CONCURRENT_UPDATES = 8


# 时间参数：storage 里的 TTL / 冷却 / 有效期 -----
# 按一次使用流程的先后顺序排列：抓来源 → 下载产物 → 分享 → 分享记录保留 → 下架申请 → 申请冷却 → 申请记录保留
# ① 抓来源：同一链接的 JSON 响应缓存多久；预检 / 解析系列 / 打包共用同一份
FETCH_CACHE_TTL_HOURS = 24
# ② 下载产物：file_id 在该时间（天）内可直接复用，不再重新上传
FILE_CACHE_TTL_DAYS = 3
# ③ 分享：同一部作品在该时间（天）内不会重复发送到频道
SHARE_COOLDOWN_DAYS = 3
# ④ 分享记录：频道消息保留多久；下架核验通过后按记录回溯删除
SHARE_RECORD_TTL_DAYS = 365 * 2
# ⑤ 下架申请：点「申请下架」后必须在该时间（分钟）内提交后台截图，过期作废
BLACK_REQUEST_MATERIAL_TTL_MINUTES = 30
# ⑥ 申请冷却：同一作者在该时间（小时）内只能申请一次（兽人名单 / 黑名单共用）
#    兽人名单按「提交申请」算；黑名单按「提交截图送审」算（受理后 30 分钟没交截图会作废，不该再等一天）
APPLY_COOLDOWN_HOURS = 24
# ⑦ 申请记录保留：已结束（通过 / 拒绝）的申请在该时间（天）后淘汰
#    还在流程里的申请（pending / pending_material / pending_review）不按 TTL 淘汰：
#    等审核的不能凭空消失，等截图的过期后要被下一位申请人接手（见 storage/black_request.py）
FURRY_REQUEST_TTL_DAYS = 90
# 拉黑记录本身就是「作者本人申请下架」的凭据，比被拒的兽人作者申请留得更久
BLACK_REQUEST_TTL_DAYS = 365


def config_errors() -> list[str]:
	"""启动前检查配置，返回问题列表；为空表示可以启动。"""
	errors: list[str] = []
	if not BOT_TOKEN:
		errors.append("BOT_TOKEN 未配置")
	if not PIXIV_COOKIE:
		errors.append("PIXIV_COOKIE 未配置")
	
	if SHARE_MODE not in SHARE_MODES:
		errors.append(f"SHARE_MODE 只能是 {' / '.join(SHARE_MODES)}，当前为 {SHARE_MODE!r}")
	required = {"test": ("TEST_CHANNEL",), "prod": ("FURRY_NOVELS", "FURRY_READING", "TRANSIT_CHANNEL")}
	for name in required.get(SHARE_MODE, ()):
		if not globals()[name]:
			errors.append(f"SHARE_MODE={SHARE_MODE} 时必须配置 {name}")
	return errors
