from pathlib import Path
from typing import Any

import requests
from storage.file import read_json, save_json
# from storage.file_async import read_json, save_json
from storage.list import ListManager


def download_json(url: str, file_name: str) -> Any:
	"""下载 JSON 并可选保存到本地"""
	response = requests.get(url, timeout=15)
	response.raise_for_status()
	data = response.json()
	save_path = Path(__file__).parent.resolve() / file_name
	save_json(data, save_path)
	return data


def import_linpx_authors() -> None:
	path = Path(__file__).parent.resolve() / "linpx.json"
	data = read_json(path)
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


def import_linpx_authors_online() -> None:
	response = requests.get("https://api.linpx.ink/fav/user/cache", timeout=15)
	response.raise_for_status()
	data = response.json()
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


if __name__ == "__main__":
	# download_json("https://api.linpx.ink/fav/user/cache", "linpx.json")
	# import_linpx_authors()
	# 或者直接在线导入：
	import_linpx_authors_online()