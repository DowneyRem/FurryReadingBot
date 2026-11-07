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

