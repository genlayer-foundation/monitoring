#!/usr/bin/env python3
"""Poll unhardcoded's per-key usage report and log each NEW request as one JSON line.

Foundation node only (2026-11-03). The node's LLM rotation sends
`profile:default` to unhardcoded, whose router picks the real model; GenVM never
shows that choice to the node, but the router's own report does. This script
keeps the key ON THE NODE: it reads UNHARDCODEDKEY from the node's .env, calls
GET https://router.ygr.ai/v1/usage, and appends to a file Alloy already ships
(LOG_FILE_PATTERN=/var/log/genlayer/node*.log). Grafana only reads Loki.

Lines:
  {"event":"router_request", ...one per request not seen before}
  {"event":"router_totals", ...one per run: lifetime requests/errors/cost}

First run seeds the seen-set WITHOUT emitting requests, so history is not
re-stamped as "now". Run by systemd timer unhardcoded-usage-poll.timer (5 min).
Best-effort: any failure exits non-zero and is retried next tick.
"""
import hashlib
import json
import os
import sys
import time
import urllib.request

ENV_FILE = "/opt/genlayer-node/.env"
OUT = "/opt/genlayer-node/data/node/logs/node-llm-unhardcoded.log"
STATE = "/opt/genlayer-node/llm-telemetry/unhardcoded-seen.json"
URL = "https://router.ygr.ai/v1/usage"  # default window: last 100 requests
MAX_BYTES = 20 * 1024 * 1024
KEEP_SEEN = 1000


def read_key():
    with open(ENV_FILE) as f:
        for line in f:
            if line.startswith("UNHARDCODEDKEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("UNHARDCODEDKEY not in " + ENV_FILE)


def fingerprint(r):
    raw = json.dumps([r.get(k) for k in ("ts", "status", "served_model_id", "provider",
                                          "tokens_in", "tokens_out", "cost_usd",
                                          "requested_model", "error_kind")])
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)) if ts else None


def main():
    req = urllib.request.Request(URL, headers={"Authorization": "Bearer " + read_key(),
                                               "User-Agent": "genlayer-foundation-node-telemetry"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        usage = json.load(resp)

    try:
        with open(STATE) as f:
            seen = json.load(f)
        first_run = False
    except (OSError, ValueError):
        seen, first_run = [], True
    seen_set = set(seen)

    lines = []
    for r in sorted(usage.get("recent") or [], key=lambda r: r.get("ts") or 0):
        if r.get("event") not in (None, "request"):
            continue
        fp = fingerprint(r)
        if fp in seen_set:
            continue
        seen.append(fp)
        seen_set.add(fp)
        if first_run:
            continue
        lines.append({
            "event": "router_request",
            "time": iso(r.get("ts")),
            "ts": r.get("ts"),
            "status": r.get("status"),
            "ok": isinstance(r.get("status"), int) and 200 <= r["status"] < 300,
            "requested_model": r.get("requested_model"),
            "served_model": r.get("served_model_id"),
            "model_family": r.get("model_family"),
            "upstream": r.get("provider"),
            "latency_ms": r.get("latency_ms"),
            "tokens_in": r.get("tokens_in"),
            "tokens_out": r.get("tokens_out"),
            "tokens_total": r.get("tokens_total"),
            "cost_usd": r.get("cost_usd"),
            "error_kind": r.get("error_kind"),
            "error_type": r.get("error_type"),
        })

    t = usage.get("totals") or {}
    lines.append({
        "event": "router_totals",
        "time": iso(int(time.time())),
        "requests": t.get("requests"),
        "errors": t.get("errors"),
        "tokens_total": t.get("tokens_total"),
        "cost_usd": (usage.get("cost_estimate") or {}).get("usd"),
        "seeded": first_run,
    })

    try:
        if os.path.getsize(OUT) > MAX_BYTES:
            os.replace(OUT, OUT + ".1")  # ".1" does not match node*.log
    except OSError:
        pass
    with open(OUT, "a") as f:
        for line in lines:
            f.write(json.dumps({k: v for k, v in line.items() if v is not None},
                               separators=(",", ":")) + "\n")

    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(seen[-KEEP_SEEN:], f)
    os.replace(tmp, STATE)
    print(f"{'seeded' if first_run else 'ok'}: {len(lines) - 1} new request(s)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 — log and let the timer retry
        print(f"unhardcoded usage poll failed: {e}", file=sys.stderr)
        sys.exit(1)
