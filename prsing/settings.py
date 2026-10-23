"""面板设置：默认值、加载保存、登录鉴权。"""

import hashlib
import hmac
import json
import secrets
import time

from . import paths, store

DEFAULT_SETTINGS = {
    # 面板
    "panel_port": 3001,
    "panel_listen": "0.0.0.0",
    # 内核
    "auto_start_core": True,
    "core_binary": paths.SING_BOX_BIN,
    "log_level": "info",
    # 入站
    "tun_enabled": False,
    "tun_interface": "tun0",
    "tun_address": "172.19.0.1/30",
    "tun_stack": "system",           # system / gvisor / mixed
    "tun_auto_route": True,
    "tun_strict_route": False,
    "tun_dns_mode": "hijack",        # hijack / native / disabled
    "mixed_enabled": True,
    "mixed_listen": "127.0.0.1",
    "mixed_port": 2080,
    # 分流
    "route_mode": "proxy",           # global / proxy / direct / custom
    "final_outbound": "auto",        # auto = 主选择组
    "extra_rules": [],               # 自定义规则（所有模式都生效，排在内置规则之后）
    "block_ads": True,
    # DNS
    "dns_mode": "fakeip",            # auto / fakeip
    "dns_local_servers": [],         # 国内/本地解析，如 223.5.5.5
    "dns_overseas_servers": ["https://1.1.1.1/dns-query", "tls://8.8.8.8"],
    "dns_fakeip_pool": "198.18.0.0/10",
    "dns_strategy": "prefer_ipv4",
    # 链式代理
    "chain_test_url": "https://api.ipify.org",
    "chain_geo_url": "https://ipinfo.io/json",
    "chain_test_timeout": 20,
    # 规则库 / Geo 数据
    "geo_url_base": "https://github.com/SagerNet",
    "rule_set_url_base": "https://raw.githubusercontent.com/SagerNet",
    "user_agent": "Mozilla/5.0 (PR-Sing)",
    # 订阅
    "sub_update_interval": 72,       # 小时
    "sub_http_timeout": 20,
}

# 内置 rule-set 清单：tag -> (源文件名, 说明)
BUILTIN_RULESETS = {
    "geosite-geolocation-cn": ("geosite-geolocation-cn.srs", "中国大陆（地理位置）域名，代理模式下默认直连"),
    "geosite-private": ("geosite-private.srs", "局域网/私有域名"),
    "geosite-category-ads-all": ("geosite-category-ads-all.srs", "广告与跟踪（全部）"),
    "geoip-cn": ("geoip-cn.srs", "中国大陆（地理位置）IP 段，来自 sing-geoip"),
}


def default_settings() -> dict:
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    salt = secrets.token_hex(8)
    s["panel_password_salt"] = salt
    s["panel_password_hash"] = _hash_password("pr-sing", salt)
    return s


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def load() -> dict:
    s = store.load(paths.SETTINGS_FILE, None)
    if not isinstance(s, dict):
        s = default_settings()
        store.save(paths.SETTINGS_FILE, s)
        return s
    base = json.loads(json.dumps(DEFAULT_SETTINGS))
    merged = {**base, **s}
    # 确保密码字段存在（旧版本可能缺失）
    if "panel_password_hash" not in merged or "panel_password_salt" not in merged:
        d = default_settings()
        merged["panel_password_hash"] = d["panel_password_hash"]
        merged["panel_password_salt"] = d["panel_password_salt"]
    store.save(paths.SETTINGS_FILE, merged)
    return merged


def save(settings: dict) -> dict:
    store.save(paths.SETTINGS_FILE, settings)
    return settings


def set_password(settings: dict, old_password: str, new_password: str) -> str:
    if old_password:
        if not _verify(settings, old_password):
            return "原密码错误"
    if len(new_password) < 4:
        return "新密码至少 4 位"
    salt = secrets.token_hex(8)
    settings["panel_password_salt"] = salt
    settings["panel_password_hash"] = _hash_password(new_password, salt)
    store.save(paths.SETTINGS_FILE, settings)
    return ""


def _verify(settings: dict, password: str) -> bool:
    return hmac.compare_digest(
        _hash_password(password, settings.get("panel_password_salt", "")),
        settings.get("panel_password_hash", ""),
    )


def verify_password(settings: dict, password: str) -> bool:
    return _verify(settings, password)


def make_session_token(settings: dict, expires_in: int = 30 * 86400) -> str:
    """签发会话 token：HMAC(payload, secret)。"""
    secret = settings.get("panel_password_hash", "pr-sing")
    payload = f"pr-sing-session:{int(time.time()) + expires_in}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def check_session_token(settings: dict, token: str) -> bool:
    try:
        payload, sig = token.rsplit(":", 1)
    except ValueError:
        return False
    expected = hmac.new(
        settings.get("panel_password_hash", "pr-sing").encode(),
        payload.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        _, expires = payload.split(":")
        return int(expires) >= time.time()
    except (ValueError, IndexError):
        return False