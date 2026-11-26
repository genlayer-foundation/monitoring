"""Network profiles: every per-network fact the Foundation dashboards hard-code.

One entry per network. The generators (build_network.py, build_validator_profile.py)
read nothing else, so adding a network = fill a profile here, run both generators,
upload the two files they name.

A value of None means "not known / not available yet". Never guess one: leave it None.
  - portal_key or explorer None  -> the panels that need that source are generated with
    an empty inline query and say so on the board; everything else is live.
  - any REQUIRED field None      -> the generators refuse to build that network.
"""

import os

PORTAL_ROSTER = "https://portal-admin.genlayer.foundation/api/v1/validators/wallets/grafana/?network="

# The network that owns the UNSUFFIXED uids: gl-testnet-network (the public board,
# dashboards/foundation/network.json) and gl-validator-profile. Every other network
# gets gl-testnet-network-<slug> / gl-validator-profile-<slug>, team-only.
# Changing this line and re-running the generators is how the public URL moves.
# NETWORK_CURRENT / NETWORK_OUT override it for one run, to generate into another folder
# what the boards would be after a move, without changing what is committed as current.
CURRENT = os.environ.get("NETWORK_CURRENT", "bradbury-phase3")
OUT = os.environ.get("NETWORK_OUT", "dashboards/foundation/")

NETWORKS = {
    "bradbury-phase2": {
        "name": "Bradbury Phase 2",        # display name, used in titles and descriptions
        "slug": "phase2",                  # uid + file suffix when the network is not CURRENT
        "label": "bradbury-phase2",        # Prometheus / Loki `network` label (node NETWORK_NAME)
        "portal_key": None,                # ?network=<key> on the portal roster endpoint. Was "bradbury2" until
                                           # 2026-11-25, when the portal switched Phase 2 off (the key now returns [])
        "rpc": "https://rpc.testnet-chain.genlayer.com",
        "chain_explorer": "https://scan.testnet-chain.genlayer.com",
        "explorer": None,                  # GenLayer explorer; its indexer API is <explorer>/api/v1. Phase 2 had
                                           # scan.bradbury.genlayer.com until 2026-11-25, when that host moved to Phase 3
        "staking": "0xD8fBa96C0dBB0257028dBc0107060b958e5c7113",         # emits ValidatorSlash, ValidatorBannedIdleness, ValidatorJoin
        "fees_processor": "0x040a455CA9c6A8Cdc696F6fE603152692D4CA775",  # emits ValidatorPenaltyRecorded
        "genesis_block": 47930,            # AddressManager deployment block: eth_getLogs start
        "appeal_window_s": 60,             # accepted -> finalized gap; "time to acceptance" = finalization - this
        "appeal_window_note": "measured 60-66s on this testnet), so it can read up to ~6s high",
        "boards": False,                   # True = its boards are live in Grafana: the others link to them
        "foundation_node": "0xb0dab7fc62e276f5be045b7ec3674f7168623342",  # validator-profile default; None = no default
        # reference only, no board reads them:
        "address_manager": "0x3F71AE080BD6270A91dBcc7960d88797828538E0",
        "consensus_main": "0x2E2766cbc3E5e61Ce93bBcdCBb3eAcB82082A019",
    },
    # Same chain as Phase 2 (4221): told apart by contract address only.
    # Source: genlayerlabs/genlayer-networks bradbury-phase-3 (deployed 2026-11-24).
    "bradbury-phase3": {
        "name": "Bradbury Phase 3",
        "slug": "phase3",
        "label": "bradbury-phase3",        # carried today only by the Heartbeat monitors; no node pushes it yet (2026-11-25)
        "portal_key": "bradbury3",         # live since 2026-11-25 ~15:45 UTC
        "rpc": "https://rpc.testnet-chain.genlayer.com",
        "chain_explorer": "https://scan.testnet-chain.genlayer.com",
        "explorer": "https://scan.bradbury.genlayer.com",   # serves Phase 3 since 2026-11-25 ~14:00 UTC (was Phase 2's)
        "staking": "0xcE16862EAf10B97A0619BeBb662991fb4a52e346",
        "fees_processor": "0x0c74AC5e70E07C5E10EC8c8fC6D852F36F944Ea4",
        "genesis_block": 694191,           # found by eth_getCode bisection, 2026-11-24 17:03 UTC
        "appeal_window_s": 1800,           # the `decided` timeout; accepted -> finalized measured 1811s on 11 txs, 2026-11-25
        "appeal_window_note": "measured 1811s on this testnet), so it can read up to ~11s high",
        "boards": True,
        "foundation_node": "0xe04bb8b6766dd7baaeacf38a41b1338216e631b7",  # joined 2026-11-25, block 706253
        "address_manager": "0x0192C6C9482251790965B7136352B26234d81d79",
        "consensus_main": "0x0f4F0e05475723790E4a2ed0598370783C300926",
    },
    # Clarke: epoch 0 starts 2026-11-26 and runs alongside Phase 3. Nothing is known here yet.
    "clarke": {
        "name": "Clarke",
        "slug": "clarke",
        "label": None,                     # TODO: count by (network)(genlayer_node_info)
        "portal_key": None,                # TODO: ask the portal
        "rpc": None,                       # TODO
        "chain_explorer": None,            # TODO
        "explorer": None,                  # TODO
        "staking": None,                   # TODO: deployment book, key "Staking"
        "fees_processor": None,            # TODO: deployment book, key "FeesProcessor"
        "genesis_block": None,             # TODO: AddressManager deployment block
        "appeal_window_s": None,           # TODO: measure via <explorer>/api/v1/transactions/consensus-steps/<hash>
        "appeal_window_note": None,        # TODO: "measured <n>s on this testnet), so it can read up to ~<m>s high"
        "address_manager": None,
        "consensus_main": None,
    },
}

