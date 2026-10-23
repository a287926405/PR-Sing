"""规则库（rule-set .srs）与 Geo 数据下载管理。

sing-box v1.14 起，路由/DNS 规则的域名站点匹配使用 rule-set（.srs 二进制），
不再直接引用 geosite 数据库；中国大陆 IP 同时保留 geoip 数据库（.db 格式）。
"""

import json
import os
import urllib.request

from . import paths, settings as settings_mod

_UA = {"User-Agent": "Mozilla/5.0 (compatible; PR-Sing)"}

# tag -> (文件名, 来源)
RULESETS = {
    "geosite-geolocation-cn": ("geosite-geolocation-cn.srs", "geosite"),
    "geosite-private": ("geosite-private.srs", "geosite"),
    "geosite-category-ads-all": ("geosite-category-ads-all.srs", "geosite"),
    "geoip-cn": ("geoip-cn.srs", "geoip"),
}

GEO_FILES = {
    "geoip": ("geoip.db", "geoip", "geoip.dat"),
}


def _ruleset_url_base(s: dict, source: str) -> str:
    base = s.get("rule_set_url_base", "https://raw.githubusercontent.com/SagerNet").rstrip("/")
    if source == "geoip":
        return f"{base}/sing-geoip/rule-set"
    return f"{base}/sing-geosite/rule-set"


def _geo_release_url(s: dict, source: str, asset: str) -> str:
    base = s.get("geo_url_base", "https://github.com/SagerNet").rstrip("/")
    return f"{base}/sing-{source}/releases/latest/download/{asset}"


def _download(url: str, dest: str, timeout: int = 120):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest + ".part", "wb") as f:
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            f.write(chunk)
    os.replace(dest + ".part", dest)
    return os.path.getsize(dest)


def status() -> dict:
    s = settings_mod.load()
    out = {"rule_sets": {}, "geo": {}}
    for tag, (fname, source) in RULESETS.items():
        p = os.path.join(paths.RULESET_DIR, fname)
        out["rule_sets"][tag] = {
            "file": fname,
            "exists": os.path.isfile(p),
            "size": os.path.getsize(p) if os.path.isfile(p) else 0,
        }
    for key, (asset, source, local_name) in GEO_FILES.items():
        p = os.path.join(paths.GEO_DIR, local_name)
        out["geo"][key] = {
            "file": local_name,
            "exists": os.path.isfile(p),
            "size": os.path.getsize(p) if os.path.isfile(p) else 0,
        }
    return out


def ensure_all(quiet: bool = False) -> dict:
    """确保全部规则库/Geo 文件就绪；缺失则下载。返回 {downloaded: [...], errors: [...]}"""
    s = settings_mod.load()
    downloaded, errors = [], []
    for tag, (fname, source) in RULESETS.items():
        p = os.path.join(paths.RULESET_DIR, fname)
        if os.path.isfile(p) and os.path.getsize(p) > 100:
            continue
        try:
            url = f"{_ruleset_url_base(s, source)}/{fname}"
            _download(url, p)
            downloaded.append(fname)
        except Exception as e:
            errors.append(f"{fname}: {e}")
    for key, (asset, source, local_name) in GEO_FILES.items():
        p = os.path.join(paths.GEO_DIR, local_name)
        if os.path.isfile(p) and os.path.getsize(p) > 10000:
            continue
        try:
            url = _geo_release_url(s, source, asset)
            _download(url, p)
            downloaded.append(local_name)
        except Exception as e:
            errors.append(f"{local_name}: {e}")
    if not quiet:
        return {"downloaded": downloaded, "errors": errors}
    return {}


def update_all() -> dict:
    """强制重新下载全部文件。"""
    s = settings_mod.load()
    downloaded, errors = [], []
    for tag, (fname, source) in RULESETS.items():
        p = os.path.join(paths.RULESET_DIR, fname)
        try:
            url = f"{_ruleset_url_base(s, source)}/{fname}"
            _download(url, p)
            downloaded.append(fname)
        except Exception as e:
            errors.append(f"{fname}: {e}")
    for key, (asset, source, local_name) in GEO_FILES.items():
        p = os.path.join(paths.GEO_DIR, local_name)
        try:
            url = _geo_release_url(s, source, asset)
            _download(url, p)
            downloaded.append(local_name)
        except Exception as e:
            errors.append(f"{local_name}: {e}")
    return {"downloaded": downloaded, "errors": errors, "status": status()}
