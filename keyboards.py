# keyboards.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def apply_furry_keyboard(link: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(
				text="✅ 申请加入兽人作者名单",
				callback_data=f"apply_furry_author:{link}"),
			InlineKeyboardButton(
				text="🗑 忽略",
				callback_data=f"ignore"),
		]]
	)

def check_furry_keyboard(link: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(
				text="✅ 确认为兽人小说",
				callback_data=f"is_furry_novel:{link}"),
			InlineKeyboardButton(
				text="🗑 确认非兽人小说",
				callback_data=f"not_furry_novel:{link}"),
		]]
	)


def down_novel_keyboard(link: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(
				text="📄 下载本章为txt文件",
				callback_data=f"down_novel:{link}"),
			InlineKeyboardButton(
				text="👤 下载作者全部小说",
				callback_data=f"down_author:{link}"),
		]]
	)

def down_novel_series_keyboard(link: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(
				text="📄 下载本章为txt文件",
				callback_data=f"down_novel:{link}"),
			InlineKeyboardButton(
				text="👤 下载作者全部小说",
				callback_data=f"down_author:{link}"),
		], [
			InlineKeyboardButton(
				text="📚 下载系列为txt合集",
				callback_data=f"down_series_txt:{link}"),
			InlineKeyboardButton(
				text="📚 下载系列为zip合集",
				callback_data=f"down_series_zip:{link}"),
		]]
	)

def down_series_keyboard(link: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(
				text="📚 下载系列为txt合集",
				callback_data=f"down_series_txt:{link}"),
			InlineKeyboardButton(
				text="📚 下载系列为zip合集",
				callback_data=f"down_series_zip:{link}"),
			InlineKeyboardButton(
				text="▶️ 自动选择",
				callback_data=f"down_series:{link}"),
		]]
	)


def down_author_keyboard(link: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(
				text="👤 全部下载",
				callback_data=f"down_author_novels:{link}"),
			InlineKeyboardButton(
				text="✅ 选择下载",
				callback_data=f"down_author_some:{link}"),
		]]
	)

def import_to_legado_keyboard(link: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(
				text="⬇️ 下载开源阅读",
				url="https://pixivsource.pages.dev/Download"),
			InlineKeyboardButton(
				text="🚀 导入 Pixiv 书源",
				url="https://pixivsource.pages.dev/Import?src=https://cdn.jsdelivr.net/gh/DowneyRem/PixivSource@main/pixiv.json"),
		], [
			InlineKeyboardButton(
				text="➕ 添加本文至书架",
				url=f"https://pixivsource.pages.dev/Import?src=legado://import/addToBookshelf?src={link}"),
		]]
	)