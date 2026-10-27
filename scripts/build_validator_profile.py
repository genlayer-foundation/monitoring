"""Generate dashboards/foundation/validator_profile.json (uid gl-validator-profile).

Usage, from the repo root:  python3 scripts/build_validator_profile.py dashboards/foundation/validator_profile.json
Then upload the file to Grafana (folder fkpd6m). Design + data sources: VALIDATOR-PROFILE-PLAN.md.
"""
import json, sys

PROM = {"type": "prometheus", "uid": "grafanacloud-prom"}
LOKI = {"type": "loki", "uid": "grafanacloud-logs"}
INF = {"type": "yesoreyeram-infinity-datasource", "uid": "grafanacloud-infinity"}
EXP = "https://scan.bradbury.genlayer.com/api/v1"
ROSTER = "https://portal-admin.genlayer.foundation/api/v1/validators/wallets/grafana/?network=bradbury2"
RPC = "https://rpc.testnet-chain.genlayer.com"
N = 'network="$network", node=~"(?i)$node"'
LSEL = '{job="genlayer-node"} | json | __error__="" | network="$network" | node=~"(?i)$node"'
LSEL_RAW = '{job="genlayer-node"} | json | network="$network" | node=~"(?i)$node"'
NOPROMPT = ' | message!="answer from module"'
NODE_LC = '("${node}" | ascii_downcase)'

panels = []
pid = [0]
y = [0]


def nid():
    pid[0] += 1
    return pid[0]


def prom(expr, legend="", ref="A", instant=False, fmt="time_series"):
    t = {"datasource": PROM, "expr": expr, "refId": ref, "legendFormat": legend or "__auto", "format": fmt}
    if instant:
        t["instant"] = True
        t["range"] = False
    return t


def loki(expr, ref="A", instant=False):
    t = {"datasource": LOKI, "expr": expr, "refId": ref, "queryType": "instant" if instant else "range"}
    return t


def inf_get(url, jq, ref="A", fmt="table"):
    return {"datasource": INF, "refId": ref, "type": "json", "source": "url", "parser": "jq-backend",
            "format": fmt, "url": url, "root_selector": jq, "url_options": {"method": "GET", "data": ""}}


def inf_rpc(calls, jq, ref="A"):
    body = json.dumps([{"jsonrpc": "2.0", "id": i + 1, "method": "eth_call", "params": [{"to": to, "data": data}, "latest"]}
                       for i, (to, data) in enumerate(calls)])
    return {"datasource": INF, "refId": ref, "type": "json", "source": "url", "parser": "jq-backend", "format": "table",
            "url": RPC, "root_selector": jq,
            "url_options": {"method": "POST", "body_type": "raw", "body_content_type": "application/json", "data": body,
                            "headers": [{"key": "Content-Type", "value": "application/json"}]}}


def row(title, collapsed=False):
    p = {"id": nid(), "type": "row", "title": title, "collapsed": collapsed, "gridPos": {"h": 1, "w": 24, "x": 0, "y": y[0]}, "panels": []}
    panels.append(p)
    y[0] += 1
    return p


cur_row = [None]
xcur = [0]
rowh = [0]


def place(p, w, h):
    if xcur[0] + w > 24:
        y[0] += rowh[0]
        xcur[0] = 0
        rowh[0] = 0
    p["gridPos"] = {"h": h, "w": w, "x": xcur[0], "y": y[0]}
    xcur[0] += w
    rowh[0] = max(rowh[0], h)
    if cur_row[0] is not None and cur_row[0]["collapsed"]:
        cur_row[0]["panels"].append(p)
    else:
        panels.append(p)
    return p


def section(title, collapsed=False):
    y[0] += rowh[0]
    xcur[0] = 0
    rowh[0] = 0
    cur_row[0] = row(title, collapsed)


def panel(typ, title, desc, targets, w, h, **kw):
    p = {"id": nid(), "type": typ, "title": title, "description": desc, "targets": targets,
         "datasource": (targets[0]["datasource"] if len({t["datasource"]["uid"] for t in targets}) == 1 else {"type": "datasource", "uid": "-- Mixed --"}) if targets else None,
         "fieldConfig": {"defaults": kw.pop("defaults", {}), "overrides": kw.pop("overrides", [])},
         "options": kw.pop("options", {})}
    if "_order" in kw:
        o = kw.pop("_order"); p["targets"] = sorted(p["targets"], key=lambda t: o.index(t["refId"]))
    if "transformations" in kw:
        p["transformations"] = kw.pop("transformations")
    p.update(kw)
    return place(p, w, h)


C = {"green": "green", "yellow": "yellow", "orange": "orange", "red": "red", "gray": "#808080", "grey": "#808080"}


def text_map(pairs):
    """pairs: [(match, text, color)] exact value mappings"""
    return [{"type": "value", "options": {m: {"text": t, "color": c, "index": i} for i, (m, t, c) in enumerate(pairs)}}]


def regex_map(pairs):
    return [{"type": "regex", "options": {"pattern": pat, "result": {"text": t, "color": c, "index": i}}} for i, (pat, t, c) in enumerate(pairs)]


def stat_opts(fields="", mode="background", text="value"):
    return {"reduceOptions": {"calcs": ["lastNotNull"], "fields": fields, "values": False},
            "colorMode": mode, "graphMode": "none", "textMode": text, "justifyMode": "center", "wideLayout": True}


HEALTH_MAP = regex_map([(r"^red\|(.*)$", "$1", "red"), (r"^orange\|(.*)$", "$1", "orange"), (r"^yellow\|(.*)$", "$1", "yellow"),
                        (r"^gr[ae]y\|(.*)$", "$1", C["gray"]), (r"^green\|(.*)$", "$1", "green")])
SEV_MAP = text_map([("red", "red", "red"), ("orange", "orange", "orange"), ("yellow", "yellow", "yellow"), ("green", "green", "green"), ("gray", "gray", C["gray"])])
COND_MAP = text_map([("healthy", "healthy", "green"), ("warning", "warning", "yellow"), ("degraded", "degraded", "orange"),
                     ("suspect", "suspect", "orange"), ("unavailable", "unavailable", "red"), ("unknown", "unknown", C["gray"])])
GEN = "(tonumber / 1e18)"

# ---------------------------------------------------------------- Row 1
addr = f"{EXP}/address/${{node}}"
roster_me = f'[.[] | select(.node == {NODE_LC})]'
STAKING = "0xD8fBa96C0dBB0257028dBc0107060b958e5c7113"

