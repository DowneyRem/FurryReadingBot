from telegram import Update
from telegram.ext import ContextTypes

from config import FURRY_READING


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	text = [
		f"你好，我是 {FURRY_READING} 的小说分享投稿 Bot",
		f"向我发送 Pixiv / Linpx 小说、系列或作者链接即可下载",
		f"查看命令可用 /help"
	]
	await update.message.reply_text("\n".join(text))


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	text = [
		"/start 开始",
		"/help 查看命令",
		# "/ping 查看 uid 和语言",
		"/sponsor 众筹 & 代码开源",
		"/down 下载并分享",
		"/black 申请下架（主页链接）",
		"/furry 申请兽人作者（主页链接）",
		"",
		"/sync 仅管理：同步运营数据",
		"/review 仅管理：推送待审核申请",
		"/blackadd 仅管理：添加下架作者（主页链接）",
		"/furryadd 仅管理：添加兽人作者（主页链接）",
	]
	await update.message.reply_text("\n".join(text))


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
