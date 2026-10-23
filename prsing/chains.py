"""链式代理（Chain Proxy）——PR-Sing 的核心特性。

语义（与 Open-Box 公开文档一致，基于 sing-box v1.14 原生 detour 重新实现）：
    给一个出口节点（如住宅/静态 IP 的 socks5/http/https）指定前置节点，
    流量先经前置节点、再到出口节点。建好之后，这条链可以像普通节点一样
    放进节点组、分流规则里使用。

    链 = [前置1, 前置2, ..., 出口]
    生成配置：路由指向出口 hop，出口.detour = 前一个 hop，依次到前置1（无 detour）。

实现要点（sing-box v1.14）：
    - 每个 hop 复制对应节点的 outbound 配置，tag 为 pr-c-<chainid>-h<i>
    - hop<i> 的 "detour" 指向 hop<i-1> 的 tag（链式上游）
    - 链对外暴露的 tag 是出口 hop（最后一个）
"""

import json

from . import paths, store
from .store import new_id


def list_chains() -> list:
    return store.load(paths.CHAINS_FILE, [])


def _save(chains: list):
    store.save(paths.CHAINS_FILE, chains)


def get(chain_id: str):
    for c in list_chains():
        if c["id"] == chain_id:
            return c
    return None


def add(name: str, member_ids: list, note: str = "", enabled: bool = True) -> dict:
    _validate(name, member_ids, None)
    chains = list_chains()
    for c in chains:
        if c["name"] == name:
            raise ValueError(f"链名已存在: {name}")
    chain = {
        "id": new_id("c"),
        "name": name.strip(),
        "members": member_ids,
        "note": (note or "").strip(),
        "enabled": enabled,
    }
    chains.append(chain)
    _save(chains)
    return chain


def update(chain_id: str, fields: dict):
    chains = list_chains()
    for c in chains:
        if c["id"] == chain_id:
            if "name" in fields and not str(fields["name"]).strip():
                raise ValueError("链名不能为空")
            if "members" in fields:
                _validate(fields.get("name") or c["name"], fields["members"], chain_id)
            for k in ("name", "members", "note", "enabled"):
                if k in fields:
                    c[k] = fields[k]
            _save(chains)
            return c
    return None


def delete(chain_id: str) -> bool:
    chains = list_chains()
    new = [c for c in chains if c["id"] != chain_id]
    if len(new) == len(chains):
        return False
    # 清理引用了该链的组
    from . import groups as groups_mod
    for g in groups_mod.list_groups():
        if chain_id in g.get("members", []):
            g["members"] = [m for m in g["members"] if m != chain_id]
            groups_mod._save(groups_mod.list_groups())
            break
    _save(new)
    return True


def _validate(name: str, member_ids: list, self_id: str):
    """成员必须是已启用的节点；不允许成环（链只引用节点，天然无环；这里做防御）。"""
    if not isinstance(member_ids, list) or len(member_ids) < 2:
        raise ValueError("链至少需要 2 个节点（前置 + 出口）")
    from . import nodes as nodes_mod
    ids = [m for m in member_ids if m]
    seen = set()
    for mid in ids:
        node = nodes_mod.get_node(mid)
        if not node:
            raise ValueError(f"链成员不存在（可能是节点 {mid[:8]}）")
        if node["type"] not in ("socks", "http", "vless", "vmess", "trojan",
                                "shadowsocks", "hysteria2", "tuic", "naive"):
            raise ValueError(f"节点 {node['name']} 的类型 {node['type']} 不能作为链成员")
        if mid in seen:
            raise ValueError(f"链成员 {node['name']} 重复，会形成死循环")
        seen.add(mid)


def describe(chain: dict) -> list:
    """返回链的成员名称列表（供 UI 展示）。"""
    from . import nodes as nodes_mod
    out = []
    for mid in chain.get("members", []):
        n = nodes_mod.get_node(mid)
        out.append(n["name"] if n else f"(已删除:{mid[:6]})")
    return out
