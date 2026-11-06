from __future__ import annotations

from sources.base import Novel, NovelSource
from sources.linpx import LinpxSource

_SOURCES: list[NovelSource] = [
    LinpxSource(),
]


def resolve_source(text: str) -> NovelSource | None:
    for src in _SOURCES:
        if src.can_handle(text):
            return src
    return None


async def fetch_novel(text: str) -> Novel:
    src = resolve_source(text)
    if src is None:
        raise ValueError("无法识别的链接或平台")
    return await src.fetch(text)