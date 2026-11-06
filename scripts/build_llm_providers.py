#!/usr/bin/env python3
"""Build dashboards/foundation/llm_providers.json — "GenLayer Foundation | LLM Providers".

What the Foundation node's LLM rotation is actually doing: calls per provider,
failures/timeouts, latency, how often the rotation falls back, and — for
unhardcoded — which upstream model really served each call.

Two sources:

1. Loki, file `/var/log/genlayer/node-llm-calls.log` on validator
   `genlayer-foundation-bradbury-1`. Written by OUR instrumented copy of
   `genvm-llm-rotate.lua` on the node (one JSON line per provider attempt,
   `event="attempt"`, and one per prompt, `event="prompt"`). Alloy ships it
   because the node's LOG_FILE_PATTERN is `/var/log/genlayer/node*.log`.
   Fields: time event tx_id session lead attempt fallback provider model format
   images ok ms timeout_s http_status error_kind error attempts providers_tried
   tokens_in tokens_out tokens_total cost_usd.
   ⚠️ A node upgrade replaces the Lua and silences these panels — re-apply it.

2. Loki, file `/var/log/genlayer/node-llm-unhardcoded.log` on the same node.
   Written every 5 min by `/opt/genlayer-node/llm-telemetry/unhardcoded-usage-poll.py`
   (systemd `unhardcoded-usage-poll.timer`), which reads the node's own
   UNHARDCODEDKEY and logs each NEW request from unhardcoded's per-key report
   `GET https://router.ygr.ai/v1/usage` (`event="router_request"`: served_model,
   upstream, status, ok, latency_ms, tokens_*, cost_usd) plus one
   `event="router_totals"` per poll. The key never leaves the node — Grafana
   only reads Loki. This is the only place the served model exists: GenVM hands
   Lua the `usage` block, not the router's `x_router`. Loki stamps a line when
   Alloy reads it, so a request shows up to ~6 min after it happened.

Run:  python3 scripts/build_llm_providers.py
"""
import json
import os

UID = "gl-llm-providers"
TITLE = "GenLayer Foundation | LLM Providers"
LOKI = {"type": "loki", "uid": "grafanacloud-logs"}

SEL = '{validator_name="$validator", filename="/var/log/genlayer/node-llm-calls.log"}'
ATTEMPT = SEL + ' | json | __error__="" | event="attempt"'
PROMPT = SEL + ' | json | __error__="" | event="prompt"'
UHSEL = '{validator_name="$validator", filename="/var/log/genlayer/node-llm-unhardcoded.log"}'
ROUTER = UHSEL + ' | json | __error__="" | event="router_request"'
TOTALS = UHSEL + ' | json | __error__="" | event="router_totals"'
TIMEOUT = 'error_kind=~"timeout|gateway_timeout" or error=~"(?i).*time.?out.*"'

# Portal health palette (frontend/src/lib/validatorHealth.js) for status colours.
GREEN, YELLOW, ORANGE, RED, GREY, NEUTRAL = (
    "#10b981", "#fbbf24", "#f97316", "#ef4444", "#9ca3af", "#6b7280")

_id = [0]


def nid():
    _id[0] += 1
    return _id[0]


def loki(expr, ref="A", instant=False, legend="", fmt=None):
    t = {"datasource": LOKI, "editorMode": "code", "expr": expr, "refId": ref,
         "legendFormat": legend, "queryType": "instant" if instant else "range"}
    if fmt:
        t["format"] = fmt
    return t


def fixed(color):
    return {"fixedColor": color, "mode": "fixed"}


def by_name(name, *props):
    return {"matcher": {"id": "byName", "options": name},
            "properties": [{"id": k, "value": v} for k, v in props]}


def by_ref(ref, *props):
    return {"matcher": {"id": "byFrameRefID", "options": ref},
            "properties": [{"id": k, "value": v} for k, v in props]}


def row(title, y, collapsed=False):
    return {"type": "row", "title": title, "id": nid(), "collapsed": collapsed,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "panels": []}


