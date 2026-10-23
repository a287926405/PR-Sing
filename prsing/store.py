"""简单的 JSON 持久化层：原子写入 + 进程内锁。"""

import json
import os
import secrets
import string
import threading
import time

_ALPHABET = string.ascii_lowercase + string.digits

_locks: dict = {}
_locks_guard = threading.Lock()


def _lock_for(path: str) -> threading.Lock:
    with _locks_guard:
        lk = _locks.get(path)
        if lk is None:
            lk = threading.Lock()
            _locks[path] = lk
        return lk


def new_id(prefix: str, n: int = 6) -> str:
    return prefix + "_" + "".join(secrets.choice(_ALPHABET) for _ in range(n))


def load(path: str, default):
    lk = _lock_for(path)
    with lk:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return default


def save(path: str, data) -> None:
    lk = _lock_for(path)
    with lk:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)


def load_json_safe(path: str, default=None):
    return load(path, default)
