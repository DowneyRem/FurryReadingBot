from pathlib import Path

from storage.file import download_json, read_json, save_json, get_json
from storage.list import ListManager


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
	# download_json(url_fav_user_data(), "linpx.json", headers = HEADERS)
	# import_linpx_authors()
	# 或者直接在线导入：
	import_linpx_authors_online()