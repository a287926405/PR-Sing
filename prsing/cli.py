"""PR-Sing 终端管理 CLI（供 manage.sh 调用，也可直接使用）。

用法: python3 -m prsing.cli <命令> [参数]
  status                     内核状态与计数
  start|stop|restart         内核控制
  gen                        重新生成配置并校验
  node list                  节点列表
  node import <链接...>      导入分享链接（多个参数或 - 从 stdin 读）
  node del <id>              删除节点
  node test <id>             节点延迟测试
  chain list                 链列表（含成员路径）
  chain add <名> <id,id,...> 按顺序新建链（最后是出口）
  chain del <id>             删除链
  chain test <id>            链出口 IP 测试
  group list                 节点组列表
  sub list                   订阅列表
  sub add <名称> <URL>       添加订阅
  sub refresh [id]           刷新订阅（无 id = 全部）
环境变量 PRSING_HOME 指定数据目录（与面板共用同一份数据）。
"""

import os
import sys

from . import paths


def _p(*a):
    print(*a, flush=True)


def _fail(msg):
    _p("错误: " + msg)
    return 1


def cmd_status():
    from . import chains as chains_mod, core, groups, nodes, subs
    paths.ensure_dirs()
    st = core.status()
    _p("内核: %s (PID %s)" % ("运行中" if st["running"] else "已停止", st.get("pid") or "-"))
    _p("内核版本: %s" % (st.get("version") or "-"))
    _p("内核路径: %s (%s)" % (st["core_bin"], "正常" if st["core_bin_ok"] else "缺失"))
    _p("Mixed 入站: %s 端口 %s" % ("开" if st["mixed_enabled"] else "关", st["mixed_port"]))
    _p("TUN: %s" % ("开 (%s)" % st["tun_interface"] if st["tun_enabled"] else "关"))
    _p("分流模式: %s / DNS 模式: %s" % (st.get("route_mode"), st.get("dns_mode")))
    _p("节点 %d / 链 %d / 组 %d / 订阅 %d" % (
        len(nodes.list_nodes()), len(chains_mod.list_chains()),
        len(groups.list_groups()), len(subs.list_subs())))
    return 0


def cmd_core(action):
    from . import core
    paths.ensure_dirs()
    r = {"start": core.start, "stop": core.stop, "restart": core.restart}[action]()
    _p(("OK: " if r.get("ok") else "失败: ") + str(r.get("detail", "")))
    if r.get("output"):
        _p(r["output"][-1200:])
    return 0 if r.get("ok") else 1


def cmd_gen():
    from . import core, generator
    paths.ensure_dirs()
    generator.generate()
    chk = core.check_config()
    _p("配置已生成: " + paths.CORE_CONFIG)
    _p("sing-box 校验: " + ("通过" if chk["ok"] else "失败"))
    if not chk["ok"]:
        _p(chk["output"][-1200:])
        return 1
    return 0


def cmd_node(args):
    from . import core, generator, nodes
    paths.ensure_dirs()
    if not args:
        return _fail("node 需要子命令: list|import|del|test")
    sub, rest = args[0], args[1:]
    if sub == "list":
        ns = nodes.list_nodes()
        if not ns:
            _p("（暂无节点）")
        for i, n in enumerate(ns, 1):
            addr = ""
            if n.get("cfg"):
                addr = "%s:%s" % (n["cfg"].get("server", ""), n["cfg"].get("server_port", ""))
            lat = "-" if n.get("latency") is None else "%dms" % n["latency"]
            _p("%2d. [%s] %s  %s  %s  id=%s" % (
                i, "启用" if n.get("enabled") else "禁用", n["name"], n["type"], addr, n["id"]))
            _p("    延迟: %s" % lat)
        return 0
    if sub == "import":
        if not rest:
            return _fail("用法: node import <链接...> 或 node import - (stdin，空行结束)")
        if rest == ["-"]:
            # 从 stdin 逐行读到空行为止（不能 read() 到 EOF：
            # 在 manage.sh 菜单里 stdin 与菜单共用，读尽会吞掉后续菜单输入）
            lines = []
            for line in sys.stdin:
                if not line.strip():
                    break
                lines.append(line)
            text = "".join(lines)
        else:
            text = "\n".join(rest)
        parsed, errors = nodes.parse_links(text)
        added = nodes.add_nodes(parsed) if parsed else []
        from . import generator as gen
        gen.generate()
        _p("已导入 %d 个节点" % len(added))
        for e in errors:
            _p("  第%d行失败: %s" % (e["line"], e["error"]))
        return 0 if added else 1
    if sub == "del":
        if not rest:
            return _fail("用法: node del <id>")
        okk = nodes.delete_node(rest[0])
        from . import generator as gen
        gen.generate()
        _p("已删除" if okk else "节点不存在")
        return 0 if okk else 1
    if sub == "test":
        if not rest:
            return _fail("用法: node test <id>")
        r = core.test_latency(generator.node_tag(rest[0]))
        nodes.set_latency(rest[0], r.get("ms"))
        if r.get("ok"):
            _p("延迟: %dms" % r["ms"])
            return 0
        return _fail(r.get("error", "测试失败"))
    return _fail("未知 node 子命令: " + sub)