JOIN_TOPIC = "0x2b7297b31452d0a13e57c605870ec3c9b4ac6ef33e5cbae7a0f00bc2a3e96782"
def join_logs(jq, ref="J"):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs", "params": [{"address": STAKING, "fromBlock": "0xbb3a", "toBlock": "latest", "topics": [JOIN_TOPIC]}]})
    t = inf_rpc([], "", ref=ref)
    t["url_options"]["data"] = body
    t["root_selector"] = ('def h2i: ascii_downcase | reduce (explode[]) as $c (0; .*16 + (if $c>=97 then $c-87 else $c-48 end));\n'
                          '[.result[] | select((.data | ascii_downcase | .[90:130]) == "${node_hex}")] | first // {} | ' + jq)
    return t

section("Profile")
panel("text", "", "", [], 15, 8, options={"mode": "html", "content": """
<div style="display:flex;gap:28px;align-items:center;padding:8px 4px">
  ${p_logo:raw}
  <div style="min-width:0">
    <div style="font-size:34px;font-weight:600;line-height:1.15">${p_name:raw}</div>
    <div style="font-size:16px;opacity:.85;margin:10px 0 12px 0;max-width:820px">${p_desc:raw}</div>
    <div style="font-size:14px">${p_links:raw}</div>
    <div style="font-family:monospace;font-size:12px;opacity:.6;margin-top:10px">validator wallet ${node}</div>
  </div>
</div>"""}, transparent=True)
_facts_targets = None
panel("table", "Facts", "Identity facts. Sources: chain `ValidatorJoin` event (since, initial stake), explorer `/address` (status, operator, owner), portal roster (portal link, identity completeness).",
      [inf_get(addr, '.validator | ['
                     '{fact: "Status", value: .status}, {fact: "Operator", value: (.operator_address | ascii_downcase)}, {fact: "Owner", value: (.owner_address | ascii_downcase)}]', ref="A"),
       inf_get(ROSTER, roster_me + ' | map([{fact: "Portal", value: (if .linked == true then ("linked" + (if (.account_name // "") != "" then " — " + .account_name else "" end)) elif .linked == false then "NOT LINKED" else "-" end)}, '
               '{fact: "On-chain identity", value: ([(if (.moniker // "") == "" then "moniker" else empty end), (if (.logo_uri // "") == "" then "logo" else empty end), (if .has_description == true then empty else "description" end)] '
               '| if length == 0 then "complete" else "missing: " + join(", ") end)}]) | add // []', ref="B"),
       join_logs('if .blockTimestamp then [{fact: "Validator since", value: ((.blockTimestamp | ltrimstr("0x") | h2i) | strftime("%Y-%m-%d %H:%M UTC"))}, '
                 '{fact: "Joined with", value: (((.data | ltrimstr("0x") | .[128:192] | h2i) / 1e18 | floor | tostring) + " GEN self stake")}] else [{fact: "Validator since", value: "no join event found"}] end', ref="C")],
      9, 8, options={"showHeader": False, "cellHeight": "sm"}, transformations=[{"id": "merge", "options": {}}],
      _order=["C", "A", "B"],
      overrides=[{"matcher": {"id": "byName", "options": "fact"}, "properties": [{"id": "custom.width", "value": 150}, {"id": "custom.cellOptions", "value": {"type": "auto"}}]},
                 {"matcher": {"id": "byName", "options": "value"}, "properties": [
                     {"id": "mappings", "value": regex_map([(r"^(linked.*|complete|active)$", "$1", "green"), (r"^(NOT LINKED|missing.*|quarantined)$", "$1", "orange")])},
                     {"id": "custom.cellOptions", "value": {"type": "color-text"}}]}])
panel("stat", "Validator for", "Time since the validator joined the network (its on-chain `ValidatorJoin` event). Source: chain, staking contract logs.",
      [join_logs('[{since: ((.blockTimestamp // "0x0" | ltrimstr("0x") | h2i) * 1000)}]')], 5, 3, options=stat_opts("/^since$/", mode="value"),
      defaults={"unit": "dateTimeFromNow", "color": {"mode": "fixed", "fixedColor": "text"}})
panel("stat", "Total stake", "Self + delegated stake, GEN. Source: explorer `/validators` (same number as the network board).",
      [inf_get(f"{EXP}/validators?page_size=100", f'[.validators[] | select((.validator_address | ascii_downcase) == {NODE_LC}) | {{stake: (((.self_stake | tonumber) + (.delegated_stake | tonumber)) / 1e18)}}]')], 5, 3, options=stat_opts("/^stake$/", mode="value"), defaults={"decimals": 0, "color": {"mode": "fixed", "fixedColor": "text"}})
panel("stat", "Transactions", "Transactions this validator has taken part in. Source: explorer `/validators` `transaction_count`.",
      [inf_get(f"{EXP}/validators?page_size=100", f'[.validators[] | select((.validator_address | ascii_downcase) == {NODE_LC}) | {{txs: (.transaction_count // 0)}}]')], 5, 3, options=stat_opts("/^txs$/", mode="value"), defaults={"decimals": 0, "color": {"mode": "fixed", "fixedColor": "text"}})
panel("stat", "Delegators", "Delegators staking with this validator. Source: explorer `/address`.",
      [inf_get(addr, '.validator | {d: (.delegators | length)}')], 4, 3, options=stat_opts("/^d$/", mode="value"), defaults={"decimals": 0, "color": {"mode": "fixed", "fixedColor": "text"}})
panel("stat", "Node running for", "Time since the node process last started (a restart resets it). Source: `genlayer_node_uptime_seconds`.",
      [prom(f'max(genlayer_node_uptime_seconds{{{N}, component="node"}})', instant=True)], 5, 3, options=stat_opts(mode="value"),
      defaults={"unit": "s", "decimals": 0, "color": {"mode": "fixed", "fixedColor": "text"}})
section("Status — things to fix")
roster_me = f'[.[] | select(.node == {NODE_LC})]'
panel("stat", "Health (portal verdict)",
      "The portal's single health verdict for this node — the same colour the validator sees on the portal and Deckard. Source: portal roster `health`.",
      [inf_get(ROSTER, roster_me + ' | map({health: ((.health.color // "gray") + "|" + (.health.label // .health.color // "not checked"))})')],
      5, 8, options=stat_opts("/^health$/"), defaults={"mappings": HEALTH_MAP, "color": {"mode": "fixed", "fixedColor": C["gray"]}})

