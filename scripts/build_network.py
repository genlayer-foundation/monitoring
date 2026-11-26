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

    missing = nw.stub_unavailable(dash, p)
    if p.get("roster_empty"):  # the roster key exists but lists nobody yet: an empty panel is not good news
        for panel in nw._panels(dash["panels"]):
            if panel.get("fieldConfig", {}).get("defaults", {}).get("noValue") == "Every graduated validator is on this network":
                panel["fieldConfig"]["defaults"]["noValue"] = f"The portal lists nobody for {p['name']} yet"
                panel["description"] = (f"[The portal roster for {p['name']} is empty so far: no validator has joined and "
                                        "the portal does not list who is missing yet.] " + panel.get("description", ""))
        note = (f"**The portal roster for {p['name']} is empty so far**: nobody has joined yet, so the validator panels "
                "and Open issues read zero or \"No data\"; they fill in as validators join.")
        banner = next((x for x in dash["panels"] if x["type"] == "text" and x["gridPos"]["y"] == 0), None)
        if banner:
            banner["options"]["content"] += "\n\n" + note
            banner["gridPos"]["h"] = 3
            for x in dash["panels"]:
                if x is not banner:
                    x["gridPos"]["y"] += 1
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
