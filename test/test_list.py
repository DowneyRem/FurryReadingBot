from storage.authors import ListManager


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


if __name__ == "__main__":
	import tempfile
	from pathlib import Path

	tmp = Path(tempfile.mkdtemp())
	test_add_and_contains(tmp)
	test_persist_across_instances(tmp)
	test_whitelist_removes_from_blacklist(tmp)
	test_remove(tmp)