FIX = {
    "quarantined": ("Quarantined", "Keep the node up and responsive until the quarantine lifts; see 'Why did it go wrong?' for the cause."),
    "permanently_quarantined": ("No longer participating", "Permanently quarantined: restake with a new validator wallet."),
    "inactive": ("Not participating", "Check self stake is at the minimum and the node is primed for the next epoch."),
    "not_deployed": ("Not deployed", "Deploy a validator wallet and node on this network."),
    "stake_below_minimum": ("Stake below minimum", "Top up self stake to the minimum."),
    "no_metrics": ("Not sending metrics", "Enable metrics push — docs.genlayer.com/validators/monitoring."),
    "no_logs": ("Not sending logs", "Enable log shipping — docs.genlayer.com/validators/monitoring."),
    "version_behind": ("Version behind", "Upgrade the node to the latest release."),
    "identity_incomplete": ("Profile incomplete", "Set the missing on-chain identity fields (moniker, logo, description) on the validator wallet."),
    "not_linked": ("Not linked to portal", "Link this validator wallet to your portal account."),
    "blocks_behind": ("Behind on blocks", "The node lags the chain head: check its RPC provider, disk and CPU (Sync & connectivity)."),
    "source_unavailable": ("Monitoring delayed", "Monitoring has not checked this node recently — nothing to do on your side."),
}
fix_jq = ("{" + ", ".join(f'"{k}": {{problem: {json.dumps(v[0])}, fix: {json.dumps(v[1])}}}' for k, v in FIX.items()) + "} as $fix | ")
SEVR = '{"red":0,"orange":1,"yellow":2,"gray":3,"green":4}'
cond_fix = ('{"chain.rpc": "Check the RPC endpoint and key in the node config.", "chain.sync": "Node is not syncing: check RPC and disk.", '
            '"chain.websocket": "Websocket to the chain keeps dropping: check the WSS endpoint.", "consensus.ban": "Quarantined/banned: wait for the stated epoch (see the node message below).", '
            '"consensus.operator_funds": "Top up the operator address with GEN for gas.", "consensus.prime": "Primes are not landing: check operator funds and RPC.", '
            '"consensus.stake": "Self stake is below the minimum: top it up.", "genvm.llm": "LLM provider calls fail: check the provider key, quota and model.", '
            '"genvm.web": "Web requests from GenVM fail: check outbound network and the webdriver.", "node.disk": "Disk is filling up: free or grow it.", '
            '"node.snapshot_age": "Snapshot is old.", "webdriver.render": "Webdriver cannot render pages: restart the webdriver container."}')

import json as _json
_CF = _json.loads(cond_fix)
def cond_expr():
    e = f'max by (condition, state)(genlayer_node_operator_condition_state{{{N}, state!~"healthy|unknown"}}) == 1'
    for c, t in _CF.items():
        e = f'label_replace({e}, "fix", {_json.dumps(t)}, "condition", {_json.dumps(c.replace(".", "[.]"))})'
    for st, sev in (("warning", "yellow"), ("degraded", "orange"), ("suspect", "orange"), ("unavailable", "red")):
        e = f'label_replace({e}, "severity", "{sev}", "state", "{st}")'
    e = f'label_replace({e}, "problem", "Node check: $1", "condition", "(.*)")'
    e = f'label_replace({e}, "details", "The node reports this check as $1.", "state", "(.*)")'
    e = f'label_replace({e}, "from", "Node", "", "")'
    return e
panel("table", "Things to fix",
      "Everything that is off for this node, worst first, with what to do. Rows come from the portal verdict (Portal) and from the node's own condition checks (Node). Empty = nothing to fix.",
      [inf_get(ROSTER, fix_jq + roster_me + ' | [.[] | (.health.findings // [])[] | {severity, problem: ($fix[.type].problem // (.type | gsub("_"; " "))), '
               'details: .detail, fix: ($fix[.type].fix // ""), from: "Portal"}]', ref="A"),
       prom(cond_expr(), instant=True, fmt="table", ref="B")],
      19, 8, options={"showHeader": True, "cellHeight": "sm"},
      transformations=[
          {"id": "labelsToFields", "options": {"mode": "columns"}},
          {"id": "merge", "options": {}},
          {"id": "organize", "options": {"excludeByName": {"Time": True, "Value": True, "condition": True, "state": True, "__name__": True}, "indexByName": {"severity": 0, "problem": 1, "details": 2, "fix": 3, "from": 4}}}],
      overrides=[{"matcher": {"id": "byName", "options": "severity"}, "properties": [
          {"id": "mappings", "value": SEV_MAP}, {"id": "custom.cellOptions", "value": {"type": "color-background"}}, {"id": "custom.width", "value": 80}]},
          {"matcher": {"id": "byName", "options": "problem"}, "properties": [{"id": "custom.width", "value": 170}]},
          {"matcher": {"id": "byName", "options": "from"}, "properties": [{"id": "custom.width", "value": 70}]},
          {"matcher": {"id": "byName", "options": "condition"}, "properties": [{"id": "custom.width", "value": 170}]},
          {"matcher": {"id": "byName", "options": "state"}, "properties": [{"id": "mappings", "value": COND_MAP}, {"id": "custom.cellOptions", "value": {"type": "color-background"}}, {"id": "custom.width", "value": 100}]},
          {"matcher": {"id": "byRegexp", "options": "details|fix"}, "properties": [{"id": "custom.cellOptions", "value": {"type": "auto", "wrapText": True}}]}])

