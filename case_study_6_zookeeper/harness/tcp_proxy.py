#!/usr/bin/env python3
"""
CS6 controllable TCP proxy. Serves as Proxy A (node 2's learner channel to the
leader's quorum port) and Proxy B (client -> node 1). Python stdlib only.

States:
  PASS - forward bytes both ways normally.
  HOLD - blackhole: keep live TCP connections OPEN but stop moving bytes, so the
         peer does not see a close and waits for its own application read timeout.
         Use for Proxy A (follower learner channel) to get the full serving
         window bounded by syncLimit * tickTime.
  CUT  - close all live proxied connections and refuse new ones (immediate FIN).
         Use for Proxy B (client -> node 1) so the client fails over fast.

Control: line-oriented control port. Send one of:
  pass | hold | cut | status

Every state change and connection open/close is logged to stderr with a
millisecond timestamp (explicit partition-state record for the pilot).

Usage:
  python -I tcp_proxy.py --name A --listen 12883 --target 127.0.0.1:2883 --control 13001
  python -I tcp_proxy.py --name B --listen 12181 --target 127.0.0.1:2181 --control 13002
"""
import argparse
import select
import socket
import sys
import threading
import time

STATE = "PASS"
STATE_LOCK = threading.Lock()
LIVE = set()
LIVE_LOCK = threading.Lock()
ACCEPTED = 0
NAME = "?"


def ts():
    t = time.time()
    return time.strftime("%H:%M:%S", time.localtime(t)) + (".%03d" % int((t % 1) * 1000))


def log(msg):
    sys.stderr.write("[%s %s] %s\n" % (ts(), NAME, msg))
    sys.stderr.flush()


def get_state():
    with STATE_LOCK:
        return STATE


def bridge(client, upstream):
    """Pump both directions; forward only while PASS, park while HOLD, stop on CUT."""
    socks = [client, upstream]
    peer = {client: upstream, upstream: client}
    try:
        while True:
            st = get_state()
            if st == "CUT":
                break
            if st == "HOLD":
                time.sleep(0.1)
                continue
            r, _, x = select.select(socks, [], socks, 0.2)
            if x:
                break
            for s in r:
                try:
                    b = s.recv(65536)
                except OSError:
                    return
                if not b:
                    return
                try:
                    peer[s].sendall(b)
                except OSError:
                    return
    finally:
        pass


def handle(client, target_host, target_port):
    global ACCEPTED
    if get_state() == "CUT":
        log("refuse (CUT) from %s" % (client.getpeername(),))
        try:
            client.close()
        except OSError:
            pass
        return
    try:
        upstream = socket.create_connection((target_host, target_port), timeout=5)
    except OSError as e:
        log("dial target failed: %s" % e)
        try:
            client.close()
        except OSError:
            pass
        return
    with LIVE_LOCK:
        LIVE.add(client)
        LIVE.add(upstream)
        ACCEPTED += 1
    log("open conn -> target (live=%d)" % (len(LIVE) // 2))
    try:
        bridge(client, upstream)
    finally:
        with LIVE_LOCK:
            LIVE.discard(client)
            LIVE.discard(upstream)
        for s in (client, upstream):
            try:
                s.close()
            except OSError:
                pass
        log("close conn (live=%d)" % (len(LIVE) // 2))


def cut_live():
    with LIVE_LOCK:
        socks = list(LIVE)
        LIVE.clear()
    for s in socks:
        try:
            s.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            s.close()
        except OSError:
            pass
    log("CUT dropped %d live socket(s)" % (len(socks) // 2))


def control_loop(control_port):
    global STATE
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", control_port))
    srv.listen(8)
    log("control on 127.0.0.1:%d" % control_port)
    while True:
        c, _ = srv.accept()
        try:
            cmd = c.recv(256).decode("utf-8", "replace").strip().lower()
            if cmd in ("pass", "hold", "cut"):
                with STATE_LOCK:
                    STATE = cmd.upper()
                log("STATE -> %s" % STATE)
                if cmd == "cut":
                    cut_live()
                c.sendall(("ok %s\n" % cmd).encode())
            elif cmd == "status":
                with LIVE_LOCK:
                    live = len(LIVE) // 2
                c.sendall(("state=%s live=%d accepted=%d at=%s\n" % (get_state(), live, ACCEPTED, ts())).encode())
            else:
                c.sendall(b"err unknown (pass|hold|cut|status)\n")
        except OSError:
            pass
        finally:
            try:
                c.close()
            except OSError:
                pass


def main():
    global NAME
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="proxy")
    ap.add_argument("--listen", type=int, required=True)
    ap.add_argument("--target", required=True, help="HOST:PORT")
    ap.add_argument("--control", type=int, required=True)
    a = ap.parse_args()
    NAME = a.name
    th, tp = a.target.rsplit(":", 1)
    tp = int(tp)
    threading.Thread(target=control_loop, args=(a.control,), daemon=True).start()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", a.listen))
    srv.listen(64)
    log("listen 127.0.0.1:%d -> %s:%d (state=PASS)" % (a.listen, th, tp))
    while True:
        client, _ = srv.accept()
        threading.Thread(target=handle, args=(client, th, tp), daemon=True).start()


if __name__ == "__main__":
    main()
