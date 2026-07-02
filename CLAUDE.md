# GenLayer Monitoring — Grafana

**Core rule:** always save all changes done in Grafana back to the corresponding
JSON file in this repo (unwrapped dashboard model, pretty-printed). Use the
Grafana MCP server to manage Grafana resources; fall back to the Grafana API for
anything the MCP doesn't support.

## Grafana instance & datasources

- **Instance**: https://genlayerfoundation.grafana.net
- **Datasource UIDs**:
  - Prometheus `grafanacloud-prom` (default)
  - Loki `grafanacloud-logs`
  - Infinity `grafanacloud-infinity`
  - Tempo `grafanacloud-traces`
  - Pyroscope `grafanacloud-profiles`
  - Alertmanager (Grafana-managed)
- MCP service-account token lives in **local Claude config, never commit it**.

## Folder ownership (who owns what — critical)

- **GenLayer Foundation** — uid `fkpd6m` = **OURS**; home for everything we build.
- **GenLayer Labs** uid `dfa1v9yck3ny8b` (Darien) and **Heartbeat** uid
  `heartbeat` (Darien) = **do NOT modify**; copy (never move) if we want to build
  on them. `validator-overview` (49-panel per-validator deep-dive) is Darien's
  reference.
- **5ElementsNodes / Asimov / Bradbury** folders (editor handle `d5en12eb`) =
  5Elements' own dashboards (WOS family, Chain Metrics, LLM). Ours per the user,
  but treat as reference.
- **Retire** the broken root orphans `asimov-wall-of-shame` (old stub) and
  `genlayer-fleet-overview` (deprecated `exported_network` label).

## Our Foundation dashboards (uid → file in `dashboards/foundation/`)

- `gl-testnets-index` → `index.json` — landing page; validator directory table
  (deep-links each row to the profile) + links to the other dashboards.