REQUIRED = ("name", "slug", "label", "rpc", "chain_explorer", "staking", "fees_processor", "genesis_block")
UNAVAILABLE = "unavailable://"  # placeholder URL scheme; stub_unavailable() turns it into an empty query
SOURCE_NAMES = {"roster": "portal roster", "explorer": "GenLayer explorer"}


def profile(key):
    """The profile for `key`, or exit with the list of what is still missing."""
    if key not in NETWORKS:
        raise SystemExit(f"unknown network {key!r}; profiles: {', '.join(NETWORKS)}")
    p = dict(NETWORKS[key], key=key)
    missing = [f for f in REQUIRED if p[f] is None]
    if missing:
        raise SystemExit(f"{key}: fill these in scripts/networks.py first: {', '.join(missing)}")
    if p["explorer"] and None in (p["appeal_window_s"], p["appeal_window_note"]):
        raise SystemExit(f"{key}: an explorer is set, so appeal_window_s and appeal_window_note must be too")
    return p


def roster_url(p):
    return PORTAL_ROSTER + p["portal_key"] if p["portal_key"] else UNAVAILABLE + "roster"


def explorer_api(p):
    return p["explorer"] + "/api/v1" if p["explorer"] else UNAVAILABLE + "explorer"


def explorer_site(p):
    return p["explorer"] or UNAVAILABLE + "explorer-site"


def uid(base, p):
    return base if p["key"] == CURRENT else f"{base}-{p['slug']}"


def filename(base, p):
    return f"{base}.json" if p["key"] == CURRENT else f"{base}_{p['slug']}.json"


def board_links(p, base, label="{name}"):
    """Dashboard links from `p`'s board to the `base` board of every other network with live boards."""
    others = [dict(v, key=k) for k, v in NETWORKS.items() if v.get("boards") and k != p["key"]]
    return [{"title": label.format(name=q["name"]), "type": "link", "icon": "dashboard",
             "url": f"/d/{uid(base, q)}", "targetBlank": False} for q in others]


def _panels(panels):
    for p in panels:
        yield p
        yield from _panels(p.get("panels", []))


def _drop_links(obj):
    """Remove every link whose url points at a site the profile does not have."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, list) and v and all(isinstance(i, dict) and "url" in i for i in v):
                obj[k] = [i for i in v if not str(i["url"]).startswith(UNAVAILABLE)]
            _drop_links(obj[k])
    elif isinstance(obj, list):
        for i in obj:
            _drop_links(i)


def stub_unavailable(dash, p, keep_jq=()):
    """Turn every Infinity query aimed at an UNAVAILABLE source into an empty inline query.

    The panel then reads "No data" (with the reason) instead of erroring, and the board keeps
    its layout, so filling the profile in later only swaps the data in. `keep_jq` names the
    variables whose jq does not read its input and must survive. Returns the missing sources.
    """
    missing = set()

    def stub(q, keep=False):
        src = q["url"][len(UNAVAILABLE):].split("/")[0]
        missing.add(src)
        jq = q["root_selector"] if keep else "[]"
        for k in [k for k in q if k not in ("datasource", "refId", "type", "parser", "format", "hide")]:
            del q[k]
        q.update(source="inline", data="[]", root_selector=jq)
        return src

    for panel in _panels(dash["panels"]):
        gone = [stub(t) for t in panel.get("targets", []) if str(t.get("url", "")).startswith(UNAVAILABLE)]
        if gone:
            why = " and ".join(SOURCE_NAMES[s] for s in sorted(set(gone)))
            if len(gone) == len(panel["targets"]):
                panel.setdefault("fieldConfig", {}).setdefault("defaults", {})["noValue"] = f"No {why} for {p['name']} yet"
            panel["description"] = f"[Incomplete: no {why} for {p['name']} yet.] " + panel.get("description", "")
    for var in dash.get("templating", {}).get("list", []):
        q = var.get("query")
        if isinstance(q, dict) and str(q.get("infinityQuery", {}).get("url", "")).startswith(UNAVAILABLE):
            stub(q["infinityQuery"], keep=var["name"] in keep_jq)
    _drop_links(dash)
    if missing:
        names = " and ".join(SOURCE_NAMES[s] for s in sorted(missing))
        for panel in _panels(dash["panels"]):
            panel["gridPos"]["y"] += 2
        dash["panels"].insert(0, {
            "id": max(x["id"] for x in _panels(dash["panels"])) + 1, "type": "text", "title": "",
            "gridPos": {"h": 2, "w": 24, "x": 0, "y": 0}, "transparent": True,
            "options": {"mode": "markdown", "content":
                        f"**{p['name']} has no {names} yet.** Panels that need it read \"No data\"; "
                        "chain and node-telemetry panels are live. Set the value in `scripts/networks.py` and regenerate."}})
    return sorted(missing)
