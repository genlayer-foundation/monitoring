"""Generate every network's copy of the network board from scripts/network.template.json.

The board is variable-free (public dashboards do not interpolate variables), so every network
fact in it is a literal. The template is the complete board, with every panel's real query,
carrying the literals in TEMPLATE below. This script rewrites them to a profile from
scripts/networks.py. Change a panel in the template, never in the generated files.

Usage, from the repo root:
    python3 scripts/build_network.py                  # every network whose profile is filled in
    python3 scripts/build_network.py bradbury-phase3  # just that one

  - networks.CURRENT -> dashboards/foundation/network.json, uid gl-testnet-network (the PUBLIC
    board: same uid whatever the network, so the public share and its URL stay);
  - any other network -> dashboards/foundation/network_<slug>.json, uid
    gl-testnet-network-<slug>, team-only (no "public" tag).

Then upload each file it names to Grafana, folder fkpd6m, overwrite.
"""
import json, re, sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import networks as nw

DIR = nw.OUT
SRC = "scripts/network.template.json"
# The literals the template carries. Frozen with the template: they say what to look for in it,
# not what any network is today (profiles change; e.g. this explorer host now serves Phase 3).
TEMPLATE = {
    "key": "template", "name": "Bradbury Phase 2", "label": "bradbury-phase2", "portal_key": "bradbury2",
    "rpc": "https://rpc.testnet-chain.genlayer.com", "chain_explorer": "https://scan.testnet-chain.genlayer.com",
    "explorer": "https://scan.bradbury.genlayer.com", "staking": "0xD8fBa96C0dBB0257028dBc0107060b958e5c7113",
    "appeal_window_s": 60, "appeal_window_note": "measured 60-66s on this testnet), so it can read up to ~6s high",
}
PROFILE_BOARD = "/d/gl-validator-profile?"
# who emits which penalty event (genlayer-consensus); used as the eth_getLogs address filter
EMITTER = {
    "0xa627246e5775111863fbcde9461dd14307b2830d3cbe4c384728da5bb175fbe0": "staking",         # ValidatorSlash
    "0x46cda53c301fdcf68b170f57e98b59fbc32ad0d522bdd36278d635e4750ac520": "staking",         # ValidatorBannedIdleness
    "0xb53a9a4243f44525ba76af0beaa6c0feaf0d4531da91814112747f4c60313fa9": "fees_processor",  # ValidatorPenaltyRecorded
}


def swap(text, old, new, what):
    if old not in text:
        raise SystemExit(f"{SRC}: expected the template's {what} ({old}) and did not find it")
    return text.replace(old, new)


JOIN_TOPIC = "0x2b7297b31452d0a13e57c605870ec3c9b4ac6ef33e5cbae7a0f00bc2a3e96782"  # ValidatorJoin(operator, validator, amount)
H2I = 'def h2i: ascii_downcase | reduce (explode[]) as $c (0; .*16 + (if $c>=97 then $c-87 else $c-48 end)); '


def join_target(p, ref, jq):
    """An Infinity target over every ValidatorJoin this network's Staking emitted since genesis.

    Data words: operator, validator, amount (none indexed). The chain, not the portal or the
    explorer, so it works on a network with neither and on the public share."""
    call = {"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs",
            "params": [{"address": p["staking"], "fromBlock": hex(p["genesis_block"]), "toBlock": "latest", "topics": [JOIN_TOPIC]}]}
    return {"refId": ref, "datasource": {"type": "yesoreyeram-infinity-datasource", "uid": "grafanacloud-infinity"},
            "type": "json", "source": "url", "parser": "jq-backend", "format": "table", "method": "POST",
            "url": p["rpc"], "url_options": {"method": "POST", "body_type": "raw", "body_content_type": "application/json",
                                             "data": json.dumps(call, separators=(",", ":"))},
            "root_selector": H2I + jq, "filters": [], "columns": []}


