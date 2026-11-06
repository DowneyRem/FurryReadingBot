# keyboards.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def apply_furry_keyboard(link: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(
				text="✅ 申请加入兽人作者名单",
				callback_data=f"apply_furry_author:{link}",
			),
			InlineKeyboardButton(
				text="🗑 忽略",
				callback_data="ignore",
			),
		]]
	)