"""AuthorPolicy：黑名单 / 兽人作者名单的名单判定。

运行（在项目根目录）:
	python -m pytest test/test_author_policy.py -q

产品语义（当前只使用两份名单）:
	- 黑名单：拒绝下载，且禁止申请兽人作者；
	- 兽人作者名单：允许下载；
	- 都不在：拒绝下载，但可以申请兽人作者。
"""

from __future__ import annotations

from policy import AuthorPolicy
from storage.author_list import ListManager


def make_policy(tmp_path, *, black=(), furry=()) -> AuthorPolicy:
	manager = ListManager(data_dir=tmp_path)
	for author_id, name in black:
		manager.add_blacklist(author_id, name=name)
	for author_id, name in furry:
		manager.add_furrylist(author_id, name=name)
	return AuthorPolicy(manager)


def test_blacklisted_denies_download_and_apply(tmp_path) -> None:
	policy = make_policy(tmp_path, black=[("42", "黑名单作者")])

	decision = policy.check("42")

	assert decision.status == "blacklisted"
	assert decision.can_download is False
	assert decision.can_apply is False


def test_furry_allows_download_without_apply(tmp_path) -> None:
	policy = make_policy(tmp_path, furry=[("42", "兽人作者")])

	decision = policy.check("42")

	assert decision.status == "furry"
	assert decision.can_download is True
	assert decision.can_apply is False


def test_unknown_denies_download_but_allows_apply(tmp_path) -> None:
	policy = make_policy(tmp_path)

	decision = policy.check("42")

	assert decision.status == "unknown"
	assert decision.can_download is False
	assert decision.can_apply is True


def test_blacklist_wins_over_furry(tmp_path) -> None:
	manager = ListManager(data_dir=tmp_path)
	manager.add_furrylist("42", name="兽人作者")
	manager.add_blacklist("42", name="黑名单作者")

	decision = AuthorPolicy(manager).check("42")

	assert decision.status == "blacklisted"
	assert decision.can_download is False
	assert decision.can_apply is False


def test_whitelist_is_ignored(tmp_path) -> None:
	"""白名单暂不参与判定：仍然禁止下载，可以申请。"""
	manager = ListManager(data_dir=tmp_path)
	manager.add_whitelist("42", name="白名单作者")

	decision = AuthorPolicy(manager).check("42")

	assert decision.status == "unknown"
	assert decision.can_download is False
	assert decision.can_apply is True


def test_name_prefers_caller_then_list_then_id(tmp_path) -> None:
	policy = make_policy(tmp_path, black=[("42", "名单里的名字")])

	assert policy.check("42", "调用方的名字").author_name == "调用方的名字"
	assert policy.check("42").author_name == "名单里的名字"
	assert policy.check("404").author_name == "404"


def test_reads_lists_at_call_time(tmp_path) -> None:
	policy = make_policy(tmp_path)
	assert policy.check("42").can_download is False

	policy.list_manager.add_furrylist("42", name="后来加入")
	assert policy.check("42").can_download is True

	policy.list_manager.add_blacklist("42", name="再被拉黑")
	assert policy.check("42").status == "blacklisted"
