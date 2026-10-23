"""订阅管理：添加 / 拉取 / 解析 / 更新。

支持 base64 或纯文本的分享链接集合；自动剔除旧节点、按名称去重。
"""

import base64
import re
import time
import urllib.request

from . import nodes as nodes_mod
from . import paths, store
from .store import new_id

_UA = "Mozilla/5.0 (compatible; PR-Sing)"


def list_subs() -> list:
    return store.load(paths.SUBS_FILE, [])


def _save(subs: list):
    store.save(paths.SUBS_FILE, subs)


def get(sub_id: str):
    for s in list_subs():
        if s["id"] == sub_id:
            return s
    return None


def add(name: str, url: str, enabled: bool = True) -> dict:
    subs = list_subs()
    for s in subs:
        if s["url"] == url:
            raise ValueError("该订阅已存在")
    sub = {
        "id": new_id("s"),
        "name": (name or "").strip() or (url.split("/")[2] if "://" in url else "订阅"),
        "url": url.strip(),
        "enabled": enabled,
        "updated_at": 0,
        "node_ids": [],
    }
    subs.append(sub)
    _save(subs)
    return sub


def update(sub_id: str, fields: dict):
    subs = list_subs()
    for s in subs:
        if s["id"] == sub_id:
            for k in ("name", "url", "enabled"):
                if k in fields:
                    s[k] = fields[k]
            _save(subs)
            return s
    return None


def delete(sub_id: str) -> bool:
    subs = list_subs()
    new = [s for s in subs if s["id"] != sub_id]
    if len(new) == len(subs):
        return False
    # 同时移除该订阅下的节点
    removed_ids = []
    for s in subs:
        if s["id"] == sub_id:
            removed_ids = s.get("node_ids", [])
    if removed_ids:
        all_nodes = nodes_mod.list_nodes()
        nodes_mod._save_nodes([n for n in all_nodes if n["id"] not in set(removed_ids)])
    _save(new)
    return True


def _fetch(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": _UA,
        "Accept": "*/*",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    text = data.decode("utf-8", "replace").strip()
    # base64 订阅
    if "\n" not in text and "://" not in text[:200]:
        try:
            pad = "=" * (-len(text) % 4)
            decoded = base64.b64decode(text + pad).decode("utf-8", "replace")
            if "://" in decoded:
                return decoded
        except Exception:
            pass
    return text


def refresh(sub_id: str) -> dict:
    """拉取订阅并同步节点。返回统计信息。"""
    sub = get(sub_id)
    if not sub:
        raise ValueError("订阅不存在")
    text = _fetch(sub["url"])
    parsed, errors = nodes_mod.parse_links(text)
    # 用 订阅id|节点名 做归属：同名节点保留旧的 id，新增的追加
    all_nodes = nodes_mod.list_nodes()
    by_name = {n["name"]: n for n in all_nodes}
    keep_ids = set(sub.get("node_ids", []))
    kept = []
    added = 0
    for item in parsed:
        name = (item.get("name") or "").strip() or f"节点-{item['type']}"
        existing = by_name.get(name)
        if existing:
            # 更新配置
            existing["cfg"] = item["cfg"]
            existing["type"] = item["type"]
            kept.append(existing["id"])
        else:
            node = {
                "id": new_id("n"),
                "name": name,
                "type": item["type"],
                "enabled": True,
                "latency": None,
                "latency_at": 0,
                "raw": "",
                "cfg": item["cfg"],
                "sub_id": sub_id,
            }
            all_nodes.append(node)
            by_name[name] = node
            kept.append(node["id"])
            added += 1
    # 清理旧节点（订阅中被删掉的）
    old_ids = set(sub.get("node_ids", [])) - set(kept)
    if old_ids:
        all_nodes = [n for n in all_nodes if n["id"] not in old_ids]
        for n in all_nodes:
            by_name[n["name"]] = n
    nodes_mod._save_nodes(all_nodes)
    sub["node_ids"] = list(kept)
    sub["updated_at"] = int(time.time())
    # 把更新后的 sub 写回订阅列表再保存（此前重新加载一份新数据保存，
    # 改过的 node_ids/updated_at 被丢弃，刷新结果从不落盘）
    subs = list_subs()
    for i, s in enumerate(subs):
        if s["id"] == sub_id:
            subs[i] = sub
            break
    _save(subs)
    return {"added": added, "kept": len(kept), "removed": len(old_ids), "errors": errors[:20]}


def refresh_all() -> list:
    results = []
    for s in list_subs():
        if not s.get("enabled"):
            continue
        try:
            r = refresh(s["id"])
            r["name"] = s["name"]
            r["ok"] = True
        except Exception as e:
            r = {"name": s["name"], "ok": False, "error": str(e)}
        results.append(r)
    return results
