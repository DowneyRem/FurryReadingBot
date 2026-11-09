"""Telegram file_id 缓存：按业务 key 存储，支持 TTL，热加载。"""

from __future__ import annotations

import json
import threading
from datetime import timedelta
from pathlib import Path

from storage.utils import parse_iso, utc_now, utc_now_iso
from utils.json import JsonDict


class FileCacheStore:
    """
    统一缓存 4 种下载产物，key 格式：
      novel:{id}:txt
      series:{id}:txt
      series:{id}:zip
      author:{id}:zip
    """
    DEFAULT_TTL_DAYS = 30


    def __init__(self, path: Path | None = None, default_ttl_days: float | None = None) -> None:
        if path is None:
            path = Path(__file__).parent.parent.resolve() / "data" / "files_cache.json"
        self.path = path
        # bot 内由 config.FILE_CACHE_TTL_DAYS 覆盖；0 也是合法值，不能用 or 兜底
        self.default_ttl_days = (
            self.DEFAULT_TTL_DAYS if default_ttl_days is None else default_ttl_days
        )
        self._lock = threading.RLock()
        self._mtime: float = 0.0
        self._files: JsonDict = JsonDict()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write_empty()
        self.reload(force=True)


    def _write_empty(self) -> None:
        payload = JsonDict(updated_at=utc_now_iso(), files=JsonDict())
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=4),
            encoding="utf-8",
        )


    def reload(self, force: bool = False) -> bool:
        with self._lock:
            if not self.path.exists():
                self._write_empty()
                return True
            mtime = self.path.stat().st_mtime
            if not force and mtime == self._mtime:
                return False
            data = JsonDict.from_obj(json.loads(self.path.read_text(encoding="utf-8")))
            raw = data.files or JsonDict()
            files = JsonDict()
            for key, info in raw.items():
                key = str(key)
                if isinstance(info, dict):
                    files[key] = JsonDict(
                        file_id=str(info.get("file_id") or ""),
                        file_name=str(info.get("file_name") or ""),
                        caption=str(info.get("caption") or ""),
                        uploaded_at=str(info.get("uploaded_at") or ""),
                        expires_at=str(info.get("expires_at") or ""),
                    )
            self._files = files
            self._mtime = mtime
            self._prune()
            return True


    def _maybe_reload(self) -> None:
        if self.path.exists() and self.path.stat().st_mtime != self._mtime:
            self.reload(force=True)


    def _persist(self) -> None:
        self._prune()
        payload = JsonDict(
            updated_at=utc_now_iso(),
            files=JsonDict({k: self._files[k] for k in sorted(self._files.keys())}),
        )
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=4),
            encoding="utf-8",
        )
        self._mtime = self.path.stat().st_mtime


    def _prune(self) -> None:
        """丢弃已过期的缓存条目，避免文件无限增长。"""
        now = utc_now()
        expired = [
            key for key, info in self._files.items()
            if (exp := parse_iso(info.expires_at)) is not None and now >= exp
        ]
        for key in expired:
            del self._files[key]


    @staticmethod
    def make_key(kind: str, item_id: str, file_type: str) -> str:
        return f"{kind}:{item_id}:{file_type}"


    def get_valid(self, key: str) -> JsonDict | None:
        self._maybe_reload()
        with self._lock:
            info = self._files.get(str(key))
            if not info or not info.file_id:
                return None
            exp = parse_iso(info.expires_at)
            if exp is not None and utc_now() >= exp:
                del self._files[str(key)]
                self._persist()
                return None
            return info


    def set(
        self,
        key: str,
        file_id: str,
        *,
        file_name: str = "",
        caption: str = "",
    ) -> None:
        if not file_id:
            return
        now = utc_now()
        expires = now + timedelta(days=self.default_ttl_days)
        with self._lock:
            self._maybe_reload()
            self._files[str(key)] = JsonDict(
                file_id=file_id,
                file_name=file_name or "",
                caption=caption or "",
                uploaded_at=now.strftime("%Y-%m-%dT%H:%M:%S%z"),
                expires_at=expires.strftime("%Y-%m-%dT%H:%M:%S%z"),
            )
            self._persist()


    def remove(self, key: str) -> bool:
        with self._lock:
            self._maybe_reload()
            k = str(key)
            if k not in self._files:
                return False
            del self._files[k]
            self._persist()
            return True