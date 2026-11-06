import asyncio
from pathlib import Path
from typing import Any

from storage.file_async import get_json, download_json, read_json
from storage.list import ListManager
from sources.linpx.urls import url_fav_user_data
from sources.linpx.config import HEADERS


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
	data = await get_json(url=url_fav_user_data(), headers=HEADERS)
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
	# await download_json(url_fav_user_data(), "linpx.json", headers = HEADERS)
	# await import_linpx_authors()


if __name__ == "__main__":
    asyncio.run(main())