from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from config import FURRY_READING
from handlers.telegram import transit_admin_policy


USER_COMMANDS = (
	"/start 开始",
	"/help 查看命令",
	# "/ping 查看 uid 和语言",
	"/sponsor 众筹 & 代码开源",
	"/down 下载并分享",
	"/black 申请下架（主页链接）",
	"/furry 申请兽人作者（主页链接）",
)
ADMIN_COMMANDS = (
	"以下功能仅管理可用：",
	"/sync 同步运营数据",
	"/review 推送待审核申请",
	"/blackadd 添加黑名单（主页链接）",
	"/furryadd 添加兽人作者（主页链接）",
	"/blackremove 移出黑名单（主页链接）",
	"/furryremove 移出兽人作者（主页链接）",
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	text = [
		f"你好，我是 {FURRY_READING} 的小说分享投稿 Bot",
		f"向我发送 Pixiv / Linpx 小说、系列或作者链接即可下载",
		f"查看命令可用 /help"
	]
	await update.message.reply_text("\n".join(text))


def help_text(*, is_admin: bool) -> str:
	"""帮助文案：非管理员只有公开命令，管理员额外看到管理命令。"""
	lines = list(USER_COMMANDS)
	if is_admin:
		lines += ["", *ADMIN_COMMANDS]
	return "\n".join(lines)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""/help：按中转频道管理员身份决定是否附带管理命令。"""
	message = update.effective_message
	user = update.effective_user
	if message is None:
		return

	is_admin = False
	if user is not None:
		decision = await transit_admin_policy(context.bot).check(user.id)
		is_admin = decision.allowed
	await message.reply_text(help_text(is_admin=is_admin))


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	text = [
		f"chat_id: <code>{update.message.chat.id}</code>",
		f"language: <code>{update.message.from_user.language_code}</code>",
	]
	await update.message.reply_text(text="\n".join(text), parse_mode="HTML")


async def sponsor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	text = [
		"💖 Github Sponsor：", "https://github.com/DowneyRem/FurryReadingBot",
		"💜 爱发电众筹：", "https://afdian.com/a/DowneyRem",
	]
	await update.message.reply_text("\n".join(text))
