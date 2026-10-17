#!/usr/bin/env python3
"""
CS6 / CS6-SF1 controllable TCP proxy. Serves as Proxy A (node 2's learner
channel to the leader's quorum port) and Proxy B (client -> node 1).
Python stdlib only.

States:
  PASS  - forward bytes both ways normally.
  HOLD  - blackhole: keep live TCP connections OPEN but stop moving bytes, so the
          peer does not see a close and waits for its own application read timeout.
          Use for Proxy A (follower learner channel) to get the full serving
          window bounded by syncLimit * tickTime. (CS6)
  CUT   - close all live proxied connections and refuse new ones (immediate FIN).
          Use for Proxy B (client -> node 1) so the client fails over fast. (CS6)
  DELAY - forward both ways but add DELAY_MS latency to the upstream->client
          direction ONLY, keeping the connection open and quorum intact. (CS6-SF1)
          On Proxy A, upstream = leader and client = node 2 (the learner dials in),
          so this delays leader->follower traffic (proposals/commits): node 2 lags
          on Z while still connected and revalidation-capable. The follower->leader
          direction (ACKs, ping responses) stays immediate so the leader keeps the
          follower in its view. Keep DELAY_MS < syncLimit * tickTime (with margin)
          or the follower drops out of quorum -- the usable band is found in the
          SF1 pilot (CS6_SF1_PLAN.md, hash 2580427C).

Control: line-oriented control port. Send one of:
  pass | hold | cut | delay <ms> | status

Every state change and connection open/close is logged to stderr with a
millisecond timestamp (explicit partition/delay-state record for the pilot).

Usage:
  python -I tcp_proxy.py --name A --listen 12883 --target 127.0.0.1:2883 --control 13001
  python -I tcp_proxy.py --name B --listen 12181 --target 127.0.0.1:2181 --control 13002

Control examples (node 2 learner channel, Proxy A on 13001):
  printf 'delay 1500\n' | <send to 127.0.0.1:13001>   # lag leader->follower by 1.5s
  printf 'pass\n'       | <send to 127.0.0.1:13001>   # recover (full speed)
"""
import argparse
import collections
import select
import socket
import sys
import threading
import time

STATE = "PASS"
DELAY_MS = 0
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
    """Pump both directions.
       PASS : forward both immediately.
       HOLD : park (no bytes either way); connections stay open.
       CUT  : stop (sockets are closed by cut_live).
       DELAY: client->upstream immediate; upstream->client held by DELAY_MS.
    On Proxy A, client = node 2 (learner, dialed in), upstream = leader, so the
    delayed direction is leader->follower. Single thread per connection: the
    delayed direction uses an in-loop timed queue, so the prompt direction is
    never blocked by the delay."""
    socks = [client, upstream]
    dq = collections.deque()  # (due_monotonic, bytes) pending for upstream->client
    try:
        while True:
            st = get_state()
            if st == "CUT":
                break
            if st == "HOLD":
                time.sleep(0.1)
                continue

            # Wake early enough to flush the next delayed chunk on time.
            now = time.monotonic()
            if dq:
                timeout = max(0.0, min(0.2, dq[0][0] - now))
            else:
                timeout = 0.2

            r, _, x = select.select(socks, [], socks, timeout)
            if x:
                break
            for s in r:
                try:
                    b = s.recv(65536)
                except OSError:
                    return
                if not b:
                    return
                if s is client:
                    # follower -> leader: always immediate
                    try:
                        upstream.sendall(b)
                    except OSError:
                        return
                else:
                    # leader -> follower: delay by DELAY_MS while in DELAY, else immediate
                    d = DELAY_MS if get_state() == "DELAY" else 0
                    dq.append((time.monotonic() + d / 1000.0, b))

            # Flush any upstream->client chunks whose delay has elapsed (FIFO, ordered).
            now = time.monotonic()
            while dq and dq[0][0] <= now:
                try:
                    client.sendall(dq.popleft()[1])
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
    global STATE, DELAY_MS
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", control_port))
    srv.listen(8)
    log("control on 127.0.0.1:%d" % control_port)
    while True:
        c, _ = srv.accept()
        try:
            cmd = c.recv(256).decode("utf-8", "replace").strip().lower()
            parts = cmd.split()
            head = parts[0] if parts else ""
            if head in ("pass", "hold", "cut"):
                with STATE_LOCK:
                    STATE = head.upper()
                log("STATE -> %s" % get_state())
                if head == "cut":
                    cut_live()
                c.sendall(("ok %s\n" % head).encode())
            elif head == "delay":
                try:
                    ms = int(parts[1])
                    if ms < 0:
                        raise ValueError
                except (IndexError, ValueError):
                    c.sendall(b"err usage: delay <ms>  (non-negative integer)\n")
                else:
                    with STATE_LOCK:
                        STATE = "DELAY"
                        DELAY_MS = ms
                    log("STATE -> DELAY (%d ms; upstream->client / leader->follower)" % ms)
                    c.sendall(("ok delay %d\n" % ms).encode())
            elif head == "status":
                with LIVE_LOCK:
                    live = len(LIVE) // 2
                with STATE_LOCK:
                    st, dms = STATE, DELAY_MS
                c.sendall(("state=%s delay_ms=%d live=%d accepted=%d at=%s\n"
                           % (st, dms, live, ACCEPTED, ts())).encode())
            else:
                c.sendall(b"err unknown (pass|hold|cut|delay <ms>|status)\n")
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