def show_joined(dash, p):
    """Profile `joined_label` set: list every validator that has joined, not only the current set.

    While nobody is selectable (Clarke's epoch 0) the current-set table is empty although
    validators have registered. Joined = a portal roster row with a real wallet (status not
    `missing`; the portal syncs these from the Staking contract). The roster, not the chain, because
    the public RPC answers 429 when a full board loads and the portal endpoint is cached. Adds a
    Joined count on the Validator set stat, every joined wallet in the Validators table (portal
    health replaced by `joined_label` while the portal says `inactive`), and a Latest joins table
    (chain ValidatorJoin events: the only source with a join time)."""
    panels = {x["id"]: x for x in nw._panels(dash["panels"])}
    real = '(.status != "missing" and ((.node // "") | startswith("0x")))'
    roster = panels[24]["targets"][0]
    # 1. Validator set stat: + Joined (roster)
    vs = panels[1]
    rj = json.loads(json.dumps(roster))
    rj.update(refId="J", columns=[], root_selector=f'[{{Joined: ([.[] | select({real}) | .node | ascii_downcase] | unique | length)}}]')
    vs["targets"].append(rj)
    vs["fieldConfig"]["overrides"].append({"matcher": {"id": "byName", "options": "Joined"},
                                           "properties": [{"id": "displayName", "value": "Joined"}, {"id": "color", "value": {"fixedColor": "text", "mode": "fixed"}}]})
    vs["description"] += " Joined = every validator wallet the portal roster lists on this network (synced from the Staking contract), active or not."
    # 2. Validators table: every joined wallet passes the filter
    vt = panels[24]
    rs = roster["root_selector"]
    for old, new in (("health_txt: (", f'joined: (if {real} then 1 else 0 end), health_txt: (if .status == "inactive" and ((.node // "") | startswith("0x")) then "yellow|{p["joined_label"]}" else ('),
                     (", hrank: (", " end), hrank: (")):
        assert rs.count(old) == 1, old
        rs = rs.replace(old, new, 1)
    roster["root_selector"] = rs
    roster["columns"].append({"selector": "joined", "text": "joined", "type": "number"})  # Infinity emits listed columns only
    for o in vt["fieldConfig"]["overrides"]:  # room for the label
        if o["matcher"] == {"id": "byName", "options": "Health"}:
            for prop in o["properties"]:
                if prop["id"] == "custom.width":
                    prop["value"] = max(prop["value"], 7 * len(p["joined_label"]) + 30)
    tr = vt["transformations"]
    for x in tr:
        o = x["options"]
        if o.get("alias") == "universalone":  # field names lose their " A" suffix when RPC frames are missing (429)
            o["reduce"]["include"] += ["rone", "joined A", "joined"]
        if o.get("alias") == "shown":
            x["options"] = {"alias": "shown", "replaceFields": False, "mode": "reduceRow",
                            "reduce": {"include": ["live1", "pendflag", "joinflag"], "reducer": "sum"}}
            i = tr.index(x)
        if x["id"] == "organize":
            o["excludeByName"].update({"joined A": True, "joined": True, "joinflag": True})
    tr.insert(i, {"id": "calculateField", "options": {"alias": "joinflag", "replaceFields": False, "mode": "reduceRow",
                                                     "reduce": {"include": ["joined A", "joined", "zeroU"], "reducer": "sum"}}})
    vt["description"] = (f"[{p['name']}: also lists every validator the portal roster has on this network but that is not "
                         f"in the set yet, marked \"{p['joined_label']}\" in Health.] " + vt.get("description", ""))
    # 3. Latest joins, beside the not-on-this-network panel
    nj = panels[30]
    nj["gridPos"]["w"] = 12
    rost = json.loads(json.dumps(roster))
    rost.update(refId="R", columns=[], root_selector=f'[.[] | select({real}) | {{node: (.node | ascii_downcase), name: (if (.account_name // "") != "" then .account_name elif (.moniker // "") != "" then .moniker else .name end)}}]')
    logs = join_target(p, "J", '[.result[] | {node: ("0x" + (.data[90:130] | ascii_downcase)), joined_ms: ((.blockTimestamp | ltrimstr("0x") | h2i) * 1000), stake_gen: ((.data[130:194] | h2i) / 1e18 | round)}]')
    dash["panels"].append({
        "id": max(panels) + 1, "type": "table", "title": "Latest joins",
        "description": "Every validator wallet that has joined this network, newest first: when, with how much self stake, and its name from the portal when the portal knows it. Source: staking `ValidatorJoin` events since genesis (chain) + the portal roster for names. The public RPC rate-limits (429) when the whole board loads at once: if this reads empty with a red badge, refresh the panel.",
        "datasource": {"type": "yesoreyeram-infinity-datasource", "uid": "grafanacloud-infinity"},
        "gridPos": {"h": nj["gridPos"]["h"], "w": 12, "x": 12, "y": nj["gridPos"]["y"]},
        "targets": [logs, rost],
        "transformations": [
            {"id": "joinByField", "options": {"byField": "node", "mode": "outer"}},
            {"id": "filterByValue", "options": {"filters": [{"config": {"id": "isNotNull", "options": {}}, "fieldName": "joined_ms J"}], "match": "all", "type": "include"}},
            # firstNotNull walks fields in frame order, not include order: copy the address to the end first
            {"id": "calculateField", "options": {"alias": "node_last", "mode": "reduceRow", "reduce": {"include": ["node"], "reducer": "firstNotNull"}, "replaceFields": False}},
            {"id": "calculateField", "options": {"alias": "Validator", "mode": "reduceRow", "reduce": {"include": ["name R", "name", "node_last"], "reducer": "firstNotNull"}, "replaceFields": False}},
            {"id": "convertFieldType", "options": {"conversions": [{"destinationType": "time", "targetField": "joined_ms J"}, {"destinationType": "string", "targetField": "Validator"}], "fields": {}}},
            {"id": "sortBy", "options": {"fields": {}, "sort": [{"desc": True, "field": "joined_ms J"}]}},
            {"id": "organize", "options": {"excludeByName": {"name R": True, "name": True, "node_last": True},
                                           "indexByName": {"joined_ms J": 0, "Validator": 1, "stake_gen J": 2, "node": 3},
                                           "renameByName": {"joined_ms J": "Joined", "stake_gen J": "Self stake (GEN)", "node": "Address"}}}],
        "fieldConfig": {"defaults": {"custom": {"align": "left", "cellOptions": {"type": "auto"}, "filterable": True},
                                     "noValue": f"No validator has joined {p['name']} yet"},
                        "overrides": [{"matcher": {"id": "byName", "options": "Joined"}, "properties": [{"id": "unit", "value": "dateTimeAsIso"}, {"id": "custom.width", "value": 170}]},
                                      {"matcher": {"id": "byName", "options": "Self stake (GEN)"}, "properties": [{"id": "decimals", "value": 0}, {"id": "custom.width", "value": 130}]}]},
        "options": {"cellHeight": "sm", "footer": {"countRows": True, "fields": "", "reducer": ["count"], "show": True}, "showHeader": True, "sortBy": []}})


