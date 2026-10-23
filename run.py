#!/usr/bin/env python3
"""PR-Sing 面板入口：python3 run.py [--port 3001] [--listen 0.0.0.0] [--no-auto]"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from prsing import core, rules, settings as settings_mod, paths as paths_mod  # noqa: E402
from prsing import httpd  # noqa: E402


def main():
    ap = argparse.ArgumentParser(prog="pr-sing")
    ap.add_argument("--port", type=int, default=None, help="面板端口（默认取设置）")
    ap.add_argument("--listen", default=None, help="面板监听地址")
    ap.add_argument("--no-ensure", action="store_true", help="跳过规则库/Geo 自检下载")
    ap.add_argument("--no-auto", action="store_true", help="不自动启动内核")
    args = ap.parse_args()

    s = settings_mod.load()
    listen = args.listen or s.get("panel_listen", "0.0.0.0")
    port = args.port or int(s.get("panel_port", 3001))

    # 确保运行时目录
    paths_mod.ensure_dirs()

    if not args.no_ensure:
        try:
            r = rules.ensure_all(quiet=True)
            if r.get("errors"):
                print("[pr-sing] 规则库/Geo 下载警告: %s" % r["errors"], flush=True)
        except Exception as e:
            print("[pr-sing] 规则库自检失败（继续运行）: %s" % e, flush=True)

    if not args.no_auto and s.get("auto_start_core", True):
        from prsing import core
        if not core.get_pid():
            r = core.start()
            print("[pr-sing] 内核自启动: %s" % (r.get("detail") if r.get("ok")
                                               else "失败: " + r.get("detail", "?")[:200]),
                  flush=True)

    try:
        httpd.serve(listen, port)
    except OSError as e:
        print("[pr-sing] 面板启动失败: %s（端口 %d 被占用？）" % (e, port), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()