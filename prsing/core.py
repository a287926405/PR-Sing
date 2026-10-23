"""sing-box 内核进程管理：启动/停止/重启/状态/测速/出口IP测试。"""

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import time
import urllib.request

from . import paths, settings as settings_mod
from . import generator
from .store import load, save

PID_FILE = os.path.join(paths.CONFIG_DIR, "core.pid")
STATE_FILE = os.path.join(paths.CONFIG_DIR, "core.state.json")


def core_bin():
    s = settings_mod.load()
    p = s.get("core_binary") or paths.SING_BOX_BIN
    return p


def read_state():
    try:
        return load(STATE_FILE, default={})
    except Exception:
        return {}


def write_state(state):
    state["updated_at"] = int(time.time())
    save(STATE_FILE, state)


def _proc_alive(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (ProcessLookupError, ValueError, TypeError):
        return False
    except PermissionError:
        return True


def _read_pid():
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        if _proc_alive(pid):
            return pid
    except Exception:
        pass
    return None


def version():
    try:
        out = subprocess.run([core_bin(), "version"], capture_output=True, text=True, timeout=10)
        return out.stdout.strip().splitlines()[0] if out.stdout.strip() else None
    except Exception as e:
        return "unavailable: %s" % e


def check_config(cfg=None):
    """sing-box check；cfg 为 dict 时先落盘到临时文件。"""
    target = paths.CORE_CONFIG
    if cfg is not None:
        target = paths.CORE_TEST_CONFIG
        save(target, cfg)
    try:
        r = subprocess.run([core_bin(), "check", "-c", target],
                           capture_output=True, text=True, timeout=60)
    except OSError as e:
        return {"ok": False, "code": -1, "output": "内核不可用: %s" % e}
    return {
        "ok": r.returncode == 0,
        "code": r.returncode,
        "output": (r.stdout + "\n" + r.stderr).strip()[-8000:],
    }


def start(settings=None):
    if get_pid():
        return {"ok": True, "detail": "already running", "pid": get_pid()}
    cfg = generator.generate(settings)
    chk = check_config(cfg)
    if not chk["ok"]:
        return {"ok": False, "detail": "config invalid", "output": chk["output"][-4000:]}
    binp = core_bin()
    if not os.path.isfile(binp) or not os.access(binp, os.X_OK):
        return {"ok": False, "detail": "sing-box 二进制不可用: %s" % binp}
    logf = open(paths.CORE_LOG, "ab")
    proc = subprocess.Popen(
        [binp, "run", "-c", paths.CORE_CONFIG],
        stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    logf.close()
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))
    # 等待启动：配置已通过 check，进程存活满 1 秒即视为启动成功；
    # 只有在 6 秒内提前退出才判定失败（不再无条件等满 6 秒）。
    for i in range(12):
        time.sleep(0.5)
        if proc.poll() is not None:
            with open(paths.CORE_LOG, "rb") as f:
                tail = f.read()[-4000:].decode("utf-8", "replace")
            return {"ok": False, "detail": "进程退出 code=%s" % proc.returncode,
                    "output": tail}
        if i >= 1:
            break
    write_state({"running": True, "pid": proc.pid,
                 "started_at": int(time.time()),
                 "version": version()})
    return {"ok": True, "detail": "started", "pid": proc.pid}


def stop():
    pid = get_pid()
    if not pid:
        write_state({"running": False, "pid": None})
        return {"ok": True, "detail": "not running"}
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    for _ in range(20):
        time.sleep(0.3)
        if not _proc_alive(pid):
            break
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
    try:
        os.unlink(PID_FILE)
    except FileNotFoundError:
        pass
    write_state({"running": False, "pid": None, "stopped_at": int(time.time())})
    return {"ok": True, "detail": "stopped"}


def restart():
    stop()
    time.sleep(0.5)
    return start()


def get_pid():
    return _read_pid()


def status():
    s = settings_mod.load()
    pid = get_pid()
    running = bool(pid)
    # 检查面板端口是否活着（mixed 或 TUN 不可探测，用日志兜底）
    st = read_state()
    info = {
        "running": running,
        "pid": pid,
        "started_at": st.get("started_at"),
        "version": st.get("version") or (version() if not running else st.get("version")),
        "tun_enabled": s.get("tun_enabled", True),
        "tun_interface": s.get("tun_interface") or "tun0",
        "mixed_enabled": s.get("mixed_enabled", True),
        "mixed_port": s.get("mixed_port") or 2080,
        "route_mode": s.get("route_mode"),
        "dns_mode": s.get("dns_mode"),
        "core_bin": core_bin(),
        "core_bin_ok": os.path.isfile(core_bin()),
        "config": paths.CORE_CONFIG,
        "log": paths.CORE_LOG,
    }
    if running and s.get("tun_enabled"):
        info["tun_present"] = os.path.isdir("/sys/class/net/%s" % (s.get("tun_interface") or "tun0"))
    return info