def cmd_chain(args):
    from . import chains as chains_mod, core, generator
    paths.ensure_dirs()
    if not args:
        return _fail("chain 需要子命令: list|add|del|test")
    sub, rest = args[0], args[1:]
    if sub == "list":
        cs = chains_mod.list_chains()
        if not cs:
            _p("（暂无链式代理）")
        for i, c in enumerate(cs, 1):
            _p("%2d. [%s] %s  id=%s" % (i, "启用" if c.get("enabled") else "禁用", c["name"], c["id"]))
            _p("    路径: %s" % " → ".join(chains_mod.describe(c)))
        return 0
    if sub == "add":
        if len(rest) < 2:
            return _fail("用法: chain add <名称> <成员id,成员id,...>（顺序即流量顺序，最后是出口）")
        members = [m.strip() for m in rest[1].split(",") if m.strip()]
        try:
            c = chains_mod.add(rest[0], members)
        except ValueError as e:
            return _fail(str(e))
        generator.generate()
        _p("已创建链: %s (%s)" % (c["name"], " → ".join(chains_mod.describe(c))))
        return 0
    if sub == "del":
        if not rest:
            return _fail("用法: chain del <id>")
        okk = chains_mod.delete(rest[0])
        generator.generate()
        _p("已删除" if okk else "链不存在")
        return 0 if okk else 1
    if sub == "test":
        if not rest:
            return _fail("用法: chain test <id>")
        tag = generator.chain_public_tag(rest[0])
        if not tag:
            return _fail("链不可用（已禁用，或成员被删除/禁用）")
        r = core.test_egress(tag)
        if r.get("ok"):
            _p("出口 IP: %s (%sms)" % (r.get("ip", ""), r.get("ms", "?")))
            return 0
        return _fail(r.get("error", "测试失败"))
    return _fail("未知 chain 子命令: " + sub)


def cmd_group(args):
    from . import groups
    paths.ensure_dirs()
    if args and args[0] == "list":
        gs = groups.list_groups()
        if not gs:
            _p("（暂无节点组）")
        for i, g in enumerate(gs, 1):
            _p("%2d. [%s] %s (%s) 成员 %d 个  id=%s" % (
                i, "启用" if g.get("enabled") else "禁用", g["name"], g["type"],
                len(g.get("members", [])), g["id"]))
        return 0
    return _fail("用法: group list")


def cmd_sub(args):
    from . import subs
    paths.ensure_dirs()
    if not args:
        return _fail("sub 需要子命令: list|add|refresh")
    sub, rest = args[0], args[1:]
    if sub == "list":
        ss = subs.list_subs()
        if not ss:
            _p("（暂无订阅）")
        for i, s in enumerate(ss, 1):
            import time
            upd = time.strftime("%Y-%m-%d %H:%M", time.localtime(s["updated_at"])) if s.get("updated_at") else "从未"
            _p("%2d. [%s] %s  节点 %d 个  上次更新: %s  id=%s" % (
                i, "启用" if s.get("enabled") else "禁用", s["name"],
                len(s.get("node_ids", [])), upd, s["id"]))
        return 0
    if sub == "add":
        if len(rest) < 2:
            return _fail("用法: sub add <名称> <URL>")
        try:
            s = subs.add(rest[0], rest[1])
        except ValueError as e:
            return _fail(str(e))
        _p("已添加订阅: %s" % s["name"])
        return 0
    if sub == "refresh":
        if rest:
            try:
                r = subs.refresh(rest[0])
            except ValueError as e:
                return _fail(str(e))
            from . import generator
            generator.generate()
            _p("新增 %d / 保留 %d / 移除 %d" % (r["added"], r["kept"], r["removed"]))
            return 0
        results = subs.refresh_all()
        from . import generator
        generator.generate()
        for r in results:
            if r.get("ok"):
                _p("%s: 新增 %d / 保留 %d / 移除 %d" % (r["name"], r["added"], r["kept"], r["removed"]))
            else:
                _p("%s: 失败 %s" % (r["name"], r.get("error")))
        return 0
    return _fail("未知 sub 子命令: " + sub)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        _p(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    try:
        if cmd == "status":
            return cmd_status()
        if cmd in ("start", "stop", "restart"):
            return cmd_core(cmd)
        if cmd == "gen":
            return cmd_gen()
        if cmd == "node":
            return cmd_node(rest)
        if cmd == "chain":
            return cmd_chain(rest)
        if cmd == "group":
            return cmd_group(rest)
        if cmd == "sub":
            return cmd_sub(rest)
    except Exception as e:
        return _fail("%s: %s" % (type(e).__name__, e))
    return _fail("未知命令: " + cmd)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        # 输出被管道截断（如 | head）时安静退出
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
        except OSError:
            pass
        sys.exit(0)
