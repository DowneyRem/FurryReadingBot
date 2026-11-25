"""Pixiv 源错误：上层统一 catch PixivError。"""

from __future__ import annotations


class PixivError(Exception):
	"""Pixiv 源相关错误的基类。"""

	def __init__(self, message: str = "", *, raw: object | None = None):
		self.raw = raw
		super().__init__(message or self.__class__.__doc__ or "Pixiv 错误")


class PixivNotFoundError(PixivError):
	"""Pixiv 有响应，但没有该作品 / 作者 / 系列。"""


class PixivAuthError(PixivError):
	"""Cookie 未配置、失效，或当前账号无权访问。"""


class PixivRateLimitError(PixivError):
	"""请求过于频繁，重试后仍然失败。"""


class PixivNetworkError(PixivError):
	"""超时、连接失败、5xx 等传输问题。"""


class PixivParseError(PixivError):
	"""响应不是合法 JSON，或结构与预期不符。"""


class PixivAPIError(PixivError):
	"""Pixiv 返回 error: true 时的业务错误。"""
