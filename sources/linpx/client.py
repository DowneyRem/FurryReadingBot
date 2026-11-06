from __future__ import annotations

import aiohttp
from sources.linpx.config import *


async def get_json(url: str) -> dict:
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data


async def get_novel(novel_id: str | int) -> dict:
    url = f"{API_BASE}/pixiv/novel/{novel_id}/cache"
    return await get_json(url)


async def get_series(series_id: str | int) -> dict:
    url = f"{API_BASE}/pixiv/series/{series_id}/cache"
    return await get_json(url)


async def get_user(user_id: str | int) -> dict:
    url = f"{API_BASE}/pixiv/user/{user_id}/cache"
    return await get_json(url)