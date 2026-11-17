from storage.author_list import ListManager


def test_add_and_contains(tmp_path) -> None:
	mgr = ListManager(tmp_path)
	assert not mgr.is_whitelisted("1")
	mgr.add_whitelist("1", name="A", note="ok")
	assert mgr.is_whitelisted("1")
	assert mgr.whitelist.get("1")["name"] == "A"


def test_persist_across_instances(tmp_path) -> None:
	mgr1 = ListManager(tmp_path)
	mgr1.add_blacklist("99", name="bad")
	mgr2 = ListManager(tmp_path)
	assert mgr2.is_blacklisted("99")


def test_whitelist_removes_from_blacklist(tmp_path) -> None:
	mgr = ListManager(tmp_path)
	mgr.add_blacklist("7")
	mgr.add_whitelist("7", name="now_good")
	assert mgr.is_whitelisted("7")
	assert not mgr.is_blacklisted("7")


def test_remove(tmp_path) -> None:
	mgr = ListManager(tmp_path)
	mgr.add_whitelist("3")
	assert mgr.remove_whitelist("3") is True
	assert not mgr.is_whitelisted("3")
	assert mgr.remove_whitelist("3") is False


def test_add_many_writes_once_and_skips_known(tmp_path) -> None:
	"""批量导入：已存在的 key 不覆盖，整批只落盘一次。"""
	mgr = ListManager(tmp_path)
	mgr.add_furrylist("1", name="旧名", note="兽人阅读")
	writes: list[int] = []
	persist = mgr.furrylist._persist

	def counting_persist():
		writes.append(1)
		persist()

	mgr.furrylist._persist = counting_persist

	added = mgr.furrylist.add_many([
		("1", "旧名", "Linpx"),
		("2", "乙", "Linpx"),
		("3", "丙", "Linpx"),
	])

	assert added == 2
	assert len(writes) == 1
	assert mgr.furrylist.get("1")["note"] == "兽人阅读"
	assert mgr.furrylist.get("2")["name"] == "乙"


def test_add_many_without_new_records_does_not_write(tmp_path) -> None:
	mgr = ListManager(tmp_path)
	mgr.add_furrylist("1", name="甲", note="Linpx")
	writes: list[int] = []
	persist = mgr.furrylist._persist

	def counting_persist():
		writes.append(1)
		persist()

	mgr.furrylist._persist = counting_persist

	assert mgr.furrylist.add_many([("1", "甲", "Linpx")]) == 0
	assert writes == []


if __name__ == "__main__":
	import tempfile
	from pathlib import Path

	tmp = Path(tempfile.mkdtemp())
	test_add_and_contains(tmp)
	test_persist_across_instances(tmp)
	test_whitelist_removes_from_blacklist(tmp)
	test_remove(tmp)
	test_add_many_writes_once_and_skips_known(tmp)
	test_add_many_without_new_records_does_not_write(tmp)
