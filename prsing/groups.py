"""节点组（selector / urltest）。

成员只能是节点或链（v1.14 组内不能嵌套组）。
"""

from . import paths, store
from .store import new_id

GROUP_TYPES = ("selector", "urltest")


def list_groups() -> list:
    return store.load(paths.GROUPS_FILE, [])


def _save(groups: list):
    store.save(paths.GROUPS_FILE, groups)


def get(group_id: str):
    for g in list_groups():
        if g["id"] == group_id:
            return g
    return None


def add(name: str, gtype: str, member_ids: list, default: str = "",
        url: str = "https://www.gstatic.com/generate_200",
        interval: int = 300, tolerance: int = 50) -> dict:
    if gtype not in GROUP_TYPES:
        raise ValueError(f"组类型必须是 {GROUP_TYPES}")
    if not member_ids:
        raise ValueError("组至少需要 1 个成员")
    _check_members(member_ids)
    groups = list_groups()
    for g in groups:
        if g["name"] == name:
            raise ValueError(f"组名已存在: {name}")
    group = {
        "id": new_id("g"),
        "name": name.strip(),
        "type": gtype,
        "members": list(member_ids),
        "default": default if default in member_ids else (member_ids[0] if member_ids else ""),
        "url": url,
        "interval": int(interval or 300),
        "tolerance": int(tolerance or 50),
        "enabled": True,
    }
    groups.append(group)
    _save(groups)
    return group


def update(group_id: str, fields: dict):
    groups = list_groups()
    for g in groups:
        if g["id"] == group_id:
            if "members" in fields:
                if not fields["members"]:
                    raise ValueError("组至少需要 1 个成员")
                _check_members(fields["members"])
                g["members"] = list(fields["members"])
                if g.get("default") not in g["members"]:
                    g["default"] = g["members"][0]
            for k in ("name", "type", "default", "url", "interval", "tolerance", "enabled"):
                if k in fields and fields[k] not in (None, ""):
                    g[k] = fields[k]
            if "interval" in fields:
                g["interval"] = int(fields["interval"] or 300)
            if "tolerance" in fields:
                g["tolerance"] = int(fields["tolerance"] or 50)
            _save(groups)
            return g
    return None


def delete(group_id: str) -> bool:
    groups = list_groups()
    new = [g for g in groups if g["id"] != group_id]
    if len(new) == len(groups):
        return False
    _save(new)
    return True


def _check_members(member_ids: list):
    from . import chains as chains_mod
    from . import nodes as nodes_mod
    for mid in member_ids:
        if not (nodes_mod.get_node(mid) or chains_mod.get(mid)):
            raise ValueError(f"组成员不存在: {mid[:8]}")