def stat(title, desc, targets, pos, unit="none", overrides=(), decimals=0,
         thresholds=None, color="text"):
    defaults = {"unit": unit, "decimals": decimals, "noValue": "0"}
    if thresholds:
        defaults["color"] = {"mode": "thresholds"}
        defaults["thresholds"] = {"mode": "absolute", "steps": thresholds}
    else:
        defaults["color"] = fixed(color)
        defaults["thresholds"] = {"mode": "absolute",
                                  "steps": [{"color": "text", "value": None}]}
    return {"type": "stat", "id": nid(), "title": title, "description": desc,
            "gridPos": pos, "targets": list(targets),
            "fieldConfig": {"defaults": defaults, "overrides": list(overrides)},
            "options": {"colorMode": "value", "graphMode": "none",
                        "justifyMode": "center", "textMode": "value_and_name",
                        "orientation": "horizontal", "wideLayout": True,
                        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "",
                                          "values": False}}}


def series(title, desc, targets, pos, unit="short", bars=True, overrides=(),
           stack=True, interval="1h"):
    return {"type": "timeseries", "id": nid(), "title": title,
            "description": desc, "gridPos": pos, "interval": interval,
            "targets": list(targets),
            "fieldConfig": {"defaults": {
                "unit": unit, "min": 0, "color": {"mode": "palette-classic"},
                "custom": {"drawStyle": "bars" if bars else "line",
                           "fillOpacity": 70 if bars else 10, "lineWidth": 1 if bars else 2,
                           "showPoints": "never" if bars else "always", "pointSize": 6,
                           "spanNulls": False, "gradientMode": "none",
                           "stacking": {"mode": "normal" if stack else "none",
                                        "group": "A"}}},
                "overrides": list(overrides)},
            "options": {"legend": {"displayMode": "table", "placement": "right",
                                   "calcs": ["sum"] if bars else ["mean", "max"],
                                   "showLegend": True},
                        "tooltip": {"mode": "multi", "sort": "desc"}}}


def table(title, desc, targets, pos, transformations=(), overrides=(),
          sort=None):
    opts = {"showHeader": True, "cellHeight": "sm",
            "footer": {"show": False, "reducer": ["sum"], "fields": ""}}
    if sort:
        opts["sortBy"] = [{"displayName": sort, "desc": True}]
    return {"type": "table", "id": nid(), "title": title, "description": desc,
            "gridPos": pos, "targets": list(targets),
            "transformations": list(transformations),
            "fieldConfig": {"defaults": {"custom": {"align": "left",
                                                    "cellOptions": {"type": "auto"},
                                                    "filterable": True},
                                         "noValue": "-"},
                            "overrides": list(overrides)},
            "options": opts}


def logs(title, desc, expr, pos):
    return {"type": "logs", "id": nid(), "title": title, "description": desc,
            "gridPos": pos, "targets": [loki(expr)],
            "options": {"showTime": True, "wrapLogMessage": True,
                        "prettifyLogMessage": False, "enableLogDetails": True,
                        "sortOrder": "Descending", "dedupStrategy": "none"}}


def count(expr, by=None, rng="$__range"):
    inner = f"count_over_time({expr} [{rng}])"
    return f"sum by ({by}) ({inner})" if by else f"sum({inner})"


def pct_color():
    return [{"color": RED, "value": None}, {"color": YELLOW, "value": 90},
            {"color": GREEN, "value": 98}]


def bad_color():
    return [{"color": GREEN, "value": None}, {"color": YELLOW, "value": 1},
            {"color": RED, "value": 10}]


panels = []
y = 0