def build(text, t, p):
    """The board for profile `p`, from the template text that carries profile `t`."""
    text = swap(text, nw.explorer_api(t), nw.explorer_api(p), "explorer API")
    text = swap(text, nw.explorer_site(t), nw.explorer_site(p), "explorer site")
    text = swap(text, nw.roster_url(t), nw.roster_url(p), "roster URL")
    for field in ("label", "staking", "rpc", "chain_explorer", "name"):
        text = swap(text, t[field], p[field], field)
    if p["explorer"]:  # "time to acceptance" = finalization - appeal window, in the explorer jq
        text, n = re.subn(rf"(\.finalization_timestamp(?: - \.activation_timestamp)?) - {t['appeal_window_s']}\)",
                          rf"\1 - {p['appeal_window_s']})", text)
        if not n:
            raise SystemExit(f"{SRC}: appeal-window arithmetic not found")
        text = text.replace(f"{t['appeal_window_s']}s appeal window", f"{p['appeal_window_s']}s appeal window")
        text = swap(text, t["appeal_window_note"], p["appeal_window_note"], "appeal-window note")
    dash = json.loads(text)

    # penalty events: this network's emitter and genesis only (several deployments share the chain)
    for panel in nw._panels(dash["panels"]):
        for target in panel.get("targets", []):
            body = target.get("url_options", {}).get("data", "")
            if '"eth_getLogs"' in body:
                call = json.loads(body)
                topic = call["params"][0]["topics"][0]
                call["params"][0] = {"address": p[EMITTER[topic]], "fromBlock": hex(p["genesis_block"]),
                                     "toBlock": "latest", "topics": [topic]}
                target["url_options"]["data"] = json.dumps(call, separators=(",", ":"))

    if p.get("joined_label"):
        show_joined(dash, p)
    missing = nw.stub_unavailable(dash, p)
    if p.get("roster_no_missing_rows"):  # the portal does not list who is absent: an empty panel is not good news
        for panel in nw._panels(dash["panels"]):
            if panel.get("fieldConfig", {}).get("defaults", {}).get("noValue") == "Every validator is on this network":
                panel["fieldConfig"]["defaults"]["noValue"] = f"The portal does not list who is missing on {p['name']} yet"
                panel["description"] = (f"[The portal roster for {p['name']} has no `missing` rows yet, so this panel "
                                        "cannot say who has not joined.] " + panel.get("description", ""))
    # the boards of the other networks running in parallel (team-only boards: a link from the
    # public board needs a login; public dashboards do not show dashboard links anyway)
    dash["links"] = nw.board_links(p, "gl-testnet-network", "{name} board") + dash.get("links", [])
    links_md = nw.public_links_markdown(p)
    if links_md:  # a link public viewers can follow: the link bar is hidden on public dashboards
        for panel in dash["panels"]:
            panel["gridPos"]["y"] += 2
        dash["panels"].insert(0, {
            "id": max(x["id"] for x in nw._panels(dash["panels"])) + 1, "type": "text", "title": "",
            "gridPos": {"h": 2, "w": 24, "x": 0, "y": 0}, "transparent": True,
            "options": {"mode": "markdown", "content": links_md}})
    if p["key"] != nw.CURRENT:
        dash.pop("id", None)
        dash.pop("version", None)
        dash["uid"] = nw.uid("gl-testnet-network", p)
        dash["title"] += " | " + p["name"]
        dash["tags"] = [x for x in dash["tags"] if x != "public" or p.get("public_token")]
        dash = json.loads(swap(json.dumps(dash), PROFILE_BOARD, f"/d/{nw.uid('gl-validator-profile', p)}?", "validator-board link"))
    return dash, missing


def main(keys):
    text = json.dumps(json.load(open(SRC)), ensure_ascii=False)
    for key in keys or [k for k, v in nw.NETWORKS.items() if all(v[f] is not None for f in nw.REQUIRED)]:
        p = nw.profile(key)
        dash, missing = build(text, TEMPLATE, p)
        out = DIR + nw.filename("network", p)
        with open(out, "w") as f:
            json.dump(dash, f, indent=2, ensure_ascii=False)
            f.write("\n")
        note = f" (empty for now: {', '.join(nw.SOURCE_NAMES[m] for m in missing)})" if missing else ""
        public = " [PUBLIC board]" if key == nw.CURRENT else ""
        print(f"{key}: wrote {out} -> upload as uid {dash['uid']}{public}{note}")


if __name__ == "__main__":
    main(sys.argv[1:])
