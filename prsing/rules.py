"""规则库（rule-set .srs）下载管理。

sing-box v1.14 起，路由/DNS 规则的域名与 IP 匹配统一使用 rule-set（.srs 二进制）；
旧的 geosite/geoip 数据库引用方式已移除，本模块不再下载 geoip.dat/.db。
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

# 旧 geoip 数据库已不再被生成的配置引用，停止下载（保留空表兼容 status 结构）。
GEO_FILES = {}


def _dl_prefix() -> str:
    """下载代理前缀（与 manage.sh 选择的下载源一致，如 https://gh-proxy.com/）。

    manage.sh 通过启动器/systemd 注入 PRSING_DL_PREFIX；未设置时直连。
    """
    p = os.environ.get("PRSING_DL_PREFIX", "").strip()
    if p and not p.endswith("/"):
        p += "/"
    return p


def _ruleset_url_base(s: dict, source: str) -> str:
    base = s.get("rule_set_url_base", "https://raw.githubusercontent.com/SagerNet").rstrip("/")
    if source == "geoip":
        return f"{_dl_prefix()}{base}/sing-geoip/rule-set"
    return f"{_dl_prefix()}{base}/sing-geosite/rule-set"


def _geo_release_url(s: dict, source: str, asset: str) -> str:
    base = s.get("geo_url_base", "https://github.com/SagerNet").rstrip("/")
    return f"{base}/sing-{source}/releases/latest/download/{asset}"


def _download(url: str, dest: str, timeout: int = 45):
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