# ---------------------------------------------------------------- headline
panels.append(row("Foundation node — every LLM call (time range)", y)); y += 1
panels += [
    stat("Prompts", "LLM prompts the node ran in the selected range (one per "
         "gl.nondet LLM call a contract made). Attempts = provider calls, so "
         "Attempts > Prompts means fallbacks happened.",
         [loki(count(PROMPT) + " or vector(0)", "A", True),
          loki(count(ATTEMPT) + " or vector(0)", "B", True)],
         {"h": 5, "w": 5, "x": 0, "y": y},
         overrides=[by_ref("A", ("displayName", "Prompts")),
                    by_ref("B", ("displayName", "Attempts"))]),
    stat("Answered", "Share of prompts that got an answer from SOME provider. "
         "A miss here means every provider in the chain failed "
         "(NO_PROVIDER_FOR_PROMPT) — the contract call fails.",
         [loki(f'100 * {count(PROMPT + " | ok=`true`")} / {count(PROMPT)}', "A", True)],
         {"h": 5, "w": 4, "x": 5, "y": y}, unit="percent", decimals=1,
         thresholds=pct_color(),
         overrides=[by_ref("A", ("displayName", "Answered"))]),
    stat("First try", "Share of prompts the FIRST provider tried answered — no "
         "fallback needed.",
         [loki(f'100 * {count(PROMPT + " | ok=`true` | attempts=`1`")} / {count(PROMPT)}', "A", True)],
         {"h": 5, "w": 4, "x": 9, "y": y}, unit="percent", decimals=1,
         thresholds=pct_color(),
         overrides=[by_ref("A", ("displayName", "First try"))]),
    stat("Failures", "Provider attempts that failed (any reason), and of those "
         "the timeouts (HTTP 408/504, or an error mentioning a timeout).",
         [loki(count(ATTEMPT + " | ok=`false`") + " or vector(0)", "A", True),
          loki(count(ATTEMPT + f" | ok=`false` | {TIMEOUT}") + " or vector(0)", "B", True),
          loki(count(PROMPT + " | ok=`false`") + " or vector(0)", "C", True)],
         {"h": 5, "w": 7, "x": 13, "y": y}, thresholds=bad_color(),
         overrides=[by_ref("A", ("displayName", "Failed attempts")),
                    by_ref("B", ("displayName", "Timeouts")),
                    by_ref("C", ("displayName", "Unanswered prompts"))]),
    stat("Unhardcoded spend", "USD unhardcoded charged the Foundation node's "
         "key in the selected range, and over the key's whole life (from the "
         "router's own report, polled on the node every 5 min).",
         [loki(f"sum(sum_over_time({ROUTER} | unwrap cost_usd [$__range])) or vector(0)", "A", True),
          loki(f"max(max_over_time({TOTALS} | unwrap cost_usd [$__range]))", "B", True)],
         {"h": 5, "w": 4, "x": 20, "y": y}, unit="currencyUSD", decimals=4,
         overrides=[by_ref("A", ("displayName", "In range")),
                    by_ref("B", ("displayName", "Key lifetime"))]),
]
y += 5

panels += [
    series("Calls per provider", "Provider attempts per hour, by provider. "
           "The rotation picks a random lead per session, so over time the three "
           "should be roughly even — a provider that is never tried first is "
           "being skipped (e.g. morpheus has no JSON mode, so JSON prompts skip it).",
           [loki(count(ATTEMPT, "provider", "$__interval"), "A", legend="{{provider}}")],
           {"h": 8, "w": 12, "x": 0, "y": y}),
    series("Failures per provider", "Failed attempts per hour, by provider and "
           "reason (error_kind from the HTTP status: timeout, gateway_timeout, "
           "rate_limit, server_error, auth_error, network_error, …).",
           [loki(count(ATTEMPT + " | ok=`false`", "provider, error_kind", "$__interval"),
                 "A", legend="{{provider}} · {{error_kind}}")],
           {"h": 8, "w": 12, "x": 12, "y": y}),
]
y += 8

panels += [
    series("Latency per provider (p95)", "95th percentile wall time of a "
           "SUCCESSFUL provider call, per hour. Points, not lines: calls are sparse.",
           [loki(f"quantile_over_time(0.95, {ATTEMPT} | ok=`true` | unwrap ms [$__interval]) by (provider)",
                 "A", legend="{{provider}}")],
           {"h": 8, "w": 12, "x": 0, "y": y}, unit="ms", bars=False, stack=False),
    series("Fallbacks", "Prompts per hour by the path the rotation took: "
           "lead > fallback > … (providers_tried). A long chain means the lead "
           "keeps failing.",
           [loki(count(PROMPT, "providers_tried", "$__interval"), "A",
                 legend="{{providers_tried}}")],
           {"h": 8, "w": 12, "x": 12, "y": y}),
]
y += 8

