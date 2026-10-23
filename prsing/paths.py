"""路径与常量定义。

PR-Sing 的所有运行时数据都在 PRSING_HOME 下（默认 /opt/pr-sing）。
"""

import os

HOME = os.environ.get("PRSING_HOME") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".prsing-home")

CONFIG_DIR = os.path.join(HOME, "config")
DATA_DIR = os.path.join(HOME, "data")
GEO_DIR = os.path.join(DATA_DIR, "geo")
LOG_DIR = os.path.join(HOME, "logs")
BIN_DIR = os.path.join(HOME, "bin")
BACKUP_DIR = os.path.join(HOME, "backup")

SING_BOX_BIN = os.path.join(BIN_DIR, "sing-box")
GEO_SITE_FILE = os.path.join(GEO_DIR, "geosite.dat")
GEO_IP_FILE = os.path.join(GEO_DIR, "geoip.dat")
RULESET_DIR = os.path.join(DATA_DIR, "rule-sets")

CORE_CONFIG = os.path.join(CONFIG_DIR, "sing-box.generated.json")
CORE_TEST_CONFIG = os.path.join(CONFIG_DIR, "sing-box.test.json")
CORE_LOG = os.path.join(LOG_DIR, "sing-box.log")
PANEL_LOG = os.path.join(LOG_DIR, "prsing.log")

SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
NODES_FILE = os.path.join(CONFIG_DIR, "nodes.json")
SUBS_FILE = os.path.join(CONFIG_DIR, "subscriptions.json")
CHAINS_FILE = os.path.join(CONFIG_DIR, "chains.json")
GROUPS_FILE = os.path.join(CONFIG_DIR, "groups.json")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def ensure_dirs():
    for d in (CONFIG_DIR, DATA_DIR, GEO_DIR, LOG_DIR, BIN_DIR, BACKUP_DIR):
        os.makedirs(d, exist_ok=True)
