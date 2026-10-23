"""sing-box v1.14 配置生成器（含链式代理 detour 链）。

已按 v1.14.3 实测通过的字段格式生成：
  - outbound: server + server_port（无 port），dial 字段带 domain_resolver
  - 链式代理: 出口 hop 为链对外 tag，hop<i>.detour = hop<i-1>
  - DNS: 新格式 servers[]/rules[]，站点匹配走 rule_set(.srs)
  - route: 无 geosite 字段，改用 rule_set；geoip 数据库仍可用于自定义规则
"""

import os
import re

from . import paths, rules as rules_mod, settings as settings_mod
from .store import save

TAG_DIRECT = "pr-sing-direct"
TAG_BLOCK = "pr-sing-block"
TAG_MAIN = "pr-sing-main"
TAG_DNS_RESOLVE = "dns-resolve"
TEST_PORT = 18080


def node_tag(node_id):
    return "pr-n-" + node_id


def chain_hop_tag(chain_id, i):
    return "pr-c-" + chain_id + "-h" + str(i)


def group_tag(group_id):
    return "pr-g-" + group_id


def _dns_server_dict(spec, tag, detour=None):
    spec = (spec or "").strip()
    if not spec:
        return None
    server, port = None, None
    if spec.startswith("https://"):
        rest = spec[8:]
        host, _, path = rest.partition("/")
        d = {"type": "https", "tag": tag, "server": host, "server_port": 443}
        if path:
            d["path"] = "/" + path
    elif spec.startswith("tls://"):
        d = {"type": "tls", "tag": tag, "server": spec[6:], "server_port": 443}
    elif spec.startswith("quic://"):
        d = {"type": "quic", "tag": tag, "server": spec[7:], "server_port": 853}
    elif spec.startswith("tcp://"):
        spec2 = spec[6:]
        if ":" in spec2:
            d = {"type": "tcp", "tag": tag, "server": spec2.rsplit(":", 1)[0],
                 "server_port": int(spec2.rsplit(":", 1)[1])}
        else:
            d = {"type": "tcp", "tag": tag, "server": spec2, "server_port": 53}
    elif ":" in spec and not spec.startswith("["):
        d = {"type": "udp", "tag": tag, "server": spec.rsplit(":", 1)[0],
             "server_port": int(spec.rsplit(":", 1)[1])}
    else:
        d = {"type": "udp", "tag": tag, "server": spec, "server_port": 53}
    is_ip = re.match(r"^[\d.:a-fA-F]*$", d["server"]) is not None
    if detour:
        d["detour"] = detour
        if not is_ip:
            d["domain_resolver"] = TAG_DNS_RESOLVE
    return d


def _enabled_nodes():
    from . import nodes as nodes_mod
    return [n for n in nodes_mod.list_nodes() if n.get("enabled")]


def _build_chains(enabled_nodes, outbounds, tag_of_name):
    """生成链的 hop outbounds；返回 {chain_id: pub_tag}。"""
    from . import chains as chains_mod
    node_by_id = {n["id"]: n for n in enabled_nodes}
    result = {}
    for c in chains_mod.list_chains():
        if not c.get("enabled"):
            continue
        members = [m for m in c.get("members", []) if m in node_by_id]
        if len(members) < 2:
            continue
        for i, mid in enumerate(members, start=1):
            src = node_by_id[mid]
            ob = {k: v for k, v in (src.get("cfg") or {}).items() if k not in ("tag", "detour")}
            ob = {"type": src["type"]}
            ob.update({k: v for k, v in (src.get("cfg") or {}).items() if k not in ("tag", "detour", "type")})
            ob["tag"] = chain_hop_tag(c["id"], i)
            ob["domain_resolver"] = TAG_DNS_RESOLVE
            if i > 1:
                ob["detour"] = chain_hop_tag(c["id"], i - 1)
            outbounds.append(ob)
        pub = chain_hop_tag(c["id"], len(members))
        result[c["id"]] = pub
        tag_of_name[c["name"]] = pub
    return result


