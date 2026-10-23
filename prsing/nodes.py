"""节点管理：分享链接解析（v1.14 outbound 格式）、CRUD、批量导入。

支持协议：vless / vmess / trojan / shadowsocks / hysteria2 / tuic /
naive / socks / http(s)。
也支持直接粘贴 sing-box outbound JSON（手动节点）。
注：sing-box 没有 Snell 出站，snell:// 链接不受支持（会明确报错）。
"""

import base64
import binascii
import json
import re
from urllib.parse import urlparse, parse_qs, unquote

from . import paths, store
from .store import new_id

PROTOCOL_TYPES = (
    "vless", "vmess", "trojan", "shadowsocks", "hysteria2", "tuic",
    "naive", "socks", "http",
)

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
FINGERPRINTS = ("chrome", "chrome_psk", "firefox", "safari", "ios", "android", "edge", "random")


def _b64decode(s: str) -> str:
    pad = "=" * (-len(s) % 4)
    return base64.b64decode(s + pad, validate=False).decode("utf-8", "replace")


def _q1(params: dict) -> dict:
    """取 query 参数的第一个值，统一小写 key。"""
    out = {}
    for k, v in params.items():
        if v:
            out[k.lower()] = v[0]
    return out


def _build_tls(q: dict, host: str):
    """从 query 参数构造 v1.14 tls 块；无加密返回 None。"""
    security = (q.get("security") or "").lower()
    if not security and q.get("tls") in ("1", "true", "tls"):
        security = "tls"
    if not security or security in ("none", "auto", "system"):
        return None
    tls = {"enabled": True}
    sni = q.get("sni") or q.get("peer") or q.get("server_name")
    if sni:
        tls["server_name"] = sni
    elif not q.get("pbk") and security != "reality":
        tls["server_name"] = host
    fp = (q.get("fp") or q.get("fingerprint") or "").lower()
    if fp:
        if fp not in FINGERPRINTS:
            fp = "chrome" if fp not in FINGERPRINTS else fp
        tls["utls"] = {"enabled": True, "fingerprint": fp}
    alpn = q.get("alpn")
    if alpn:
        parts = [a for a in re.split(r"[,;/]+", alpn) if a]
        if parts:
            tls["alpn"] = parts
    if q.get("insecure") in ("1", "true") or q.get("allow_insecure") in ("1", "true"):
        tls["insecure"] = True
    if security == "reality" or q.get("pbk"):
        if not q.get("pbk"):
            raise ValueError("reality 节点缺少 pbk(public_key) 参数")
        tls["reality"] = {"enabled": True, "public_key": q["pbk"], "short_id": q.get("sid", "")}
    return tls


def _build_transport(q: dict):
    """v2ray transport：ws / grpc / http。tcp 不需要该字段。kcp/quic 在 1.14 已移除。"""
    t = (q.get("type") or q.get("net") or "tcp").lower()
    if t in ("", "tcp"):
        return None
    if t in ("ws", "websocket"):
        out = {"type": "ws"}
        if q.get("path"):
            out["path"] = q["path"]
        if q.get("host"):
            out["headers"] = {"Host": q["host"]}
        if q.get("maxearlydata") or q.get("max_early_data"):
            try:
                out["max_early_data"] = int(q.get("maxearlydata") or q.get("max_early_data"))
            except ValueError:
                pass
        if q.get("edhsname") or q.get("early_data_header_name"):
            out["early_data_header_name"] = q.get("edhsname") or q.get("early_data_header_name")
        return out
    if t == "grpc":
        out = {"type": "grpc"}
        sn = q.get("servicename") or q.get("service_name")
        if sn:
            out["service_name"] = sn
        return out
    if t in ("http", "httpupgrade"):
        out = {"type": "http"}
        if q.get("host"):
            out["host"] = [q["host"]]
        if q.get("path"):
            out["path"] = q["path"]
        return out
    if t in ("kcp", "quic"):
        raise ValueError(f"内核 v1.14 不再支持 {t.upper()} 传输层，请在客户端改用 WS/gRPC/HTTP 节点")
    return None