SEL = "0x2d2f135d"
panel("stat", "Chain",
      "Live on-chain participation, same rule as the network board: in the selectable set = active; quarantined until epoch N; permanently quarantined = no longer participating; otherwise not participating. Source: staking `epoch()`, `selectableValidators()`, `validatorBanned(node)`.",
      [inf_rpc([(STAKING, "0x900cf0cf"), (STAKING, SEL), (STAKING, "0x090d60bd000000000000000000000000${node_hex}")],
               'def h2i: ascii_downcase | reduce (explode[]) as $c (0; .*16 + (if $c>=97 then $c-87 else $c-48 end));\n'
               '(map(select(.id==1))[0].result | ltrimstr("0x") | h2i) as $ep\n'
               '| (map(select(.id==2))[0].result | ltrimstr("0x") | .[128:] | [range(0; length/64) as $i | .[$i*64+24:$i*64+64]]) as $sel\n'
               '| (map(select(.id==3))[0].result | ltrimstr("0x")) as $b\n'
               '| ($b[64:128] | if . == "" then 0 else h2i end) as $until | (($b[128:192] // "") | if . == "" then 0 else h2i end) as $perm\n'
               '| [{chain: (if $perm > 0 then "red|No longer participating" elif $until > $ep then "orange|Quarantined until epoch \\($until)" '
               'elif ($sel | index("${node_hex}")) != null then "green|Active (epoch \\($ep))" else "red|Not participating" end)}]')], 5, 3, options=stat_opts("/^chain$/"), defaults={"mappings": HEALTH_MAP})
panel("stat", "Version",
      "The node's version, and whether it is the newest version running on the network. Source: `genlayer_node_info` labels.",
      [prom(f'label_replace(max by (version)(genlayer_node_info{{{N}, version="$latest_version"}}), "disp", "$1 — up to date", "version", "(.*)") '
            f'or label_replace(max by (version)(genlayer_node_info{{{N}}}), "disp", "$1 — behind ($latest_version)", "version", "(.*)")',
            instant=True, fmt="table")], 4, 3, options=stat_opts("/^disp$/"), defaults={"thresholds": {"mode": "absolute", "steps": [{"color": C["gray"], "value": None}]}, "mappings": regex_map([(r"(.*up to date)", "$1", "green"), (r"(.*behind.*)", "$1", "yellow")])})
panel("stat", "Strikes",
      "Idleness strikes in the current epoch / the limit that quarantines. Source: explorer `/address` `strikes_current`, `strikes_max` (it resets each epoch, so a quarantined node usually shows 0).",
      [inf_get(addr, '.validator | {strikes: "\\(.strikes_current // 0) / \\(.strikes_max // 3)"}')], 3, 3, options=stat_opts("/^strikes$/", mode="value"), defaults={"color": {"mode": "fixed", "fixedColor": "text"}})
panel("stat", "Primed",
      "Whether the node has primed for the next epoch. A node that stops priming drops out. Source: explorer `/address` `is_primed_next_epoch`.",
      [inf_get(addr, '.validator | {primed: (if .is_primed_next_epoch then "yes" else "no" end)}')], 3, 3, options=stat_opts("/^primed$/"), defaults={"mappings": text_map([("yes", "Yes", "green"), ("no", "No", "red")])})
panel("stat", "Blocks behind", "How far the node lags the chain head now. 5–99 orange, ≥100 red. Source: `genlayer_node_blocks_behind`.",
      [prom(f'max(genlayer_node_blocks_behind{{{N}}})', instant=True)], 3, 3, options=stat_opts(),
      defaults={"thresholds": {"mode": "absolute", "steps": [{"color": C["gray"], "value": None}, {"color": "green", "value": 0}, {"color": "orange", "value": 5}, {"color": "red", "value": 100}]}})
panel("stat", "Metrics", "Is the node pushing metrics now. Source: `genlayer_node_info`.",
      [prom(f'count(genlayer_node_info{{{N}}}) or vector(0)', instant=True)], 3, 3, options=stat_opts(),
      defaults={"mappings": [{"type": "range", "options": {"from": 1, "to": 1e9, "result": {"text": "ON", "color": "green"}}},
                             {"type": "value", "options": {"0": {"text": "OFF", "color": "yellow"}}}]})
panel("stat", "Logs", "Is the node shipping logs (any line in the last 5 min). Source: Loki, matched on the `node` field inside the log JSON.",
      [loki(f'sum(count_over_time({LSEL} [5m])) or vector(0)', instant=True)], 3, 3, options=stat_opts(),
      defaults={"mappings": [{"type": "range", "options": {"from": 1, "to": 1e12, "result": {"text": "ON", "color": "green"}}},
                             {"type": "value", "options": {"0": {"text": "OFF", "color": "yellow"}}}]})

# ---------------------------------------------------------------- Row 2
section("What do I do about it? — the node's own diagnosis")
panel("table", "Node conditions now",
      "The node checks 12 conditions on itself (RPC, sync, websocket, ban, funds, prime, stake, LLM, web, disk, snapshot, webdriver). Anything not healthy is listed first. Source: `genlayer_node_operator_condition_state`.",
      [prom(f'max by (condition, state)(genlayer_node_operator_condition_state{{{N}}}) == 1', instant=True, fmt="table")],
      8, 10, options={"showHeader": True, "cellHeight": "sm", "sortBy": [{"displayName": "rank", "desc": True}]},
      transformations=[
          {"id": "organize", "options": {"excludeByName": {"Time": True, "Value": True}}},
          {"id": "calculateField", "options": {"mode": "unary", "alias": "dummy"}}],
      overrides=[{"matcher": {"id": "byName", "options": "state"}, "properties": [
          {"id": "mappings", "value": COND_MAP}, {"id": "custom.cellOptions", "value": {"type": "color-background"}}]}])
_st = [("healthy", 0), ("warning", 1), ("degraded", 2), ("suspect", 3), ("unavailable", 4), ("unknown", -1)]
state_num = "max by (condition)(" + " or ".join(
    f'(genlayer_node_operator_condition_state{{{N}, state="{st}"}} == 1) * 0 + {v}' for st, v in _st) + ")"
panel("state-timeline", "Condition history",
      "When each condition went bad and recovered. Green healthy, yellow warning, orange degraded/suspect, red unavailable, grey unknown. Source: `genlayer_node_operator_condition_state`.",
      [prom(state_num, "{{condition}}")], 16, 10,
      options={"showValue": "never", "mergeValues": True, "rowHeight": 0.8, "legend": {"showLegend": False}},
      defaults={"mappings": text_map([("0", "healthy", "green"), ("1", "warning", "yellow"), ("2", "degraded", "orange"),
                                      ("3", "suspect", "orange"), ("4", "unavailable", "red"), ("-1", "unknown", C["gray"])]),
                "color": {"mode": "thresholds"}, "thresholds": {"mode": "absolute", "steps": [{"color": C["gray"], "value": None}, {"color": "green", "value": 0},
                    {"color": "yellow", "value": 1}, {"color": "orange", "value": 2}, {"color": "red", "value": 4}]}})
