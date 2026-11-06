import asyncio
from pathlib import Path
from typing import Any

import aiohttp
from storage.file_async import read_json, save_json   # 异步版本
from storage.list import ListManager


async def download_json(url: str, file_name: str) -> Any:
    """异步下载 JSON 并保存到本地"""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=15) as response:
            response.raise_for_status()
            data = await response.json()

    save_path = Path(__file__).parent.resolve() / file_name
    await save_json(save_path, data)          # 注意：保持和你原来一样的参数顺序
    return data


async def import_linpx_authors() -> None:
    path = Path(__file__).parent.resolve() / "linpx.json"
    data = await read_json(path)
    print(f"共获取 {len(data)} 个推荐作者")

    li = []
    mgr = ListManager()
    for item in data:
        author_id = item["id"]
        name = item["name"]
        if not mgr.is_furryauthor(author_id):
            li.append(author_id)
            print(f"{author_id}: {name}")
            mgr.add_furrylist(author_id=author_id, name=name, note="Linpx")
    print(f"共新增 {len(li)} 个推荐作者")


async def import_linpx_authors_online() -> None:
    async with aiohttp.ClientSession() as session:
        async with session.get("https://api.linpx.ink/fav/user/cache", timeout=15) as response:
            response.raise_for_status()
            data = await response.json()
    print(f"共获取 {len(data)} 个推荐作者")

    li = []
    mgr = ListManager()
    for item in data:
        author_id = item["id"]
        name = item["name"]
        if not mgr.is_furryauthor(author_id):
            li.append(author_id)
            print(f"{author_id}: {name}")
            mgr.add_furrylist(author_id=author_id, name=name, note="Linpx")
    print(f"共新增 {len(li)} 个推荐作者")


async def main():
    # await download_json("https://api.linpx.ink/fav/user/cache", "linpx.json")
    # await import_linpx_authors()
    # 或者直接在线导入：
    await import_linpx_authors_online()


if __name__ == "__main__":
    asyncio.run(main())