def _split_name(url: str) -> tuple:
    """把 # 后的节点名分离出来（URL 转义）。"""
    if "#" in url:
        body, name = url.rsplit("#", 1)
        return body, name
    return url, ""


def _split_host_port(hostport: str, default_port: int) -> tuple:
    hostport = hostport.strip().split("?")[0].split("#")[0].strip("[]")
    if ":" in hostport:
        host, _, port = hostport.rpartition(":")
        try:
            return host, int(port)
        except ValueError:
            pass
    return hostport, default_port


def _base_cfg(host: str, port: int) -> dict:
    return {"server": host, "server_port": port}


# ---------------------------------------------------------------- 各协议

def _parse_vless(url: str, q: dict, host: str, port: int, name: str) -> dict:
    m = re.match(r"vless://([0-9a-fA-F-]{36})@", url)
    if not m:
        raise ValueError("vless 链接格式不正确（缺少 uuid）")
    uuid = m.group(1)
    cfg = _base_cfg(host, port)
    cfg["uuid"] = uuid
    flow = q.get("flow", "")
    if flow:
        cfg["flow"] = flow
    tr = _build_transport(q)
    if tr:
        cfg["transport"] = tr
    tls = _build_tls(q, host)
    if tls:
        cfg["tls"] = tls
    return {"name": name, "type": "vless", "cfg": cfg}


def _parse_vmess(url: str, q: dict, host: str, port: int, name: str) -> dict:
    raw = url[len("vmess://"):]
    try:
        data = json.loads(_b64decode(raw))
    except (ValueError, binascii.Error):
        raise ValueError("vmess base64 解码失败")
    add = data.get("add") or host
    p = int(data.get("port") or port)
    if not data.get("id"):
        raise ValueError("vmess 缺少 uuid(id)")
    cfg = _base_cfg(add, p)
    cfg["uuid"] = data["id"]
    scy = data.get("scy") or "auto"
    if scy not in ("auto", "none", "zero", "aes-128-cfb", "aes-128-gcm", "chacha20-poly1305"):
        scy = "auto"
    cfg["security"] = scy
    if data.get("aid") not in (None, ""):
        try:
            cfg["alter_id"] = int(data["aid"])
        except ValueError:
            pass
    # vmess 的 json 内 transport 参数
    vq = {
        "type": data.get("net") or "tcp",
        "path": data.get("path") or "",
        "host": data.get("host") or "",
        "security": data.get("tls") or "",
        "sni": data.get("sni") or "",
        "fp": data.get("fp") or "",
        "alpn": data.get("alpn") or "",
        "servicename": data.get("serviceName") or "",
    }
    vq = {k: v for k, v in vq.items() if v}
    tr = _build_transport(vq)
    if tr:
        cfg["transport"] = tr
    tls = _build_tls(vq, add)
    if tls:
        cfg["tls"] = tls
    return {"name": name or data.get("ps") or "vmess", "type": "vmess", "cfg": cfg}


def _parse_trojan(url: str, q: dict, host: str, port: int, name: str) -> dict:
    body = url[len("trojan://"):]
    if "@" not in body:
        raise ValueError("trojan 链接格式不正确（缺少密码）")
    password, _, hostport = body.partition("@")
    if not password:
        raise ValueError("trojan 密码为空")
    host2, port2 = _split_host_port(hostport, port)
    cfg = _base_cfg(host2, port2)
    cfg["password"] = password
    tr = _build_transport(q)
    if tr:
        cfg["transport"] = tr
    tls = _build_tls(q, host2)
    if tls:
        cfg["tls"] = tls
    return {"name": name, "type": "trojan", "cfg": cfg}