def _build_groups(enabled_nodes, chain_pub, outbounds, tag_of_name):
    """生成节点组 outbounds；返回有成员的组 id 列表。"""
    from . import groups as groups_mod
    node_ids = {n["id"] for n in enabled_nodes}
    active = []
    for g in groups_mod.list_groups():
        if not g.get("enabled"):
            continue
        member_tags = []
        for mid in g.get("members", []):
            if mid in node_ids:
                member_tags.append(node_tag(mid))
            elif mid in chain_pub:
                member_tags.append(chain_pub[mid])
        if not member_tags:
            continue
        ob = {"tag": group_tag(g["id"]), "outbounds": member_tags}
        if g.get("type") == "urltest":
            ob["type"] = "urltest"
            ob["url"] = g.get("url") or "https://www.gstatic.com/generate_200"
            ob["interval"] = str(int(g.get("interval") or 300)) + "s"
            ob["tolerance"] = int(g.get("tolerance") or 50)
        else:
            ob["type"] = "selector"
            d = g.get("default")
            dtag = node_tag(d) if d in node_ids else None
            if dtag not in member_tags:
                dtag = member_tags[0]
            ob["default"] = dtag
        outbounds.append(ob)
        tag_of_name[g["name"]] = ob["tag"]
        active.append(g["id"])
    return active


def _defined_rule_sets():
    """已下载的 rule-set tag 集合。"""
    tags = set()
    for tag, (fname, source) in rules_mod.RULESETS.items():
        p = os.path.join(paths.RULESET_DIR, fname)
        if os.path.isfile(p) and os.path.getsize(p) > 100:
            tags.add(tag)
    return tags


def _custom_rules(raw_rules, tag_of_name):
    out = []
    for r in raw_rules or []:
        if not isinstance(r, dict) or r.get("enabled") is False:
            continue
        try:
            rule = _one_rule(r, tag_of_name)
            if rule:
                out.append(rule)
        except (ValueError, KeyError, TypeError):
            continue
    return out


def _one_rule(r, tag_of_name):
    if "raw" in r and isinstance(r["raw"], dict):
        raw = dict(r["raw"])
        ob = tag_of_name.get(r.get("outbound", ""), "")
        if ob:
            raw["outbound"] = ob
        return raw
    t = str(r.get("type") or "domain").lower()
    value = r.get("value") or ""
    if isinstance(value, str):
        items = [x.strip() for x in re.split(r"[,\n;]+", value) if x.strip()]
    else:
        items = list(value)
    if t != "ip_is_private" and not items:
        raise ValueError("value 为空")
    ob = tag_of_name.get(r.get("outbound", ""), "")
    if not ob:
        raise ValueError("outbound 未找到: %s" % r.get("outbound"))
    rule = {}
    if t == "domain":
        rule = {"domain": items}
    elif t == "domain_suffix":
        rule = {"domain_suffix": items}
    elif t == "domain_keyword":
        rule = {"domain_keyword": items}
    elif t == "domain_regex":
        rule = {"domain_regex": items}
    elif t == "ip_cidr":
        rule = {"ip_cidr": items}
    elif t == "geoip":
        rule = {"geoip": items}
    elif t == "rule_set":
        rule = {"rule_set": items}
    elif t == "source_ip_cidr":
        rule = {"source_ip_cidr": items}
    elif t == "port":
        rule = {"port": [int(x) for x in items]}
    elif t == "port_range":
        rule = {"port_range": ",".join(items)}
    elif t == "protocol":
        rule = {"protocol": items}
    elif t == "ip_is_private":
        rule = {"ip_is_private": True}
    else:
        raise ValueError("未知规则类型 %s" % t)
    rule["outbound"] = ob
    return rule


