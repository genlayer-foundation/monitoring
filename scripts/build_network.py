"""Derive the per-network copies of the network board from dashboards/foundation/network.json.

network.json (uid gl-testnet-network, the PUBLIC board) is hand-maintained and variable-free:
public dashboards do not interpolate variables, so every network fact in it is a literal.
This script rewrites those literals from one profile in scripts/networks.py to another.

Usage, from the repo root:
    python3 scripts/build_network.py                  # every network whose profile is filled in
    python3 scripts/build_network.py bradbury-phase3  # just that one

  - a network that is not networks.CURRENT -> dashboards/foundation/network_<slug>.json,
    uid gl-testnet-network-<slug>, team-only (no "public" tag);
  - networks.CURRENT -> network.json itself. Nothing to do while network.json already carries
    that network; after CURRENT changes, this converts network.json in place (same uid, so the
    public share and its URL stay) and the old network becomes a network_<slug>.json copy.

Then upload each file it names to Grafana, folder fkpd6m, overwrite.
"""
import json, re, sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import networks as nw

DIR = "dashboards/foundation/"
SRC = DIR + "network.json"
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
    if p["key"] != nw.CURRENT:
        dash.pop("id", None)
        dash.pop("version", None)
        dash["uid"] = nw.uid("gl-testnet-network", p)
        dash["title"] += " | " + p["name"]
        dash["tags"] = [x for x in dash["tags"] if x != "public"]
        dash = json.loads(swap(json.dumps(dash), PROFILE_BOARD, f"/d/{nw.uid('gl-validator-profile', p)}?", "validator-board link"))
    return dash, missing


def main(keys):
    text = open(SRC).read()
    template = [k for k, v in nw.NETWORKS.items() if v["label"] and f'network=\\"{v["label"]}\\"' in text]
    if len(template) != 1:
        raise SystemExit(f"{SRC}: cannot tell which network it carries (found {template})")
    t = nw.profile(template[0])
    text = json.dumps(json.load(open(SRC)))
    for key in keys or [k for k, v in nw.NETWORKS.items() if all(v[f] is not None for f in nw.REQUIRED)]:
        p = nw.profile(key)
        if key == nw.CURRENT == t["key"]:
            print(f"{key}: {SRC} already carries it (hand-maintained source), nothing to do")
            continue
        dash, missing = build(text, t, p)
        if key == nw.CURRENT and missing:
            raise SystemExit(f"{key}: cannot become the public board without: {', '.join(missing)}")
        out = DIR + nw.filename("network", p)
        with open(out, "w") as f:
            json.dump(dash, f, indent=2, ensure_ascii=False)
            f.write("\n")
        note = f" (empty for now: {', '.join(nw.SOURCE_NAMES[m] for m in missing)})" if missing else ""
        print(f"{key}: wrote {out} -> upload as uid {dash['uid']}{note}")


if __name__ == "__main__":
    main(sys.argv[1:])