def _parse_ss(url: str, q: dict, host: str, port: int, name: str) -> dict:
    body = url[len("ss://"):]
    body, q2, host3, port3 = body, q, host, port
    if "@" in body:
        cred, _, hostport = body.partition("@")
        # SIP002 两种写法：base64(method:password) 或明文 method:password。
        # 先试 base64，解出的内容形如 method:password 且可打印才采用，
        # 否则按明文处理（此前无条件按 base64 解，明文链接必然损坏）。
        decoded = None
        try:
            d = _b64decode(cred)
            if ":" in d and all(32 <= ord(ch) < 127 for ch in d):
                decoded = d
        except (ValueError, binascii.Error):
            decoded = None
        method, _, password = (decoded if decoded is not None else cred).partition(":")
        host3, port3 = _split_host_port(hostport, port)
    else:
        try:
            decoded = _b64decode(body)
        except (ValueError, binascii.Error):
            raise ValueError("ss 链接格式不正确")
        if "@" not in decoded:
            raise ValueError("ss 链接格式不正确")
        cred, _, hostport = decoded.partition("@")
        method, _, password = cred.partition(":")
        host3, port3 = _split_host_port(hostport, port)
    if not method or not password:
        raise ValueError("ss 缺少 method 或 password")
    cfg = _base_cfg(host3, port3)
    cfg["method"] = method
    cfg["password"] = password
    return {"name": name, "type": "shadowsocks", "cfg": cfg}


def _parse_hy2(url: str, q: dict, host: str, port: int, name: str) -> dict:
    body = re.sub(r"^(hysteria2|hy2)://", "", url)
    if "@" not in body:
        raise ValueError("hy2 链接格式不正确（缺少密码）")
    password, _, hostport = body.partition("@")
    host2, port2 = _split_host_port(hostport, port)
    cfg = _base_cfg(host2, port2)
    cfg["password"] = password
    obfs = (q.get("obfs") or "").lower()
    if obfs in ("salamander", "salamander-2023", "salamander2"):
        cfg["obfs"] = {"type": "salamander", "password": q.get("obfs-password", "")}
    tls = _build_tls(q, host2)
    if tls:
        cfg["tls"] = tls
    return {"name": name, "type": "hysteria2", "cfg": cfg}


def _parse_tuic(url: str, q: dict, host: str, port: int, name: str) -> dict:
    body = url[len("tuic://"):]
    if "@" not in body:
        raise ValueError("tuic 链接格式不正确")
    cred, _, hostport = body.partition("@")
    if ":" not in cred:
        raise ValueError("tuic 缺少 uuid:password")
    uuid, _, password = cred.partition(":")
    if not UUID_RE.match(uuid):
        raise ValueError("tuic uuid 格式不正确")
    host2, port2 = _split_host_port(hostport, port)
    cfg = _base_cfg(host2, port2)
    cfg["uuid"] = uuid
    if password:
        cfg["password"] = password
    cc = (q.get("congestion_control") or "").lower()
    if cc in ("cubic", "new_reno", "bbr"):
        cfg["congestion_control"] = cc
    alpn = q.get("alpn")
    if alpn:
        parts = [a for a in re.split(r"[,;/]+", alpn) if a]
        if parts:
            cfg["alpn"] = parts
    tls = _build_tls(q, host2)
    if tls:
        cfg["tls"] = tls
    return {"name": name, "type": "tuic", "cfg": cfg}


def _parse_naive(url: str, q: dict, host: str, port: int, name: str) -> dict:
    body = url[len("naive://"):]
    cred, _, hostport = body.partition("@")
    username, _, password = cred.partition(":")
    host2, port2 = _split_host_port(hostport, port)
    cfg = _base_cfg(host2, port2)
    cfg["username"] = username
    if password:
        cfg["password"] = password
    tls = _build_tls(q, host2)
    if tls:
        cfg["tls"] = tls
    return {"name": name, "type": "naive", "cfg": cfg}


def _parse_socks(url: str, q: dict, host: str, port: int, name: str) -> str:
    return url[len("socks5://"):] if url.startswith("socks5://") else url[len("socks://"):].lstrip("/")