panel("logs", "What the node says needs attention",
      "The node's own 'requires attention' messages: which condition, why, the impact and the suggested action. Source: Loki, message `operator condition requires attention`.",
      [loki(f'{LSEL_RAW} | message="operator condition requires attention" | line_format "[{{{{.condition}}}}] {{{{.reason}}}} — impact: {{{{.impact}}}} — action: {{{{.action}}}}"')],
      16, 8, options={"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending", "enableLogDetails": True})
panel("table", "Problems seen in range",
      "How many times each condition reported each reason in the selected time range. Source: `genlayer_node_operator_condition_occurrences_total`.",
      [prom(f'sum by (condition, reason)(increase(genlayer_node_operator_condition_occurrences_total{{{N}}}[$__range])) > 0', instant=True, fmt="table")],
      8, 8, options={"showHeader": True, "cellHeight": "sm", "sortBy": [{"displayName": "Value", "desc": True}]},
      transformations=[{"id": "organize", "options": {"excludeByName": {"Time": True}, "renameByName": {"Value": "times"}}}],
      defaults={"decimals": 0})

# ---------------------------------------------------------------- Row 3
section("Am I earning? — stake, rewards, slashing")
panel("stat", "Stake now (explorer)",
      "Self stake and delegated stake, in GEN. Source: explorer `/address` (indexed at the last epoch boundary — a slash enacted since may not be in it yet).",
      [inf_get(addr, f'.validator | {{self_stake: (.self_stake | {GEN}), delegated: (.delegated_stake | {GEN}), delegators: (.delegators | length)}}')],
      8, 4, options=stat_opts("/.*/", mode="value", text="value_and_name"), defaults={"decimals": 0, "unit": "none", "color": {"mode": "fixed", "fixedColor": "text"}})
STAKING = "0xD8fBa96C0dBB0257028dBc0107060b958e5c7113"
panel("stat", "Stake now (chain, live)",
      "Live `validatorView` on the staking contract: self stake and pending deposits/withdrawals, in GEN. The chain is the authority.",
      [inf_rpc([(STAKING, "0xb83f5b39000000000000000000000000${node_hex}")],
               'def h2i: ascii_downcase | reduce (explode[]) as $c (0; .*16 + (if $c>=97 then $c-87 else $c-48 end));\n'
               '.[0].result | ltrimstr("0x") | {self_stake: (.[128:192] | h2i / 1e18), delegated: (.[256:320] | h2i / 1e18), quarantined_until_epoch: (.[0:64] | h2i)}')],
      8, 4, options=stat_opts("/.*/", mode="value", text="value_and_name"), defaults={"decimals": 0, "color": {"mode": "fixed", "fixedColor": "text"}})
panel("stat", "Rewards earned (node counter)",
      "Validator rewards the node has seen paid to it since the node process started — highest value in the selected range (GEN). Resets when the node restarts. Source: `genlayer_node_fees_earned_wei_total{type=\"validator_rewards\"}`.",
      [prom(f'max(max_over_time(genlayer_node_fees_earned_wei_total{{{N}, type="validator_rewards"}}[$__range])) / 1e18', instant=True)],
      8, 4, options=stat_opts(mode="value"), defaults={"decimals": 0, "unit": "none", "color": {"mode": "fixed", "fixedColor": "text"}})

hist_targets = []
for n in range(1, 15):
    hist_targets.append(inf_get(f"{EXP}/epochs/{n}/validators?page_size=100",
                                f'[.validators[] | select((.validator_address | ascii_downcase) == {NODE_LC}) | {{epoch: "{n:02d}", '
                                f'self_stake: (.self_stake | {GEN}), rewards: (((.validator_rewards // "0") | {GEN}) + ((.fee_rewards // "0") | {GEN})), '
                                f'slashing: (-(((.validator_slashing // "0") | {GEN}) + ((.fee_penalties // "0") | {GEN}))), status}}]',
                                ref=f"E{n:02d}"))
hist_tf = [{"id": "merge", "options": {}}, {"id": "sortBy", "options": {"sort": [{"field": "epoch"}]}}]
panel("barchart", "Rewards vs slashing per epoch",
      "Green = rewards paid (validator + fee rewards), red = slashing and fee penalties, in GEN. Source: explorer `/epochs/{n}/validators`, one query per epoch (stopgap, covers epochs 1–14).",
      hist_targets, 12, 9, transformations=hist_tf + [{"id": "organize", "options": {"excludeByName": {"self_stake": True, "status": True}}}],
      options={"xField": "epoch", "stacking": "normal", "showValue": "auto", "legend": {"showLegend": True, "displayMode": "list", "placement": "bottom"}},
      defaults={"decimals": 0, "custom": {"fillOpacity": 80}},
      overrides=[{"matcher": {"id": "byName", "options": "rewards"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "green"}}]},
                 {"matcher": {"id": "byName", "options": "slashing"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]}])
panel("barchart", "Self stake per epoch",
      "Self stake at each epoch, in GEN. Rewards compound into stake; slashes take it away. Source: explorer `/epochs/{n}/validators`.",
      [dict(t) for t in hist_targets], 12, 9, transformations=hist_tf + [{"id": "organize", "options": {"excludeByName": {"rewards": True, "slashing": True, "status": True}}}],
      options={"xField": "epoch", "showValue": "auto", "legend": {"showLegend": False}},
      defaults={"decimals": 0, "color": {"mode": "fixed", "fixedColor": "blue"}, "custom": {"fillOpacity": 80}})
panel("timeseries", "Gas spent per duty (GEN / hour)",
      "What each kind of on-chain duty costs the operator. Source: `genlayer_node_gas_spent_wei_total` by method.",
      [prom(f'sum by (method)(increase(genlayer_node_gas_spent_wei_total{{{N}}}[1h])) / 1e18', "{{method}}")],
      24, 7, defaults={"unit": "none", "decimals": 4})

# ---------------------------------------------------------------- Row 4
section("Am I doing my job? — duties, votes, leader turns")
panel("stat", "Last 7 days (explorer)",
      "Leader turns, how often it was rotated out as leader, votes cast, votes in the minority, idle rounds, successful appeals against it. Source: explorer `/address` `*_7d`.",
      [inf_get(addr, '.validator | {"leader turns": .total_as_leader_7d, "rotated %": .rotation_pct_7d, "votes": .total_votes_7d, '
                     '"minority %": .minority_pct_7d, "idle": .idle_count_7d, "idle %": .idle_pct_7d, "appeals lost": .successful_appeals_7d}')],
      24, 4, options=stat_opts("/.*/", mode="value", text="value_and_name"), defaults={"color": {"mode": "fixed", "fixedColor": "text"}})