- `gl-wall-of-shame` → `wall_of_shame.json` — portal↔Grafana reconciliation table,
  with **four summary stat rows** above it (all per-`$network`):
  1. **Validators** — `Total` (union roster ∪ reporting ∪ on-chain active, via the
     A+B+E join, count `node`), `Internal` (roster name/account_name matches
     `genlayer`, case-insensitive), `On-chain active` (live `activeValidators()` —
     which INCLUDES quarantined nodes, see the "quarantine" note below),
     `Quarantined` (live **on-chain** `getAllQuarantinedValidators()`, NOT the
     portal), and portal-status counts `Portal: active` / `Inactive` / `Banned`.
     Note on-chain-active (live) routinely differs from portal-active (portal
     syncs periodically) — showing both is the point.
  2. **Metrics** — `Reporting (metrics)` (`count(genlayer_node_info{…})`),
     `Metrics SHAME` (on-chain active ∖ reporting metrics).
  3. **Logs** — `Reporting (logs)`, `Logs SHAME` (on-chain active ∖ shipping
     logs). Symmetric with the Metrics row. `Reporting (logs)` is a **Loki**
     stat: `count(sum by (node) (count_over_time({job="genlayer-node"} | json |
     network="$network" [5m])))` (count distinct nodes shipping logs in 5m).
     Reporting(logs) usually EXCEEDS Reporting(metrics) — some nodes ship logs
     but not metrics (e.g. BlockPro), which is exactly why logs are joined by
     the `node`/`operator` address from the log JSON, never `validator_name`.
  4. **Versions** (scoped to the on-chain active set, so the three sum to it):
     `Version OK` (active ∩ latest `$latest_version`), `Version behind`
     (active ∩ reporting ∩ older), `Version unknown` (active ∖ reporting — no
     metrics so version can't be read; same set as Metrics SHAME).
  - **Roster status/Internal counts** = single **Infinity `jq-backend`** query on
    the `/grafana/` endpoint returning `[{"c": (… | length)}]`; `$network`
    **interpolates inside `root_selector`** (filter `select(.network=="$network")`),
    confirmed working. Reduce `lastNotNull` on field `c`.
  - **Gotcha — `Value #<refId>` naming**: a stat that joins Infinity(E) + a
    **single** Prometheus target does NOT get the value column suffixed
    (`Value #F` won't exist → filter matches nothing → 0). Give the panel a
    **second** Prometheus target so the suffix appears. That's why `Version OK`
    carries a dummy `B` target alongside `F` even though only `F` is filtered.
  - Removed the old `Max blocks behind` and `Not in portal` stats.
  - **`Participating` column = ON-CHAIN, not portal.** The table's status column
    reads the chain, not the roster. Two Infinity RPC targets feed it: `E` =
    `activeValidators()` (`0xd2d49c4b`) and `Q` =
    `getAllQuarantinedValidators(0,100)` (`0x510a6f26`). A quarantined validator
    is **still in `activeValidators()`** on-chain (quarantine is a pending-ban
    flag with an `untilEpoch`, not removal), so **quarantine takes precedence**
    in the label. Encoded as `PartCode = aflag + 2*qflag` (aflag/qflag =
    reduceRow-sum of `onchain_active E` / `onchain_quarantined Q` with `zeroU`):
    `1 → active` (green), `2`/`3 → quarantined` (orange), `0`/null →
    `not participating` (grey, e.g. reporting-but-not-in-set spectators like
    `genlayerlabs-full-1`). The top `Quarantined` stat counts the same `Q` set.
  - **Decoding `getAllQuarantinedValidators` (and `getAllBannedValidators`
    `0x6461cf56`)**: return is a dynamic array of `(address, uint256
    untilEpochBanned, bool permanentlyBanned)` — 3 words (192 hex) per element,
    vs `activeValidators()`' 1 word. jq-backend `root_selector` skips the
    offset+length header (`.[128:]`), strides **192** hex/element, takes the
    first word's address: `[ range(0; (length/192)) as $i | .[$i*192:($i*192)+64] ]
    | map(... {node, onchain_quarantined:1})`. Body `data` = selector + 32-byte
    `startIndex=0` + 32-byte `size=100` (100 is ample for testnet; more needs
    pagination). NOTE: right now `getAllBannedValidators` returns the SAME set as
    quarantined (all current bans are temporary, `permanentlyBanned:false`), so
    banned is NOT wired separately — using it would double-count.
- `gl-network-status` → `network_status.json` — per-network fleet health
  (metrics-only).
- `gl-validator-profile` → `validator_profile.json` — per-validator drill-down;
  select by **`validator_name`** (primary), node derives from it; has an
  on-chain identity + Wall-of-Shame-status row + health + logs.
  - **Full on-chain identity block** (panels 25/26/27, y=4): reads the whole
    `getIdentity()` tuple in one `eth_call 0x36afc6fa` to `${node}` and decodes
    all fields via `jq-backend`. **Avatar** (id 25, table w/ `image` cell) shows
    `logoUri` — GitHub `blob` URLs are rewritten to `raw.githubusercontent.com`
    in the jq so they render as an image. **On-chain Links** (id 26, stat,
    `reduceOptions.fields="/.*/"` so the string tiles actually render — `""`
    would only pick numeric fields and show blank) shows website/twitter/github/
    email/telegram. **On-chain Description** (id 27, stat). Tuple field order:
    0 moniker, 1 logoUri, 2 website, 3 description, 4 email, 5 twitter,
    6 telegram, 7 github, 8 extraCid(bytes). The three name-comparison stats
    (on-chain moniker / portal account_name / metrics `validator_name`) stay in
    the y=0 row. Note: `node` == the validator wallet contract, so getIdentity()
    is callable straight on it.
  - **Version Status** (id 21, stat, y=22, replaced the old "Fleet Top Version"
    stat): shows **`Up to date`** (green) when the selected node runs the fleet's
    latest version, else **`Behind → <latest>`** (red, includes the version to
    upgrade to), `n/a` if the node isn't reporting. Latest = hidden template var
    **`$latest_version`** (same natural-sort-desc pattern as the Wall of Shame —
    `query_result(count by (version)(genlayer_node_info{network="$network"}))`,
    regex `/version="([^"]+)"/`, `sort: 8`, `current` empty). "Node Version"
    (id 20) still shows the node's own version next to it.
  - **Gotcha — value-mapping text does NOT interpolate `$vars`** (only query
    strings, titles, descriptions do). So the display string is built **in
    PromQL**: `label_replace(count(... version="$latest_version"), "disp", "Up to
    date", "", "") or label_replace((count(node)>=bool 1)*on() group_left()
    absent(... version="$latest_version"), "disp", "Behind → $latest_version",
    "", "")` (`$latest_version` interpolates because it's inside the query),
    format `table`, `reduceOptions.fields="/^disp$/"`, and **regex** value
    mappings color `disp` green/red (`(Up to date)`→green, `(Behind.*)`→red).
  - **Patch-by-index gotcha**: Grafana stores/returns `panels[]` sorted by
    `gridPos` (y,x), which differs from this file's hand order. When patching a
    panel via `update_dashboard` `operations` with `$.panels[N]`, resolve `N`
    from the **live** dashboard (`get_dashboard_property $.panels[*].id`), not the
    file — indexing off the file clobbers the wrong panel.

Always save any Grafana change back to the matching JSON file here.

## Data model & conventions

- **Networks**: the `network` label value is `asimov-phase5` / `bradbury-phase1`
  (NOT the short `asimov`/`bradbury`). Deprecated `exported_network` label is
  broken — don't use it.
- `genlayer_node_info{job="prometheus.scrape.genlayer_node", network=...}` labels:
  - `node` — validator addr, the **JOIN KEY**; **CHECKSUMMED in metrics,
    lowercase in the portal roster** → lowercase BOTH sides before joining.
  - `validator_name` — operator-set display, inconsistent, **NOT a key**.
  - `version`, `commit`, `genvm_version`, `staking_address`.
- **Roster (identity)** via Infinity = the `/grafana/` endpoint (see root
  `CLAUDE.md` → points key facts).
- **Common metrics**: `genlayer_node_blocks_behind`, `_synced` (0/1),
  `_latest_block`, `_synced_block`, `_cpu_usage_percent`, `_memory_percent`,
  `_disk_usage_percent`, `_genvm_permits_current`, `_genvm_executions`,
  `_transactions_activated_total`, `_uptime_seconds{component="node"}`,
  `up{validator_name!=""}`.
- **Logs**: Loki `{job="genlayer-node"} | json | network=... | validator_name=...`.

## Live on-chain "participating" (Wall of Shame)

We read the consensus set **directly from the chain**, not from the portal cache.

- Infinity `url`/POST to RPC `https://zksync-os-testnet-genlayer.zksync.dev`, body:
  ```json
  {"jsonrpc":"2.0","id":1,"method":"eth_call","params":[{"to":"${staking_addr}","data":"0xd2d49c4b"},"latest"]}
  ```
  (`0xd2d49c4b` = `activeValidators()` → `address[]`).
- Parser MUST be **`jq-backend`** (plain `backend` treats `root_selector` as
  JSONata and fails). Tested decoder (skip offset+length words, chunk 64 hex,
  last 40 = address, drop the zero address to match the portal's own filtering):
  ```jq
  .result | ltrimstr("0x") | .[128:] | [range(0;(length/64)) as $i | .[$i*64:($i+1)*64]] | map(select(length==64) | {node:("0x"+(.[24:64]|ascii_downcase)), onchain_active:1}) | map(select(.node != "0x0000000000000000000000000000000000000000"))
  ```
- **Staking contracts**: Asimov `0x63Fa5E0bb10fb6fA98F44726C5518223F767687A`,
  Bradbury `0x4A4449E617F8D10FDeD0b461CadEf83939E821A5`. Per-network target via a
  hidden `staking_addr` template var: Prometheus
  `query_result(topk(1, count by (staking_address)(genlayer_node_info{network="$network"})))`
  + regex `/staking_address="([^"]+)"/` (topk self-corrects one mislabeled
  Bradbury node that carries the Asimov staking_address).

## active vs reporting (DIFFERENT axes — expected to differ)

- **Active** = in the on-chain consensus set (`activeValidators()`).
- **Reporting** = node pushing metrics to Grafana now.
- **Active ∖ Reporting** = the core SHAME (validating but no telemetry).
- **Reporting ∖ Active** = up but not in the set (low stake / infra full-node
  like `genlayerlabs-full-1`, or synced spectators like Nodes.Guru / Finoa).

## Wall of Shame — node version columns ("Node Version" + "Version")

Two columns flag nodes running an outdated release (added in dashboard v14+):

- **Node Version** — the node's actual running version string, straight from the
  `genlayer_node_info.version` label (via query B's `group_left(node, version)`;
  the `version` field is un-hidden in the `organize` transform). `-` if not
  reporting.
- **Version** — `OK` (green) if the node runs the **latest version seen in the
  wild** for that network, `behind` (red) if older, `-` if not reporting. This is
  **fully dynamic — NO manual target** (deliberately decoupled from the points
  system's `TargetNodeVersion`; that lives in the backend, not here).

How the dynamic "latest" works:
- Hidden template var **`$latest_version`** = `query_result(count by (version)
  (genlayer_node_info{...network="$network"}))`, regex `/version="([^"]+)"/`,
  **`sort: 8` (natural desc)** so the auto-selected first option is the max
  semver. Per-network (chained on `$network`). **Keep `current` EMPTY (`{}`) in
  the JSON** — that's what makes it re-pick the max on every load; a saved
  `current` would pin it (sticky) and mis-flag after the fleet upgrades.
- Query **F** = `max by(node)(genlayer_node_info{...network="$network",
  version="$latest_version"})` → value 1 for nodes on the latest. Joined by
  `node`, it becomes `Value #F`.
- Transforms mirror the Metrics/Logs tri-state: `onlatest0 = sum(Value #F,zeroU)`
  (1 if on latest), `hasrep0 = sum(repone,zeroU)` (1 if reporting), `VersionCode
  = hasrep0+onlatest0` (2=OK / 1=behind / 0=n-a, mapped to text+color), and
  `behindFlag = hasrep0-onlatest0` → `ver_s = behindFlag*1000` folded into the
  `severity` reduceRow so behind nodes sort up (weight sits between logs-shame
  1e6 and raw blocks-behind).
- **Renderer caveat**: Grafana's headless image renderer mis-selects the default
  for a chained multi-option var on the **non-default network** — PNG exports of
  bradbury may mis-flag versions. The **live browser dashboard is correct** (it
  applies the natural sort and re-resolves per network). Don't "fix" this by
  pinning `current`.

## Transform gotchas (hard-won)

- `joinByField` (outer) SUFFIXES Infinity-frame fields with ` <refId>` (e.g.
  `status A`, `network A`, `onchain_active E`) while Prometheus/Loki value
  columns collide into `Value #B`, `Value #C`, `Value #D`. Downstream
  filters/organize/overrides must reference the **SUFFIXED** names.
- **Lowercase both `node` sides** before join (metric checksummed, roster
  lowercase).
- Wall of Shame Metrics/Logs are **tri-state**: ON (reporting) / SHAME (on-chain
  active but not reporting) / `-` (not active & not reporting → not expected).

## Reference docs in this repo

- `DASHBOARD-AUDIT.md` — full inventory of all ~42 dashboards + ownership + which
  are dead/duplicate.
- `FOUNDATION-DASHBOARDS-PLAN.md` — identity model, roster decision, dashboard plan.

## Alerts

- `grafana-alerts/*.json` — 9 rules synced from live Grafana; multi-network via
  the `network` label; routing labels `component`/`severity`/`threshold` (legacy
  `asimov-alert` label was dropped).

## Convention

Keep THIS file updated whenever a dashboard/query/convention/gotcha changes —
future sessions rely on it.