def _parse_generic_proxy(scheme: str, url: str, q: dict, host: str, port: int, name: str) -> dict:
    """socks5 / http / https 节点。"""
    body = url
    for pre in (f"{scheme}://", "socks5://", "socks://"):
        if body.startswith(pre):
            body = body[len(pre):]
            break
    if not body:
        raise ValueError(f"{scheme} 链接为空")
    cred = ""
    if "@" in body:
        cred, _, body = body.rpartition("@")
    host2, port2 = _split_host_port(body, 1080 if scheme == "socks" else 3128)
    cfg = _base_cfg(host2, port2)
    if scheme == "socks":
        cfg["version"] = "5"
    if cred:
        u, _, p = cred.partition(":")
        if u:
            cfg["username"] = u
        if p:
            cfg["password"] = p
    if scheme == "https":
        tls = _build_tls({**q, "security": "tls"}, host2)
        if tls:
            cfg["tls"] = tls
    return {"name": name, "type": "socks" if scheme == "socks" else "http", "cfg": cfg}



def parse_link(url: str) -> dict:
    """解析单条分享链接，返回 {name, type, cfg}。失败抛 ValueError。"""
    url = url.strip()
    if not url:
        raise ValueError("空链接")
    low = url.lower()
    # 手动 JSON 节点
    if low.startswith("{"):
        try:
            obj = json.loads(url)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 解析失败: {e}")
        if not isinstance(obj, dict) or not obj.get("type"):
            raise ValueError("JSON 节点缺少 type 字段")
        if obj["type"] not in PROTOCOL_TYPES + ("direct", "block"):
            raise ValueError(f"不支持的节点类型: {obj['type']}")
        cfg = {k: v for k, v in obj.items() if k not in ("type", "tag")}
        return {"name": obj.get("tag") or obj.get("name") or "手动节点",
                "type": obj["type"], "cfg": cfg}
    body, raw_name = _split_name(url)
    # # 后的名称是 URL 百分号编码，必须先 unquote，否则中文名全是 %E6%... 乱码
    name = _b64decode_try(unquote(raw_name)) or unquote(raw_name)
    url = body  # 后续各协议解析器只看去掉 #名称 的部分

    if low.startswith("vless://"):
        up = urlparse(url)
        q = _q1(parse_qs(up.query))
        host, port = up.hostname or "", 443
        if up.port:
            port = up.port
        return _parse_vless(url, q, host, port, name)
    if low.startswith("vmess://"):
        return _parse_vmess(url, {}, "", 0, name)
    if low.startswith("trojan://"):
        up = urlparse(url)
        q = _q1(parse_qs(up.query))
        host, port = up.hostname or "", 443
        if up.port:
            port = up.port
        return _parse_trojan(url, q, host, port, name)
    if low.startswith("ss://"):
        up = urlparse(url)
        q = _q1(parse_qs(up.query))
        host, port = up.hostname or "", 8388
        if up.port:
            port = up.port
        return _parse_ss(url, q, host, port, name)
    if low.startswith(("hysteria2://", "hy2://")):
        up = urlparse(url)
        q = _q1(parse_qs(up.query))
        host, port = up.hostname or "", 443
        if up.port:
            port = up.port
        return _parse_hy2(url, q, host, port, name)
    if low.startswith("tuic://"):
        up = urlparse(url)
        q = _q1(parse_qs(up.query))
        host, port = up.hostname or "", 443
        if up.port:
            port = up.port
        return _parse_tuic(url, q, host, port, name)
    if low.startswith("naive://"):
        up = urlparse(url)
        q = _q1(parse_qs(up.query))
        host, port = up.hostname or "", 443
        if up.port:
            port = up.port
        return _parse_naive(url, q, host, port, name)
    if low.startswith("socks5://") or low.startswith("socks://"):
        up = urlparse(url)
        return _parse_generic_proxy("socks", url, _q1(parse_qs(up.query)), up.hostname or "", up.port or 1080, name)
    if low.startswith("https://") and _looks_like_https_proxy(url):
        up = urlparse(url)
        return _parse_generic_proxy("https", url, _q1(parse_qs(up.query)), up.hostname or "", up.port or 443, name)
    if low.startswith("http://"):
        up = urlparse(url)
        return _parse_generic_proxy("http", url, _q1(parse_qs(up.query)), up.hostname or "", up.port or 3128, name)
    if low.startswith("snell://"):
        raise ValueError("sing-box 不支持 Snell 协议出站，无法导入 snell 节点")
    scheme = url.split("://")[0] if "://" in url else url[:12]
    raise ValueError(f"不支持的链接协议: {scheme}")


