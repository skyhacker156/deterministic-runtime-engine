#!/usr/bin/env python3
"""
CS7 (C1) external protected resource. Python stdlib only. Decoupled from the
Java/Curator clients (line-oriented TCP), so the resource's enforcement is
independent of the lock library.

Pre-registration: CS7_C1_PREREGISTRATION.md (cs7-c1).

The resource holds a single value and (in fenced mode) the highest fencing
token it has accepted. It is the component that does — or does not — enforce
external write authority.

Modes:
  unfenced : accept every write (Arm U). Models a resource that trusts the
             lock and performs no token check.
  fenced   : accept a write only if its token is strictly greater than the
             highest token accepted so far; else reject (Arm F). The compare-
             and-update is atomic (single lock), so B's newer token, once
             presented, permanently locks out A's older token.

Line protocol (one request per line, reply is one line):
  WRITE <clientId> <token> <value>
      unfenced -> "OK accepted clientId=<..> token=<..> value=<..>"
      fenced   -> "OK accepted ..."  or  "REJECT stale token=<t> <= highest=<h>"
  GET            -> "VALUE value=<..> highest=<..> writer=<..>"
  RESET          -> clears value/highest/log (between trials) -> "OK reset"
  LOG            -> dumps one JSON object per recorded attempt, then "END"

Every write attempt is logged (timestamp, clientId, token, decision, value).

Usage:
  python -I resource.py --mode unfenced --listen 14000
  python -I resource.py --mode fenced   --listen 14000
"""
import argparse
import json
import socket
import sys
import threading
import time

LOCK = threading.Lock()
STATE = {"value": "(none)", "highest": -1, "writer": "(none)"}
ATTEMPTS = []  # list of dicts
MODE = "unfenced"
NAME = "resource"


def ts():
    t = time.time()
    return time.strftime("%H:%M:%S", time.localtime(t)) + (".%03d" % int((t % 1) * 1000))


def log(msg):
    sys.stderr.write("[%s %s] %s\n" % (ts(), NAME, msg))
    sys.stderr.flush()


def handle_write(client_id, token, value):
    """Atomic compare-and-set under one lock. Returns (accepted, reply)."""
    with LOCK:
        now_ms = int(time.time() * 1000)
        if MODE == "fenced":
            accepted = token > STATE["highest"]
        else:
            accepted = True
        if accepted:
            STATE["value"] = value
            STATE["writer"] = client_id
            if token > STATE["highest"]:
                STATE["highest"] = token
            reply = "OK accepted clientId=%s token=%d value=%s" % (client_id, token, value)
        else:
            reply = "REJECT stale token=%d <= highest=%d" % (token, STATE["highest"])
        ATTEMPTS.append({
            "t_ms": now_ms, "clientId": client_id, "token": token,
            "value": value, "accepted": accepted,
            "highestAfter": STATE["highest"], "mode": MODE,
        })
        log("WRITE clientId=%s token=%d value=%s -> %s" % (client_id, token, value, "ACCEPT" if accepted else "REJECT"))
        return accepted, reply


def handle(conn):
    try:
        f = conn.makefile("rwb", buffering=0)
        for raw in f:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            parts = line.split(" ", 3)
            cmd = parts[0].upper()
            if cmd == "WRITE" and len(parts) == 4:
                client_id = parts[1]
                try:
                    token = int(parts[2])
                except ValueError:
                    f.write(b"ERR bad token\n"); continue
                value = parts[3]
                _, reply = handle_write(client_id, token, value)
                f.write((reply + "\n").encode())
            elif cmd == "GET":
                with LOCK:
                    f.write(("VALUE value=%s highest=%d writer=%s\n"
                             % (STATE["value"], STATE["highest"], STATE["writer"])).encode())
            elif cmd == "RESET":
                with LOCK:
                    STATE["value"] = "(none)"; STATE["highest"] = -1; STATE["writer"] = "(none)"
                    ATTEMPTS.clear()
                log("RESET")
                f.write(b"OK reset\n")
            elif cmd == "LOG":
                with LOCK:
                    snap = list(ATTEMPTS)
                for a in snap:
                    f.write((json.dumps(a) + "\n").encode())
                f.write(b"END\n")
            else:
                f.write(b"ERR unknown (WRITE|GET|RESET|LOG)\n")
    except OSError:
        pass
    finally:
        try:
            conn.close()
        except OSError:
            pass


def main():
    global MODE, NAME
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["unfenced", "fenced"], default="unfenced")
    ap.add_argument("--listen", type=int, required=True)
    ap.add_argument("--name", default="resource")
    a = ap.parse_args()
    MODE = a.mode
    NAME = a.name
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", a.listen))
    srv.listen(16)
    log("listening 127.0.0.1:%d mode=%s" % (a.listen, MODE))
    while True:
        conn, _ = srv.accept()
        threading.Thread(target=handle, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