# ---------------------------------------------------------------- tables
SUMMARY = [
    ("A", count(ATTEMPT, "provider"), "Attempts"),
    ("B", count(ATTEMPT + " | ok=`true`", "provider"), "OK"),
    ("C", count(ATTEMPT + " | ok=`false`", "provider"), "Failed"),
    ("D", count(ATTEMPT + f" | ok=`false` | {TIMEOUT}", "provider"), "Timeouts"),
    ("E", count(ATTEMPT + " | attempt=`1`", "provider"), "Tried first"),
    ("F", count(ATTEMPT + " | fallback=`true`", "provider"), "As fallback"),
    ("G", f"avg_over_time({ATTEMPT} | ok=`true` | unwrap ms [$__range]) by (provider)", "Avg ms"),
    ("H", f"quantile_over_time(0.95, {ATTEMPT} | ok=`true` | unwrap ms [$__range]) by (provider)", "p95 ms"),
    ("I", f"sum by (provider) (sum_over_time({ATTEMPT} | ok=`true` | unwrap tokens_total [$__range]))", "Tokens"),
]
panels.append(table(
    "By provider", "One row per provider over the selected range. Tried first = "
    "attempt #1 of a prompt (normally the session's rotation lead; if the lead "
    "can't take the prompt, the next one). As fallback = tried after another "
    "provider failed.",
    [loki(e, r, True, fmt="table") for r, e, _ in SUMMARY],
    {"h": 7, "w": 15, "x": 0, "y": y},
    transformations=[
        {"id": "merge", "options": {}},
        {"id": "organize", "options": {
            "excludeByName": {"Time": True},
            "renameByName": {f"Value #{r}": n for r, _, n in SUMMARY} | {"provider": "Provider"},
            "indexByName": {"provider": 0} | {f"Value #{r}": i + 1 for i, (r, _, _) in enumerate(SUMMARY)}}},
        {"id": "calculateField", "options": {
            "alias": "Success %", "mode": "binary",
            "binary": {"left": "OK", "operator": "/", "right": "Attempts"},
            "replaceFields": False}},
    ],
    overrides=[
        by_name("Success %", ("unit", "percentunit"), ("decimals", 1),
                ("custom.cellOptions", {"type": "color-text"}),
                ("thresholds", {"mode": "absolute", "steps": [
                    {"color": RED, "value": None}, {"color": YELLOW, "value": 0.9},
                    {"color": GREEN, "value": 0.98}]}),
                ("color", {"mode": "thresholds"})),
        by_name("Failed", ("custom.cellOptions", {"type": "color-text"}),
                ("color", {"mode": "thresholds"}),
                ("thresholds", {"mode": "absolute", "steps": bad_color()})),
        by_name("Timeouts", ("custom.cellOptions", {"type": "color-text"}),
                ("color", {"mode": "thresholds"}),
                ("thresholds", {"mode": "absolute", "steps": bad_color()})),
        by_name("Avg ms", ("unit", "ms"), ("decimals", 0)),
        by_name("p95 ms", ("unit", "ms"), ("decimals", 0)),
        by_name("Tokens", ("unit", "short")),
    ],
    sort="Attempts"))

panels.append(table(
    "Rotation lead → who answered", "For each session's rotation lead, which "
    "provider actually answered the prompt. Off-diagonal rows are fallbacks or "
    "lead skips (morpheus has no JSON mode, so JSON prompts skip it).",
    [loki(count(PROMPT, "lead, provider, ok"), "A", True, fmt="table")],
    {"h": 7, "w": 9, "x": 15, "y": y},
    transformations=[{"id": "organize", "options": {
        "excludeByName": {"Time": True},
        "renameByName": {"lead": "Lead", "provider": "Answered by",
                         "ok": "OK", "Value #A": "Prompts"}}}],
    sort="Prompts"))
y += 7

panels.append(logs(
    "Failed attempts", "Every failed provider attempt, newest first. Expand a "
    "line for the full record (http_status, error_kind, error causes, tx_id).",
    ATTEMPT + " | ok=`false` | line_format `{{.provider}} · {{.error_kind}} {{.http_status}} · {{.ms}}ms · attempt {{.attempt}} · {{.error}} · tx {{.tx_id}}`",
    {"h": 8, "w": 12, "x": 0, "y": y}))
panels.append(logs(
    "All prompts", "Every prompt, newest first: who answered, the path taken, "
    "and total time.",
    PROMPT + " | line_format `{{if eq .ok \"true\"}}OK{{else}}FAILED{{end}} · {{.providers_tried}} · {{.ms}}ms · {{.format}} · lead {{.lead}} · tx {{.tx_id}}`",
    {"h": 8, "w": 12, "x": 12, "y": y}))
y += 8

# ---------------------------------------------------------------- unhardcoded
panels.append(row("Unhardcoded — which model the router actually served", y)); y += 1
UH_SUMMARY = [
    ("A", "Requests", "count", ""),
    ("B", "Errors", "count", " | ok=`false`"),
    ("C", "Tokens", "tokens_total", ""),
    ("D", "USD", "cost_usd", ""),
    ("E", "Avg ms", "avg", ""),
]