def _looks_like_https_proxy(url: str) -> bool:
    """https:// 默认按订阅处理；带账号或非标端口才视为 https 代理节点。"""
    from urllib.parse import urlparse
    up = urlparse(url)
    if up.port and up.port not in (443, 80):
        return True
    if up.username or up.password:
        return True
    return False


def _b64decode_try(s: str) -> str:
    """链接名可能是 base64（部分客户端习惯）；仅当形似合法 base64 时才解码。"""
    if not s or len(s) < 8:
        return s
    if not re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", s):
        return s
    try:
        d = _b64decode(s)
        if d and all(32 <= ord(c) < 127 or "\u4e00" <= c <= "\u9fff" for c in d):
            return d
    except (ValueError, TypeError):
        pass
    return s


def parse_links(text: str) -> tuple:
    """批量解析多行链接。返回 (nodes, errors)；行号为原文真实行号（含空行）。"""
    nodes, errors = [], []
    for i, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            nodes.append(parse_link(line))
        except Exception as e:
            errors.append({"line": i, "text": line[:120], "error": str(e)})
    return nodes, errors


# ---------------------------------------------------------------- CRUD

def list_nodes() -> list:
    return store.load(paths.NODES_FILE, [])


def _save_nodes(nodes: list):
    store.save(paths.NODES_FILE, nodes)


def _unique_name(nodes: list, base: str) -> str:
    names = {n["name"] for n in nodes}
    if base not in names:
        return base
    i = 2
    while f"{base}-{i}" in names:
        i += 1
    return f"{base}-{i}"


def add_nodes(parsed: list) -> list:
    """parsed: parse_link(s) 结果列表。返回新增的节点。"""
    nodes = list_nodes()
    added = []
    for item in parsed:
        name = (item.get("name") or "").strip() or f"未命名-{item['type']}"
        name = _unique_name(nodes, name)
        node = {
            "id": new_id("n"),
            "name": name,
            "type": item["type"],
            "enabled": True,
            "latency": None,
            "latency_at": 0,
            "raw": item.get("raw", ""),
            "cfg": item["cfg"],
        }
        nodes.append(node)
        added.append(node)
    if added:
        _save_nodes(nodes)
    return added


def get_node(node_id: str):
    for n in list_nodes():
        if n["id"] == node_id:
            return n
    return None


def update_node(node_id: str, fields: dict):
    nodes = list_nodes()
    for n in nodes:
        if n["id"] == node_id:
            for k in ("name", "enabled", "cfg", "raw", "type"):
                if k in fields:
                    if k == "name" and not str(fields[k]).strip():
                        raise ValueError("节点名不能为空")
                    n[k] = fields[k]
            _save_nodes(nodes)
            return n
    return None


def delete_node(node_id: str) -> bool:
    nodes = list_nodes()
    new = [n for n in nodes if n["id"] != node_id]
    if len(new) == len(nodes):
        return False
    _save_nodes(new)
    return True


def set_latency(node_id: str, latency_ms):
    import time
    nodes = list_nodes()
    for n in nodes:
        if n["id"] == node_id:
            n["latency"] = latency_ms
            n["latency_at"] = int(time.time())
            _save_nodes(nodes)
            return n
    return None
