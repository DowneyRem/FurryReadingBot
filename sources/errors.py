"""来源层公共错误：接入层只按 `SourceError` 兜底，具体来源各自派生。

`sources/linpx/errors.py`、`sources/pixiv/errors.py` 的基类都继承这里，
所以 `handlers/` 不必认识每个来源的错误类型：

	except SourceError as e:
		await message.reply_text(str(e))

派生的错误消息直接面向用户，`raw` 保留接口原始返回用于排查。
"""

from __future__ import annotations


class SourceError(Exception):
	"""所有来源错误的基类。"""

	def __init__(self, message: str = "", *, raw: object | None = None):
		self.raw = raw
		super().__init__(message or self.__class__.__doc__ or "来源错误")