def generate(settings=None, write=True):
    """生成完整 sing-box 配置；write=True 时写入 CORE_CONFIG。"""
    settings = settings or settings_mod.load()
    enabled_nodes = _enabled_nodes()
    outbounds = [
        {"type": "direct", "tag": TAG_DIRECT, "domain_resolver": TAG_DNS_RESOLVE},
        {"type": "block", "tag": TAG_BLOCK},
    ]
    tag_of_name = {"直连": TAG_DIRECT, "拦截": TAG_BLOCK, "direct": TAG_DIRECT, "block": TAG_BLOCK}

    for n in enabled_nodes:
        ob = {"type": n["type"]}
        ob.update({k: v for k, v in (n.get("cfg") or {}).items() if k not in ("tag", "detour", "type")})
        ob["tag"] = node_tag(n["id"])
        ob["domain_resolver"] = TAG_DNS_RESOLVE
        outbounds.append(ob)
        tag_of_name[n["name"]] = ob["tag"]

    chain_pub = _build_chains(enabled_nodes, outbounds, tag_of_name)
    active_groups = _build_groups(enabled_nodes, chain_pub, outbounds, tag_of_name)

    main_members = [node_tag(n["id"]) for n in enabled_nodes]
    main_members += [chain_pub[cid] for cid in chain_pub]
    main_members += [group_tag(gid) for gid in active_groups]
    has_main = bool(main_members)
    if has_main:
        outbounds.append({
            "type": "selector", "tag": TAG_MAIN,
            "outbounds": main_members, "default": main_members[0],
        })
        tag_of_name["自动选择"] = TAG_MAIN

    # ---------------- DNS ----------------
    rs_tags = _defined_rule_sets()
    dns_servers = [
        {"type": "local", "tag": TAG_DNS_RESOLVE},
        {"type": "local", "tag": "dns-local"},
    ]
    for i, spec in enumerate(settings.get("dns_local_servers") or []):
        d = _dns_server_dict(spec, "dns-cus-%d" % i)
        if d:
            dns_servers.append(d)
    overseas = []
    for i, spec in enumerate(settings.get("dns_overseas_servers") or []):
        d = _dns_server_dict(spec, "dns-pro-%d" % i, detour=TAG_MAIN if has_main else None)
        if d:
            overseas.append(d)
            dns_servers.append(d)
    fakeip = None
    if settings.get("dns_mode") == "fakeip":
        fakeip = {"type": "fakeip", "tag": "dns-fakeip",
                  "inet4_range": settings.get("dns_fakeip_pool") or "198.18.0.0/10"}
        dns_servers.append(fakeip)
    dns_rules = []
    if "geosite-private" in rs_tags:
        dns_rules.append({"rule_set": ["geosite-private"], "server": "dns-local"})
    if "geosite-geolocation-cn" in rs_tags:
        dns_rules.append({"rule_set": ["geosite-geolocation-cn"], "server": "dns-local"})
    dns_rules.append({"source_ip_is_private": True, "server": "dns-local"})
    dns_rules.append({"domain_suffix": ["local"], "server": "dns-local"})
    if fakeip:
        dns_rules.append({"query_type": ["A", "AAAA"], "server": "dns-fakeip"})
    if overseas:
        dns_final = overseas[0]["tag"]
    elif len(dns_servers) > 2:
        dns_final = dns_servers[2]["tag"]
    else:
        dns_final = "dns-local"
    dns = {
        "servers": dns_servers,
        "rules": dns_rules,
        "final": dns_final,
        "strategy": settings.get("dns_strategy") or "prefer_ipv4",
        "timeout": "5s",
    }

    # ---------------- 入站 ----------------
    inbounds = []
    if settings.get("tun_enabled", True):
        inbounds.append({
            "type": "tun", "tag": "pr-tun",
            "interface_name": settings.get("tun_interface") or "tun0",
            "address": [settings.get("tun_address") or "172.19.0.1/30"],
            "dns_mode": settings.get("tun_dns_mode") or "hijack",
            "auto_route": bool(settings.get("tun_auto_route", True)),
            "strict_route": bool(settings.get("tun_strict_route", False)),
            "stack": settings.get("tun_stack") or "system",
        })
    if settings.get("mixed_enabled", True):
        inbounds.append({
            "type": "mixed", "tag": "pr-mixed",
            "listen": settings.get("mixed_listen") or "127.0.0.1",
            "listen_port": int(settings.get("mixed_port") or 2080),
        })

    # ---------------- 路由 ----------------
    mode = settings.get("route_mode") or "proxy"
    r_rules = [
        {"protocol": ["dns"], "action": "hijack-dns"},
        {"protocol": ["http", "tls"], "action": "sniff"},
        {"ip_is_private": True, "outbound": TAG_DIRECT},
    ]
    if "geosite-private" in rs_tags:
        r_rules.append({"rule_set": ["geosite-private"], "outbound": TAG_DIRECT})
    final = TAG_DIRECT
    if mode == "global":
        final = TAG_MAIN if has_main else TAG_DIRECT
    elif mode == "proxy":
        if "geosite-geolocation-cn" in rs_tags:
            r_rules.append({"rule_set": ["geosite-geolocation-cn"], "outbound": TAG_DIRECT})
        if "geoip-cn" in rs_tags:
            r_rules.append({"rule_set": ["geoip-cn"], "outbound": TAG_DIRECT})
        if settings.get("block_ads", True) and "geosite-category-ads-all" in rs_tags:
            r_rules.append({"rule_set": ["geosite-category-ads-all"], "outbound": TAG_BLOCK})
        r_rules.extend(_custom_rules(settings.get("extra_rules"), tag_of_name))
        final = TAG_MAIN if has_main else TAG_DIRECT
    elif mode == "custom":
        r_rules.extend(_custom_rules(settings.get("extra_rules"), tag_of_name))
        fo = settings.get("final_outbound") or "auto"
        final = tag_of_name.get(fo, TAG_MAIN)
        if not has_main and final == TAG_MAIN:
            final = TAG_DIRECT
    route = {
        "rules": r_rules,
        "final": final,
        "auto_detect_interface": True,
    }
    rule_set_cfg = []
    for tag, (fname, source) in rules_mod.RULESETS.items():
        if tag in rs_tags:
            rule_set_cfg.append({"tag": tag, "type": "local", "format": "binary",
                                 "path": os.path.join(paths.RULESET_DIR, fname)})
    if rule_set_cfg:
        route["rule_set"] = rule_set_cfg
    if os.path.isfile(paths.GEO_IP_FILE):
        route["geoip"] = {"path": paths.GEO_IP_FILE}

    cfg = {
        "log": {
            "level": settings.get("log_level") or "info",
            "output": paths.CORE_LOG,
            "timestamp": True,
        },
        "dns": dns,
        "inbounds": inbounds,
        "outbounds": outbounds,
        "route": route,
    }
    if write:
        save(paths.CORE_CONFIG, cfg)
    return cfg


def generate_test_config(target_tag, settings=None, write=True):
    """链/节点出口 IP 测试用临时配置：无 TUN，mixed 监听 127.0.0.1:18080，final=目标。"""
    full = generate(settings, write=False)
    cfg = {
        "log": {"level": "warning"},
        "dns": {
            "servers": [
                {"type": "local", "tag": TAG_DNS_RESOLVE},
                {"type": "local", "tag": "dns-local"},
            ],
            "strategy": "prefer_ipv4",
            "timeout": "5s",
        },
        "inbounds": [
            {"type": "mixed", "tag": "test-in", "listen": "127.0.0.1", "listen_port": TEST_PORT},
        ],
        "outbounds": full["outbounds"],
        "route": {
            "rules": [
                {"protocol": ["dns"], "action": "hijack-dns"},
                {"ip_is_private": True, "outbound": TAG_DIRECT},
            ],
            "final": target_tag,
        },
    }
    if "rule_set" in full["route"]:
        cfg["route"]["rule_set"] = full["route"]["rule_set"]
    if "geoip" in full["route"]:
        cfg["route"]["geoip"] = full["route"]["geoip"]
    if write:
        save(paths.CORE_TEST_CONFIG, cfg)
    return cfg