duty = [("leader_proposed", "leader proposed"), ("leader_revealed", "leader revealed"), ("validator_commit", "vote committed"),
        ("validator_reveal", "vote revealed"), ("activated", "activated")]
panel("timeseries", "Duties per hour",
      "Consensus work the node did each hour. A flat zero while active means the node is not being selected or not responding. Source: `genlayer_node_transactions_{leader_proposed,leader_revealed,validator_commit,validator_reveal,activated}_total`.",
      [prom(f'max(increase(genlayer_node_transactions_{m}_total{{{N}}}[1h]))', lbl, ref=chr(65 + i)) for i, (m, lbl) in enumerate(duty)],
      12, 8, defaults={"decimals": 0, "custom": {"drawStyle": "bars", "fillOpacity": 60, "stacking": {"mode": "none"}}})
panel("timeseries", "Submissions that failed",
      "On-chain transactions the node sent that failed or reverted, per hour, by method. Should be zero. Source: `genlayer_node_consensus_submit_total{outcome!=\"success\"}`.",
      [prom(f'sum by (method, outcome)(increase(genlayer_node_consensus_submit_total{{{N}, outcome!="success"}}[1h])) or vector(0)', "{{method}} {{outcome}}")],
      12, 8, defaults={"decimals": 0, "color": {"mode": "palette-classic"}, "custom": {"drawStyle": "bars", "fillOpacity": 60}})
part_jq = ('.participations | map({time: (.submission_timestamp * 1000), round: .round_label, role, outcome, color: .outcome_color, '
           'tx: .hash})')
link_tx = [{"title": "Open in explorer", "url": "https://scan.bradbury.genlayer.com/tx/${__value.raw}", "targetBlank": True}]
OUT_COLOR = regex_map([(r"^green$", "", "green"), (r"^red$", "", "red"), (r"^(yellow|orange)$", "", "orange")])
tx_overrides = [
    {"matcher": {"id": "byName", "options": "time"}, "properties": [{"id": "unit", "value": "dateTimeAsIso"}, {"id": "custom.width", "value": 170}]},
    {"matcher": {"id": "byName", "options": "tx"}, "properties": [{"id": "links", "value": link_tx}]},
    {"matcher": {"id": "byName", "options": "color"}, "properties": [{"id": "custom.hidden", "value": True}]},
    {"matcher": {"id": "byName", "options": "outcome"}, "properties": [
        {"id": "mappings", "value": regex_map([(r"^(Idle.*)$", "$1", "red"), (r"^(Timeout.*)$", "$1", "red"), (r"^(.*In Minority.*)$", "$1", "orange"),
                                               (r"^(.*)$", "$1", "green")])},
        {"id": "custom.cellOptions", "value": {"type": "color-text"}}]}]
panel("table", "Recent transactions",
      "The last ~100 rounds this node took part in, newest first: role and how it went. Click a tx to open it in the explorer. Source: explorer `/transactions/participations`.",
      [inf_get(f"{EXP}/transactions/participations?address=${{node}}&page_size=100", part_jq)],
      24, 10, options={"showHeader": True, "cellHeight": "sm"}, overrides=tx_overrides)

# ---------------------------------------------------------------- Row 5
section("Why did it go wrong? — idleness, quarantine, slashing")
panel("table", "Idle rounds",
      "Rounds where the node was picked but did not act in time. Idle rounds give strikes; 3 strikes in an epoch quarantine the node and slash it. Source: explorer `/transactions/participations?role_filter=idle`.",
      [inf_get(f"{EXP}/transactions/participations?address=${{node}}&page_size=100&role_filter=idle",
               part_jq + ' | map(select(.outcome == "Idle"))')],
      12, 8, options={"showHeader": True, "cellHeight": "sm"}, overrides=tx_overrides)
panel("table", "Status and money per epoch",
      "Per epoch: on-chain status, rewards, slashing, self stake (GEN). Source: explorer `/epochs/{n}/validators`.",
      [dict(t) for t in hist_targets], 12, 8, transformations=hist_tf + [{"id": "sortBy", "options": {"sort": [{"field": "epoch", "desc": True}]}}],
      options={"showHeader": True, "cellHeight": "sm"}, defaults={"decimals": 0},
      overrides=[{"matcher": {"id": "byName", "options": "status"}, "properties": [
          {"id": "mappings", "value": text_map([("active", "active", "green"), ("quarantined", "quarantined", "orange"), ("banned", "banned", "red"), ("inactive", "inactive", "red")])},
          {"id": "custom.cellOptions", "value": {"type": "color-background"}}]},
          {"matcher": {"id": "byName", "options": "slashing"}, "properties": [{"id": "custom.cellOptions", "value": {"type": "color-text"}},
              {"id": "thresholds", "value": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "text", "value": 0}]}}]}])
panel("logs", "Idle / replaced events seen by the node",
      "The node's log lines when a leader or validator was idle and replaced, and missed primes. Source: Loki.",
      [loki(f'{LSEL_RAW} | message=~"Leader is idle.*|Validator\\\\(s\\\\) idle.*|Missed prime.*|Leader rotated.*|Primed for epoch.*"')],
      24, 8, options={"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending", "enableLogDetails": True})

# ---------------------------------------------------------------- Row 6 (collapsed)
section("Sync & connectivity", collapsed=True)
panel("state-timeline", "Sync health",
      "0 Synced, 1 Degraded, 2 Catching up, 3 Hopelessly behind. Source: `genlayer_node_health_state`.",
      [prom(f'max(genlayer_node_health_state{{{N}}})', "health")], 24, 4,
      options={"showValue": "never", "mergeValues": True, "legend": {"showLegend": False}},
      defaults={"mappings": text_map([("0", "Synced", "green"), ("1", "Degraded", "yellow"), ("2", "Catching up", "orange"), ("3", "Hopelessly behind", "red")]),
                "color": {"mode": "thresholds"}, "thresholds": {"mode": "absolute", "steps": [{"color": C["gray"], "value": None}]}})