def logs(n=200):
    try:
        with open(paths.CORE_LOG, "rb") as f:
            data = f.read()
        lines = data.decode("utf-8", "replace").splitlines()
        return {"ok": True, "lines": lines[-n:], "size": len(data)}
    except FileNotFoundError:
        return {"ok": True, "lines": [], "size": 0}


def _free_port():
    so = socket.socket()
    so.bind(("127.0.0.1", 0))
    p = so.getsockname()[1]
    so.close()
    return p


def _run_singbox(cfg, timeout):
    """起临时 sing-box 实例（无 TUN），返回 (proc, log_path, http_proxy)。

    只替换入站为随机端口的 mixed 入站；route 必须原样保留——
    generate_test_config 已把 final 设为被测节点/链的 tag，
    覆盖 route 会让测速/出口 IP 测试实际走直连，结果全错。
    """
    port = _free_port()
    cfg["inbounds"] = [
        {"type": "mixed", "tag": "test-in", "listen": "127.0.0.1", "listen_port": port},
    ]
    log_path = paths.CORE_LOG + ".test"
    # sing-box 的 -c 不支持从 stdin（"-"）读配置，必须落盘到文件再启动；
    # 此前传 stdin 导致测试实例必然 FATAL: open -: no such file or directory
    save(paths.CORE_TEST_CONFIG, cfg)
    logf = open(log_path, "ab")
    proc = subprocess.Popen([core_bin(), "run", "-c", paths.CORE_TEST_CONFIG],
                            stdout=logf, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, start_new_session=True)
    logf.close()
    return proc, log_path, port


def _stop_proc(proc):
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    except Exception:
        pass


def _curl_via_proxy(port, url="https://api.ipify.org", timeout=20):
    proxy = "http://127.0.0.1:%d" % port
    req = urllib.request.Request(url, headers={"User-Agent": "pr-sing-test",
                                               "Connection": "close"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(
        {"http": proxy, "https": proxy}))
    t0 = time.time()
    try:
        with opener.open(req, timeout=timeout) as resp:
            body = resp.read(2048).decode("utf-8", "replace").strip()
        ms = int((time.time() - t0) * 1000)
        return {"ok": True, "body": body, "ms": ms}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def test_egress(tag, settings=None, probe="https://api.ipify.org"):
    """通过指定 tag 出口测公网 IP（链 = 整条链路）。"""
    cfg = generator.generate_test_config(tag, settings, write=False)
    # 去掉 TUN（测试配置本来就没有），确保 mixed 可用
    proc, log_path, port = _run_singbox(cfg, 60)
    try:
        time.sleep(1.2)
        if proc.poll() is not None:
            with open(log_path, "rb") as f:
                tail = f.read()[-3000:].decode("utf-8", "replace")
            return {"ok": False, "error": "测试实例启动失败", "log": tail}
        r = _curl_via_proxy(port, probe)
        if r["ok"] and re.match(r"^\d+\.\d+\.\d+\.\d+$", r.get("body", "")):
            r["ip"] = r["body"]
        elif r["ok"]:
            # 非 IP 返回（可能命中了 CDN 节点信息页），仍返回但标记
            r["ip"] = r.get("body", "")[:120]
        return r
    finally:
        _stop_proc(proc)


def test_latency(tag, settings=None, url="https://www.gstatic.com/generate_204"):
    """节点/链延迟测试。"""
    cfg = generator.generate_test_config(tag, settings, write=False)
    proc, log_path, port = _run_singbox(cfg, 60)
    try:
        time.sleep(1.2)
        if proc.poll() is not None:
            with open(log_path, "rb") as f:
                tail = f.read()[-3000:].decode("utf-8", "replace")
            return {"ok": False, "error": "测试实例启动失败", "log": tail}
        proxy = "http://127.0.0.1:%d" % port
        best = None
        for _ in range(3):
            req = urllib.request.Request(url, headers={"User-Agent": "pr-sing-test",
                                                       "Connection": "close"})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler(
                {"http": proxy, "https": proxy}))
            t0 = time.time()
            try:
                with opener.open(req, timeout=8) as resp:
                    resp.read(256)
                ms = int((time.time() - t0) * 1000)
                if best is None or ms < best:
                    best = ms
            except Exception:
                time.sleep(0.3)
        if best is not None:
            return {"ok": True, "ms": best}
        return {"ok": False, "error": "timeout"}
    finally:
        _stop_proc(proc)


def ensure_core():
    """确保内核二进制存在，不存在则报清晰错误（自动下载见 install.sh）。"""
    p = core_bin()
    if os.path.isfile(p) and os.access(p, os.X_OK):
        return {"ok": True, "bin": p}
    return {"ok": False, "bin": p,
            "error": "未找到 sing-box，请运行 install.sh 或在设置中指定 core_bin"}
