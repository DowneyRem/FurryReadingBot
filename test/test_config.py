"""config.py 启动校验：必需项、分享模式与频道组合。

运行（在项目根目录）:
	.venv\\Scripts\\python.exe -m pytest test/test_config.py -q
"""

from __future__ import annotations

import config


def configure(monkeypatch, **values) -> list[str]:
	"""固定一份「能启动」的配置，再按用例覆盖；返回 config_errors()。"""
	base = {
		"BOT_TOKEN": "123456:TEST",
		"PIXIV_COOKIE": "111_aaa",
		"SHARE_MODE": "prod",
		"TEST_CHANNEL": "-1001",
		"TRANSIT_CHANNEL": "-1002",
		"FURRY_READING": "-1003",
		"FURRY_NOVELS": "-1004",
	}
	base.update(values)
	for name, value in base.items():
		monkeypatch.setattr(config, name, value)
	return config.config_errors()


def test_valid_prod_config_has_no_errors(monkeypatch) -> None:
	assert configure(monkeypatch) == []


def test_missing_bot_token_and_cookie_are_both_reported(monkeypatch) -> None:
	errors = configure(monkeypatch, BOT_TOKEN="", PIXIV_COOKIE="")
	assert "BOT_TOKEN 未配置" in errors
	assert "PIXIV_COOKIE 未配置" in errors


def test_pixiv_cookie_is_required(monkeypatch) -> None:
	"""P 站小说不能只取公开内容：Cookie 是启动必需项，缺了直接退出。"""
	assert configure(monkeypatch, PIXIV_COOKIE="") == ["PIXIV_COOKIE 未配置"]


def test_unknown_share_mode_is_rejected(monkeypatch) -> None:
	errors = configure(monkeypatch, SHARE_MODE="staging")
	assert any("SHARE_MODE 只能是" in error for error in errors)


def test_prod_requires_each_channel(monkeypatch) -> None:
	errors = configure(
		monkeypatch, FURRY_READING="", FURRY_NOVELS="", TRANSIT_CHANNEL="")
	assert "SHARE_MODE=prod 时必须配置 FURRY_NOVELS" in errors
	assert "SHARE_MODE=prod 时必须配置 FURRY_READING" in errors
	assert "SHARE_MODE=prod 时必须配置 TRANSIT_CHANNEL" in errors


def test_test_mode_only_needs_test_channel(monkeypatch) -> None:
	assert configure(
		monkeypatch, SHARE_MODE="test", TEST_CHANNEL="-1001") == []