panel("timeseries", "Blocks behind", "How far the node lags the chain head. ≥100 is red on the portal. Source: `genlayer_node_blocks_behind`.",
      [prom(f'max(genlayer_node_blocks_behind{{{N}}})', "blocks behind")], 12, 7,
      defaults={"thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "orange", "value": 5}, {"color": "red", "value": 100}]},
                "custom": {"thresholdsStyle": {"mode": "line+area"}}})
panel("timeseries", "RPC latency p95 by method", "95th percentile latency of the node's calls to its chain RPC provider. Source: `genlayer_rollup_rpc_request_duration_seconds_bucket`.",
      [prom(f'histogram_quantile(0.95, sum by (le, method)(rate(genlayer_rollup_rpc_request_duration_seconds_bucket{{{N}}}[5m])))', "{{method}}")],
      12, 7, defaults={"unit": "s"})
panel("timeseries", "RPC errors by fault", "RPC errors per minute: `provider` = the RPC endpoint failed, `blockchain` = the chain rejected the call. Source: `genlayer_rollup_rpc_errors_total`.",
      [prom(f'sum by (fault, error_type)(rate(genlayer_rollup_rpc_errors_total{{{N}}}[5m])) * 60 or vector(0)', "{{fault}} {{error_type}}")],
      12, 7, defaults={"unit": "none"})
panel("timeseries", "Nonce manager", "Stuck, dropped and gap nonces; non-zero means the node's own transactions are jammed. Source: `genlayer_node_transact_*`.",
      [prom(f'max(genlayer_node_transact_stuck_nonce_count{{{N}}})', "stuck", "A"),
       prom(f'max(genlayer_node_transact_dropped_nonce_count{{{N}}})', "dropped", "B"),
       prom(f'max(genlayer_node_transact_nonce_gap_size{{{N}}})', "gap", "C"),
       prom(f'max(genlayer_node_transact_nonce_desync_delta{{{N}}})', "desync", "D")], 12, 7)
panel("timeseries", "Websocket reconnects", "Websocket disconnections per hour by reason. Source: `genlayer_rollup_ws_disconnections_total`.",
      [prom(f'sum by (reason)(increase(genlayer_rollup_ws_disconnections_total{{{N}}}[1h]))', "{{reason}}")], 24, 6)

# ---------------------------------------------------------------- Row 7
section("GenVM & LLM", collapsed=True)
panel("timeseries", "GenVM executions / min", "Contract executions per minute. Source: `genlayer_node_genvm_executions_total`.",
      [prom(f'max(rate(genlayer_node_genvm_executions_total{{{N}}}[5m])) * 60', "executions/min")], 8, 7)
panel("timeseries", "GenVM average execution time", "Average seconds per execution. Source: `_genvm_execution_time_seconds_total` / `_genvm_executions_total`.",
      [prom(f'max(rate(genlayer_node_genvm_execution_time_seconds_total{{{N}}}[15m])) / max(rate(genlayer_node_genvm_executions_total{{{N}}}[15m]))', "avg s")],
      8, 7, defaults={"unit": "s"})
panel("timeseries", "GenVM permits", "Free GenVM execution slots. At 0 the node cannot run contracts. Source: `genlayer_node_genvm_permits_current`.",
      [prom(f'max(genlayer_node_genvm_permits_current{{{N}}})', "permits")], 8, 7)
panel("logs", "GenVM errors and timeouts", "GenVM internal errors and timeouts (LLM prompt/response lines are excluded). Source: Loki.",
      [loki(f'{LSEL_RAW}{NOPROMPT} | message=~"GenVM internal error.*|genVM run error.*"')], 24, 8,
      options={"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending"})

# ---------------------------------------------------------------- Row 8
section("Machine", collapsed=True)
panel("timeseries", "CPU % by component", "Source: `genlayer_node_cpu_usage_percent`.",
      [prom(f'max by (component)(genlayer_node_cpu_usage_percent{{{N}}})', "{{component}}")], 12, 7, defaults={"unit": "percent"})
panel("timeseries", "Memory % by component", "Source: `genlayer_node_memory_percent`.",
      [prom(f'max by (component)(genlayer_node_memory_percent{{{N}}})', "{{component}}")], 12, 7, defaults={"unit": "percent"})
panel("timeseries", "Disk used by directory", "Bytes used per data directory, and the disk's overall %. Source: `genlayer_node_disk_usage_bytes`, `_disk_usage_percent`.",
      [prom(f'max by (directory)(genlayer_node_disk_usage_bytes{{{N}}})', "{{directory}}")], 12, 7, defaults={"unit": "bytes"})
panel("timeseries", "Disk % and node network", "Disk % (left) and node network throughput. Webdriver network counters are broken and excluded. Source: `_disk_usage_percent`, `_network_{rx,tx}_bytes_total{component=\"node\"}`.",
      [prom(f'max(genlayer_node_disk_usage_percent{{{N}}})', "disk %", "A"),
       prom(f'max(rate(genlayer_node_network_rx_bytes_total{{{N}, component="node"}}[5m]))', "rx", "B"),
       prom(f'max(rate(genlayer_node_network_tx_bytes_total{{{N}, component="node"}}[5m]))', "tx", "C")], 12, 7,
      overrides=[{"matcher": {"id": "byRegexp", "options": "rx|tx"}, "properties": [{"id": "unit", "value": "Bps"}, {"id": "custom.axisPlacement", "value": "right"}]},
                 {"matcher": {"id": "byName", "options": "disk %"}, "properties": [{"id": "unit", "value": "percent"}]}])
panel("stat", "Uptime", "Time since the node process started. Source: `genlayer_node_uptime_seconds{component=\"node\"}`.",
      [prom(f'max(genlayer_node_uptime_seconds{{{N}, component="node"}})', instant=True)], 6, 4, options=stat_opts(mode="value"), defaults={"unit": "s", "color": {"mode": "fixed", "fixedColor": "text"}})

# ---------------------------------------------------------------- Row 9
section("Logs", collapsed=True)
panel("timeseries", "Errors and warnings per 5 min", "Source: Loki, by level.",
      [loki(f'sum by (level)(count_over_time({LSEL} | level=~"error|warn" [5m]))')], 24, 7,
      defaults={"custom": {"drawStyle": "bars", "fillOpacity": 60}},
      overrides=[{"matcher": {"id": "byName", "options": "error"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]},
                 {"matcher": {"id": "byName", "options": "warn"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "yellow"}}]}])