def uh_table(title, desc, label, by, pos):
    targets = []
    for ref, _, kind, filt in UH_SUMMARY:
        if kind == "count":
            e = count(ROUTER + filt, by)
        elif kind == "avg":
            e = f"avg_over_time({ROUTER} | unwrap latency_ms [$__range]) by ({by})"
        else:
            e = f"sum by ({by}) (sum_over_time({ROUTER} | unwrap {kind} [$__range]))"
        targets.append(loki(e, ref, True, fmt="table"))
    return table(
        title, desc, targets, pos,
        transformations=[
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {
                "excludeByName": {"Time": True},
                "renameByName": {f"Value #{r}": n for r, n, _, _ in UH_SUMMARY} | {by: label},
                "indexByName": {by: 0} | {f"Value #{r}": i + 1 for i, (r, _, _, _) in enumerate(UH_SUMMARY)}}}],
        overrides=[by_name("USD", ("unit", "currencyUSD"), ("decimals", 5)),
                   by_name("Avg ms", ("unit", "ms"), ("decimals", 0)),
                   by_name("Tokens", ("unit", "short")),
                   by_name("Errors", ("custom.cellOptions", {"type": "color-text"}),
                           ("color", {"mode": "thresholds"}),
                           ("thresholds", {"mode": "absolute", "steps": bad_color()}))],
        sort="Requests")


panels.append(uh_table(
    "Served model", "Which model unhardcoded's router actually used for the "
    "node's `profile:default` requests, in the selected range "
    "(x_router.served_model_id). The node itself can't see this.",
    "Served model", "served_model", {"h": 8, "w": 12, "x": 0, "y": y}))
panels.append(uh_table(
    "Upstream provider", "Which upstream unhardcoded routed to (antseed, "
    "openrouter, bedrock, …), in the selected range.",
    "Upstream", "upstream", {"h": 8, "w": 12, "x": 12, "y": y}))
y += 8

panels.append(series(
    "Unhardcoded requests by served model", "Requests per hour on the "
    "Foundation node's key, by the model the router picked. Timestamps are when "
    "the node's 5-min poll logged them.",
    [loki(count(ROUTER, "served_model", "$__interval"), "A", legend="{{served_model}}")],
    {"h": 8, "w": 10, "x": 0, "y": y}))
panels.append(logs(
    "Unhardcoded requests", "Every request the router logged for this key, "
    "newest first: status, served model, upstream, latency, tokens, cost.",
    ROUTER + " | line_format `{{.status}} · {{.served_model}} via {{.upstream}} · {{.latency_ms}}ms · {{.tokens_total}} tok · USD {{.cost_usd}}{{if .error_kind}} · {{.error_kind}}{{end}}`",
    {"h": 8, "w": 14, "x": 10, "y": y}))
y += 8

dashboard = {
    "uid": UID,
    "title": TITLE,
    "description": "What the Foundation node's LLM rotation (unhardcoded / "
                   "morpheus / pearl) is doing: calls, failures, timeouts, "
                   "latency, fallbacks, and the model unhardcoded served.",
    "tags": ["foundation", "testnet", "llm", "genvm"],
    "editable": True,
    "graphTooltip": 1,
    "schemaVersion": 39,
    "refresh": "5m",
    "time": {"from": "now-7d", "to": "now"},
    "timezone": "browser",
    "links": [],
    "annotations": {"list": []},
    "templating": {"list": [{
        "name": "validator", "label": "Node", "type": "custom",
        "query": "genlayer-foundation-bradbury-1",
        "current": {"text": "genlayer-foundation-bradbury-1",
                    "value": "genlayer-foundation-bradbury-1"},
        "options": [{"selected": True, "text": "genlayer-foundation-bradbury-1",
                     "value": "genlayer-foundation-bradbury-1"}],
        "hide": 0}]},
    "panels": panels,
}

out = os.path.join(os.path.dirname(__file__), "..", "dashboards", "foundation",
                   "llm_providers.json")
with open(out, "w") as f:
    json.dump(dashboard, f, indent=2)
    f.write("\n")
print(f"wrote {os.path.normpath(out)}: {len(panels)} panels")
