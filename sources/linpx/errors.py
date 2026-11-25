# sources/linpx/errors.py
from __future__ import annotations

from sources.errors import SourceError


class LinpxError(SourceError):
	"""Linpx 源相关错误的基类。上层可统一 catch。"""


class LinpxNotFoundError(LinpxError):
	"""服务器有响应，但没有该作品数据（如 error: true、空对象）。"""


class LinpxParseError(LinpxError):
	"""链接/文本无法解析出有效 ID。"""


class LinpxNetworkError(LinpxError):
	"""请求失败、超时、非 JSON 等网络/传输问题。"""