panel("table", "Most frequent warnings and errors in range", "Source: Loki, grouped by message.",
      [loki(f'topk(20, sum by (level, message)(count_over_time({LSEL} | level=~"error|warn" [$__range])))', instant=True)], 24, 8,
      options={"showHeader": True, "cellHeight": "sm", "sortBy": [{"displayName": "Value", "desc": True}]},
      transformations=[{"id": "reduce", "options": {"reducers": ["lastNotNull"], "mode": "seriesToRows", "labelsToFields": True}}])
panel("logs", "Recent errors", "Source: Loki, level=error.", [loki(f'{LSEL_RAW}{NOPROMPT} | level="error"')], 24, 8,
      options={"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending", "enableLogDetails": True})
panel("logs", "Recent warnings", "Source: Loki, level=warn.", [loki(f'{LSEL_RAW}{NOPROMPT} | level="warn"')], 24, 8,
      options={"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending", "enableLogDetails": True})

# fix the conditions table: drop the placeholder calc, sort non-healthy first via sortBy on state
for p in panels:
    if p.get("title") == "Node conditions now":
        p["transformations"] = [{"id": "organize", "options": {"excludeByName": {"Time": True, "Value": True}}},
                                {"id": "sortBy", "options": {"sort": [{"field": "state", "desc": True}]}}]
        p["options"].pop("sortBy", None)

roster_var_q = {"queryType": "infinity", "refId": "variable",
                "infinityQuery": {"refId": "variable", "type": "json", "source": "url", "parser": "jq-backend", "format": "table",
                                  "url": ROSTER, "url_options": {"method": "GET", "data": ""},
                                  "root_selector": '[.[] | select(.node | startswith("0x")) | {text: ((.name // .moniker // .node) + " — " + .node[0:10]), value: .node}] | unique_by(.value) | sort_by(.text | ascii_downcase)'}}
hex_var_q = {"queryType": "infinity", "refId": "variable",
             "infinityQuery": {"refId": "variable", "type": "json", "source": "url", "parser": "jq-backend", "format": "table",
                               "url": ROSTER, "url_options": {"method": "GET", "data": ""},
                               "root_selector": f'[{{v: ({NODE_LC} | ltrimstr("0x"))}}] '}}

PROFILE_VARS = [
    ("p_name", '[{v: (.validator.metadata.name // "" | if . == "" then "Unnamed validator" else . end)}]'),
    ("p_desc", '[{v: (.validator.metadata.description // "" | if . == "" then "No description set on-chain." else . end)}]'),
    ("p_logo", '[{v: (.validator.metadata.image_url // "" | if . == "" then "<div style=\\"width:128px;height:128px;border-radius:18px;border:1px dashed #888;display:flex;align-items:center;justify-content:center;opacity:.6\\">no logo</div>" '
               'else "<img src=\\"" + . + "\\" style=\\"width:128px;height:128px;border-radius:18px;object-fit:cover\\">" end)}]'),
    ("p_links", '[{v: (.validator.metadata as $m | [(if ($m.url // "") != "" then "<a href=\\"" + $m.url + "\\" target=\\"_blank\\">" + $m.url + "</a>" else empty end), '
                '(if ($m.twitter // "") != "" then "X: " + $m.twitter else empty end), (if ($m.github // "") != "" then "GitHub: " + $m.github else empty end), '
                '(if ($m.telegram // "") != "" then "Telegram: " + $m.telegram else empty end), (if ($m.email // "") != "" then $m.email else empty end)] | if length == 0 then "No links set" else join(" &nbsp;·&nbsp; ") end)}]'),
]
dash = {
    "uid": "gl-validator-profile", "title": "Testnet | Validator Profile",
    "tags": ["validator", "profile"], "timezone": "browser", "editable": True, "schemaVersion": 39,
    "time": {"from": "now-24h", "to": "now"}, "refresh": "1m", "graphTooltip": 1,
    "description": "One validator: who it is, whether it is OK and what to fix, earnings, work done, why it went wrong, and node internals. Design: VALIDATOR-PROFILE-PLAN.md",
    "links": [{"title": "Open in explorer", "type": "link", "url": "https://scan.bradbury.genlayer.com/address/${node}", "targetBlank": True},
              {"title": "Validator Status", "type": "link", "url": "/d/gl-validator-status", "targetBlank": False}],
    "templating": {"list": [
        {"name": "network", "type": "custom", "query": "bradbury-phase2", "current": {"text": "bradbury-phase2", "value": "bradbury-phase2"}, "hide": 2},
        {"name": "node", "label": "Validator", "type": "query", "datasource": INF, "query": roster_var_q, "refresh": 1,
         "current": {"text": "GenLayer Foundation — 0xb0dab7fc", "value": "0xb0dab7fc62e276f5be045b7ec3674f7168623342"}, "sort": 0},
        {"name": "node_hex", "type": "query", "datasource": INF, "query": hex_var_q, "refresh": 1, "hide": 2},
        *[{"name": n, "type": "query", "datasource": INF, "refresh": 1, "hide": 2,
           "query": {"queryType": "infinity", "refId": "variable", "infinityQuery": {"refId": "variable", "type": "json", "source": "url", "parser": "jq-backend",
                     "format": "table", "url": f"{EXP}/address/${{node}}", "url_options": {"method": "GET", "data": ""}, "root_selector": jq}}}
          for n, jq in PROFILE_VARS],
        {"name": "latest_version", "type": "query", "datasource": PROM, "hide": 2, "refresh": 2, "sort": 8,
         "query": {"qryType": 3, "query": 'query_result(count by (version)(genlayer_node_info{network="$network"}))', "refId": "StandardVariableQuery"},
         "regex": '/version="([^"]+)"/', "current": {}},
    ]},
    "panels": panels,
}

NOVAL = {"What's wrong": "Nothing wrong", "Problems seen in range": "No problems in range", "Idle rounds": "No idle rounds"}
def allp():
    for p in panels:
        if p["type"] == "row":
            yield from p.get("panels", [])
        else:
            yield p
for p in allp():
    ds = p["targets"][0]["datasource"]["uid"] if p.get("targets") else ""
    nv = NOVAL.get(p["title"]) or ("No data from this node's telemetry" if ds in ("grafanacloud-prom", "grafanacloud-logs") else "No data")
    p["fieldConfig"]["defaults"].setdefault("noValue", nv)
json.dump(dash, open(sys.argv[1], "w"), indent=1)
print(len(panels), "top-level panels")
