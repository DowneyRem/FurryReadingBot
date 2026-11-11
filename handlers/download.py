from telegram import Update
from telegram.ext import ContextTypes

from config import FURRY_NOVELS, FURRY_READING
from keyboards import (
	apply_author_keyboard,
	down_author_keyboard,
	down_novel_keyboard,
	down_novel_series_keyboard,
	down_series_keyboard,
)
from services import (
	DownloadService,
	DownloadInvalidLinkError,
	DownloadUnsupportedLinkError,
)
from sources.linpx.errors import LinpxError


async def download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	message = update.effective_message
	if message is None or not message.text:
		return

	service = DownloadService()
	try:
		offer = await service.inspect_text(message.text)
	except DownloadInvalidLinkError:
		await message.reply_text("请发送一个有效的小说、系列或作者链接。")
		return
	except DownloadUnsupportedLinkError:
		await message.reply_text("暂不支持该链接，请发送 Linpx 小说、系列或作者链接。")
		return
	except LinpxError as e:
		await message.reply_text(f"发生 Linpx 错误\n{e}")
		return
	except Exception as e:
		await message.reply_text(f"发生未知错误\n{e}")
		return

	access = service.check_access(offer)
	if access.status == "blacklisted":
		text = [
			f"不好意思，作者 {access.author_name} 已禁止通过本 Bot 下载小说并分享至 {FURRY_READING} 以及 {FURRY_NOVELS}",
			"如需下载其他 Pixiv 小说，可以使用 @PixivNBot",
		]
		await message.reply_text("\n".join(text))
		return

	if access.status == "needs_apply":
		text = [
			"不好意思，本 Bot 仅可下载兽人小说。",
			f"作者：{access.author_name}（#a{access.author_id}）目前不在兽人小说作者名单", "",
			"申请其为兽人小说作者？",
			"如需下载其他 Pixiv 小说，可以使用 @PixivNBot",
		]
		await message.reply_text(
			text="\n".join(text),
			# 下架入口只在作者主页链接上出现
			reply_markup=apply_author_keyboard(
				offer.author_url, show_blacklist=offer.kind == "author"),
		)
		return

	if offer.kind == "novel":
		if offer.has_series:
			markup = down_novel_series_keyboard(offer.link)
		else:
			markup = down_novel_keyboard(offer.link)
	elif offer.kind == "series":
		markup = down_series_keyboard(offer.link)
	else:
		markup = down_author_keyboard(offer.link)

	await message.reply_text(text=offer.description, reply_markup=markup)
