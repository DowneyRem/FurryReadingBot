# config.py
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
FURRY_READING = os.environ.get("FURRY_READING", "").strip()
FURRY_NOVELS = os.environ.get("FURRY_NOVELS", "").strip()

FURRY_READING_NEW_GROUP = os.environ.get("FURRY_READING_NEW_GROUP", "").strip()
TEST_CHANNEL = os.environ.get("TEST_CHANNEL", "").strip()
TEST_GROUP = os.environ.get("TEST_GROUP", "").strip()

