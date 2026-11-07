# sources/linpx/errors.py
from __future__ import annotations


class LinpxError(Exception):
	"""Linpx 源相关错误的基类。上层可统一 catch。"""

	def __init__(self, message: str = "", *, raw: object | None = None):
		self.raw = raw  # 可选：保留接口原始返回，便于调试
		super().__init__(message or self.__class__.__doc__ or "Linpx 错误")


class LinpxNotFoundError(LinpxError):
	"""服务器有响应，但没有该作品数据（如 error: true、空对象）。"""


class LinpxParseError(LinpxError):
	"""链接/文本无法解析出有效 ID。"""


class LinpxNetworkError(LinpxError):
	"""请求失败、超时、非 JSON 等网络/传输问题。"""