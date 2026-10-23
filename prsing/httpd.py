"""面板 HTTP 服务：API + 静态文件 + 登录鉴权（纯标准库）。"""

import json
import os
import secrets
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import core, generator, groups, nodes, paths, rules
from . import settings as settings_mod
from . import store, subs

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
_PANEL_PID_FILE = os.path.join(paths.CONFIG_DIR, "panel.pid")


def _make_token():
    return settings_mod.make_session_token(settings_mod.load())


def _valid_token(t):
    if not t:
        return False
    return settings_mod.check_session_token(settings_mod.load(), t)


def _regen_config():
    try:
        generator.generate()
        return True
    except Exception as e:
        return False


def _check_password(password: str) -> bool:
    return settings_mod.verify_password(settings_mod.load(), password or "")


def serve(listen: str, port: int):
    try:
        with open(_PANEL_PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    httpd = ThreadingHTTPServer((listen, port), Handler)
    print("[pr-sing] panel listening on %s:%d" % (listen, port), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            os.unlink(_PANEL_PID_FILE)
        except Exception:
            pass


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "PR-Sing"

    # ---------- 基础 ----------
    def log_message(self, fmt, *args):
        pass  # 静默，避免日志刷屏

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, obj):
        self._send(code, obj)

    def _err(self, code, msg):
        self._json(code, {"ok": False, "error": msg})

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    def _authed(self):
        h = self.headers.get("Authorization") or ""
        if h.startswith("Bearer "):
            return _valid_token(h[7:].strip())
        return False

    # ---------- 路由 ----------
    def do_GET(self):
        try:
            self._route("GET")
        except BrokenPipeError:
            pass
        except Exception:
            self._traceback()

    def do_POST(self):
        try:
            self._route("POST")
        except BrokenPipeError:
            pass
        except Exception:
            self._traceback()

    def do_PUT(self):
        try:
            self._route("PUT")
        except BrokenPipeError:
            pass
        except Exception:
            self._traceback()

    def do_DELETE(self):
        try:
            self._route("DELETE")
        except BrokenPipeError:
            pass
        except Exception:
            self._traceback()

    def _traceback(self):
        tb = traceback.format_exc()
        try:
            self._err(500, "internal error\n" + tb[-2000:])
        except Exception:
            pass

    def _route(self, method):
        url = urllib.parse.urlparse(self.path)
        p = url.path
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}

        if p == "/api/login" and method == "POST":
            b = self._body() or {}
            if _check_password(b.get("password", "")):
                self._json(200, {"ok": True, "token": _make_token()})
            else:
                self._err(401, "密码错误")
            return

        if p.startswith("/api/"):
            if not self._authed():
                self._err(401, "未登录")
                return
            self._api(method, p, q)
            return

        # 静态文件
        if p == "/" or p == "/index.html":
            p = "/index.html"
        fpath = os.path.normpath(os.path.join(STATIC_DIR, p.lstrip("/")))
        if not fpath.startswith(STATIC_DIR) or not os.path.isfile(fpath):
            self._err(404, "not found")
            return
        ext = os.path.splitext(fpath)[1].lower()
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
        }.get(ext, "application/octet-stream")
        with open(fpath, "rb") as f:
            self._send(200, f.read(), ctype)

    # ---------- API ----------
    def _api(self, method, p, q):
        b = self._body() if method in ("POST", "PUT") else (q or {})
        if b is None:
            self._err(400, "invalid json")
            return
        try:
            self._dispatch(method, p, b)
        except ValueError as e:
            self._err(400, str(e))
        except Exception as e:
            self._err(500, "%s: %s" % (type(e).__name__, e))

    def _dispatch(self, method, p, b):
        # ---- 状态 ----
        if p == "/api/status":
            s = settings_mod.load()
            from . import chains as chains_mod
            self._json(200, {
                "ok": True,
                "version": __import__("prsing").__version__,
                "core": core.status(),
                "rules": rules.status(),
                "counts": {
                    "nodes": len(nodes.list_nodes()),
                    "chains": len(chains_mod.list_chains()),
                    "groups": len(groups.list_groups()),
                    "subs": len(subs.list_subs()),
                },
                "panel": {
                    "listen": s.get("panel_listen"),
                    "port": s.get("panel_port"),
                    "core_binary": s.get("core_binary"),
                },
            })
            return

        if p == "/api/logs":
            self._json(200, core.logs(int(b.get("n", "200") or 200)))
            return

        # ---- 节点 ----
        if p == "/api/nodes" and method == "GET":
            self._json(200, {"ok": True, "nodes": nodes.list_nodes()})
            return
        if p == "/api/nodes/parse" and method == "POST":
            text = b.get("text", "")
            parsed, errors = nodes.parse_links(text)
            self._json(200, {"ok": True, "parsed": parsed, "errors": errors})
            return
        if p == "/api/nodes/import" and method == "POST":
            text = b.get("text", "")
            parsed, errors = nodes.parse_links(text)
            added = nodes.add_nodes(parsed) if parsed else []
            self._json(200, {"ok": True, "added": len(added),
                             "node_ids": [n["id"] for n in added], "errors": errors})
            _regen_config()
            return
        if p == "/api/nodes" and method == "POST":
            item = b.get("node") or b
            if not item.get("type") or not item.get("cfg"):
                self._err(400, "需要 type 和 cfg 字段")
                return
            added = nodes.add_nodes([item])
            self._json(200, {"ok": True, "node": added[0]})
            _regen_config()
            return
        if p.startswith("/api/nodes/") and p.endswith("/latency") and method == "POST":
            nid = p.split("/")[3]
            r = core.test_latency(generator.node_tag(nid))
            nodes.set_latency(nid, r.get("ms"))
            self._json(200, r)
            return
        if p.startswith("/api/nodes/") and method == "GET":
            n = nodes.get_node(p.split("/")[3])
            self._json(200 if n else 404, {"ok": n is not None, "node": n})
            return
        if p.startswith("/api/nodes/") and method in ("PUT", "POST"):
            nid = p.split("/")[3]
            n = nodes.update_node(nid, b)
            self._json(200 if n else 404, {"ok": n is not None, "node": n})
            _regen_config()
            return
        if p.startswith("/api/nodes/") and method == "DELETE":
            ok = nodes.delete_node(p.split("/")[3])
            self._json(200, {"ok": ok})
            _regen_config()
            return

        # ---- 订阅 ----
        if p == "/api/subs" and method == "GET":
            self._json(200, {"ok": True, "subs": subs.list_subs()})
            return
        if p == "/api/subs" and method == "POST":
            sub = subs.add(b.get("name", ""), b.get("url", ""),
                           b.get("enabled", True))
            self._json(200, {"ok": True, "sub": sub})
            return
        if p == "/api/subs/refresh" and method == "POST":
            sid = b.get("id")
            r = subs.refresh(sid) if sid else {"results": subs.refresh_all()}
            self._json(200, {"ok": True, "result": r})
            _regen_config()
            return
        if p.startswith("/api/subs/") and method in ("PUT", "POST"):
            sub = subs.update(p.split("/")[3], b)
            self._json(200 if sub else 404, {"ok": sub is not None, "sub": sub})
            return
        if p.startswith("/api/subs/") and method == "DELETE":
            ok = subs.delete(p.split("/")[3])
            self._json(200, {"ok": ok})
            _regen_config()
            return

        # ---- 链式代理 ----
        if p == "/api/chains" and method == "GET":
            out = []
            from . import chains as chains_mod
            for c in chains_mod.list_chains():
                c2 = dict(c)
                c2["describe"] = chains_mod.describe(c)
                out.append(c2)
            self._json(200, {"ok": True, "chains": out})
            return
        if p == "/api/chains" and method == "POST":
            from . import chains as chains_mod
            c = chains_mod.add(b.get("name", ""), b.get("members", []),
                               b.get("note", ""), b.get("enabled", True))
            self._json(200, {"ok": True, "chain": c})
            _regen_config()
            return
        if p.startswith("/api/chains/") and p.endswith("/egress") and method == "POST":
            from . import chains as chains_mod
            cid = p.split("/")[3]
            c = chains_mod.get(cid)
            if not c:
                self._err(404, "chain not found")
                return
            tag = generator.chain_public_tag(cid)
            if not tag:
                self._err(400, "链不可用（已禁用，或成员被删除/禁用）")
                return
            r = core.test_egress(tag)
            self._json(200, r)
            return
        if p.startswith("/api/chains/") and method in ("PUT", "POST"):
            from . import chains as chains_mod
            c = chains_mod.update(p.split("/")[3], b)
            self._json(200 if c else 404, {"ok": c is not None, "chain": c})
            _regen_config()
            return
        if p.startswith("/api/chains/") and method == "DELETE":
            from . import chains as chains_mod
            ok = chains_mod.delete(p.split("/")[3])
            self._json(200, {"ok": ok})
            _regen_config()
            return

        # ---- 节点组 ----
        if p == "/api/groups" and method == "GET":
            self._json(200, {"ok": True, "groups": groups.list_groups()})
            return
        if p == "/api/groups" and method == "POST":
            g = groups.add(b.get("name", ""), b.get("type", "selector"),
                           b.get("members", []), b.get("default", ""),
                           b.get("url", "https://www.gstatic.com/generate_200"),
                           int(b.get("interval", 300) or 300),
                           int(b.get("tolerance", 50) or 50))
            self._json(200, {"ok": True, "group": g})
            _regen_config()
            return
        if p.startswith("/api/groups/") and method in ("PUT", "POST"):
            g = groups.update(p.split("/")[3], b)
            self._json(200 if g else 404, {"ok": g is not None, "group": g})
            _regen_config()
            return
        if p.startswith("/api/groups/") and method == "DELETE":
            ok = groups.delete(p.split("/")[3])
            self._json(200, {"ok": ok})
            _regen_config()
            return

        # ---- 设置 ----
        if p == "/api/settings" and method == "GET":
            s = dict(settings_mod.load())
            s.pop("panel_password_hash", None)
            s.pop("panel_password_salt", None)
            self._json(200, {"ok": True, "settings": s})
            return
        if p == "/api/settings" and method in ("POST", "PUT"):
            s = settings_mod.load()
            for k, v in b.items():
                if k in ("panel_password_hash", "panel_password_salt"):
                    continue
                s[k] = v
            settings_mod.save(s)
            _regen_config()
            self._json(200, {"ok": True})
            return
        if p == "/api/password" and method == "POST":
            err = settings_mod.set_password(
                settings_mod.load(), b.get("old", ""), b.get("password", ""))
            if err:
                self._err(400, err)
            else:
                self._json(200, {"ok": True})
            return

        # ---- 内核控制 ----
        if p == "/api/core/start" and method == "POST":
            self._json(200, core.start())
            return
        if p == "/api/core/stop" and method == "POST":
            self._json(200, core.stop())
            return
        if p == "/api/core/restart" and method == "POST":
            self._json(200, core.restart())
            return
        if p == "/api/core/regen" and method == "POST":
            ok = _regen_config()
            chk = core.check_config() if ok else None
            self._json(200, {"ok": ok, "check": chk})
            return

        # ---- 规则库 ----
        if p == "/api/rules/status" and method == "GET":
            self._json(200, {"ok": True, "status": rules.status()})
            return
        if p == "/api/rules/update" and method == "POST":
            r = rules.ensure_all()
            self._json(200, {"ok": True, "result": r})
            _regen_config()
            return

        self._err(404, "no route: %s %s" % (method, p))


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    listen = args[0] if len(args) > 0 else "0.0.0.0"
    port = int(args[1]) if len(args) > 1 else 3001
    serve(listen, port)
