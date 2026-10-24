# GenLayer Monitoring — Grafana

**Core rule:** always save all changes done in Grafana back to the corresponding
JSON file in this repo (unwrapped dashboard model, pretty-printed). Use the
Grafana MCP server to manage Grafana resources; fall back to the Grafana API for
anything the MCP doesn't support.

## Current network — Bradbury Phase 2 (since 2026-10-20)

The testnet restarted on **Arbitrum Orbit (Conduit)**, replacing ZKsync. **Asimov
(`asimov-phase5`) and Bradbury Phase 1 (`bradbury-phase1`) are sunset**; the only
network on the Foundation dashboards is **Bradbury Phase 2**:

- RPC `https://rpc.testnet-chain.genlayer.com` (chainId 4221, same as before).
  The old `https://zksync-os-testnet-genlayer.zksync.dev` still answers (old chain,
  still producing blocks) — don't point anything at it.
- Staking proxy `0xD8fBa96C0dBB0257028dBc0107060b958e5c7113` (routed "diamond";
  raw `IGenLayerStaking` ABI, genlayer-consensus `deployments/bradbury-phase-2.json`).
- Grafana `network` label **`bradbury-phase2`** (no hyphen before the 2) — the
  documented value: `NETWORK_NAME=bradbury-phase2` in
  https://docs.genlayer.com/validators/monitoring, and the setup guide says the node
  names the network `bradbury-phase2` from its consensus address. Not yet observed:
  as of 2026-10-20 no Prometheus or Loki series carries it. When the first Phase 2
  node reports, confirm with `count by (network)(genlayer_node_info)`; if it differs,
  change it in every dashboard's `network` var, `index.json` and the generator's
  `NETWORKS`. (`bradbury-phase-2` with a hyphen was a wrong guess, fixed 2026-10-20.)
- Portal roster network key is **`bradbury2`** (not the Grafana label): every roster
  target calls `/api/v1/validators/wallets/grafana/?network=bradbury2` and filters
  server-side; the jq no longer does `select(.network=="$network")`. The `index`
  directory deep-links with a hardcoded `var-network=bradbury-phase2` because the
  roster's `network` field is the portal key, not the label.
- **ABI changes** that hit the dashboards: `activeValidators()` `0xd2d49c4b` is
  **retired (reverts)** → replaced by **`selectableValidators()` `0x2d2f135d`** (same
  `address[]` ABI, same jq decoder). It is strict consensus-duty eligibility: it
  **excludes quarantined** validators (the old set included them) and is **empty
  until the first epoch advance**. `getActiveValidatorsList` does not exist on the
  router either. Unchanged and verified on the new chain: `epoch()` `0x900cf0cf`,
  `getAllQuarantinedValidators(uint256,uint256)` `0x510a6f26` (still 3-word
  elements), `getIdentity()` `0x36afc6fa` on the wallet. `validatorView` (9 words now)
  is not used by any dashboard.
- **Owner vs wallet**: the factory's first two Phase 2 validators are wallets
  `0x140457fb2eab027161a6ccdb378544dce3ea3a1d` (owner `0x5463…d866`, 500 GEN) and
  `0xf00f26f5b1a30953af621c8abfd70d8106c3f0c4` (owner `0x3850…147c`, 0.01 GEN). The
  `node` join key is the **wallet**, never the owner.
- Alerts (`grafana-alerts/`) are label-agnostic — no `network` filter in any expr,
  `network` is only carried through `by()` and templates — so they need no change.

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
- **Retired** (deleted from Grafana, JSON recoverable from git history):
  `asimov-wall-of-shame` (dead stub, 2026-07-01); `genlayer-fleet-overview`
  (deprecated `exported_network` label) and the `fede/*` scratch boards
  (`fedngdj`/`fe75g2b`/`feb9fvx`), all 2026-07-03. The empty `fede` folder
  (uid `af7w864ddjnr4f`) still exists in Grafana. `gl-wall-of-shame` /
  `gl-wos-public` were superseded 2026-07-30 by `gl-validator-status` /
  `gl-validator-status-public` (uid+file rename, same content).

## Our Foundation dashboards (uid → file in `dashboards/foundation/`)

- `gl-testnets-index` → `index.json` — landing page; validator directory table
  (deep-links each row to the profile) + links to the other dashboards. Since
  2026-10-20: two Bradbury Phase 2 stats (reporting / synced, `or on() vector(0)`
  so they read 0, not No data) replace the four Asimov/Bradbury ones.
- `gl-preclarke-status` → `preclarke_status.json` — ⚠️ **Status 2026-10-20: left
  unchanged, likely stale.** `https://rpc-bradbury.genlayer.com` still answers but is
  the OLD ZKsync chain (same head as the zksync RPC; Pre-Clarke `epoch()` = 139), the
  explorer API still lists 25 validators / 15 active, and **no Prometheus or Loki
  series carries `network="pre-clarke"`**. Ask whether Pre-Clarke is retired before
  repointing or deleting it. **Pre-Clarke network status**,
  a self-contained, portal-free validator-status page for the **Pre-Clarke**
  network. Pre-Clarke runs on the **Bradbury chain (chainId 4221,
  `https://rpc-bradbury.genlayer.com`)** with a SEPARATE consensus deployment
  (`deployment_vesting_pre_clarke`); staking `0x500261a6b5F93Bc940Fb05624a3f1B9A3CE843e3`.
  It has **no portal roster**, so the validator list comes straight from the
  **explorer chain-indexer API** and is cross-checked against Grafana telemetry.
  **PUBLICLY SHARED** (Grafana public dashboard, no login):
  `https://genlayerfoundation.grafana.net/public-dashboards/7147dc0ed75d4d3f9c05d84cb98c0520`.
  Built 2026-07-09; at launch epoch 0 all 9 validators are `pending`/primed (they
  activate at the next epoch boundary). Design notes / gotchas:
  - **Validator source = the explorer API, NOT raw RPC.** `activeValidators()` on
    the staking contract is EMPTY at epoch 0 (new validators are `inactive` until
    the next epoch), so it would show nothing while the explorer lists 9. Use
    `GET https://internal-explorer.genlayer.com/api/v1/validators?page_size=100`
    (public, no auth) — returns `{total, validators:[{validator_address, self_stake,
    delegated_stake, banned_until_epoch, is_active, is_primed_next_epoch, status,
    operator_address, owner_address, metadata:{name,…}, …}]}`. The table's `V`
    Infinity target maps each to `{node:(validator_address|lc), name:metadata.name,
    statuscode, sortweight, stake:(self_stake/1e18), operator, activeflag, rowflag:1}`.
    `statuscode`: banned=3 / active=1 / primed=2 / pending=0 → colored
    active(green)/primed·next epoch(blue)/pending(grey)/banned(red).
  - **Stats** (Infinity API + telemetry): Validators (`.total`), Active
    (`is_active` count), Primed·next epoch (`is_primed_next_epoch && !is_active`),
    Reporting (metrics) = `count(genlayer_node_info{network="pre-clarke", node!=""})`,
    Reporting (logs) = Loki distinct nodes, Epoch = on-chain `epoch()` (selector
    **`0x900cf0cf`**) decoded via `hexval`. **`node!=""` matters**: a non-validator
    full node `preclarke-full-1` reports metrics but has no `node` label — without
    the filter the metrics stat shows 1 while every validator's Metrics cell is `-`
    (Ivan caught this). Filtering to `node!=""` counts only real validators →
    consistent with the table. Prometheus/Loki stats end with `or on() vector(0)`
    so they read `0` pre-launch, not "No data".
  - **No template vars** (network + staking address hardcoded in every query).
    REQUIRED for public dashboards: public mode does **NOT interpolate template
    variables inside Infinity RPC bodies** (`${staking_addr}` stayed literal →
    `eth_call` to a bad address → `ltrimstr("0x") cannot be applied to: null`).
  - **Telemetry join by `node` address** (lowercased both sides — the metrics/logs
    `node` label is CHECKSUMMED, the API side is `ascii_downcase`'d; the leading
    `formatString → Lower Case` on `node` handles it and DOES lowercase all frames).
    Validators get a `node` label once they run a node; the tri-state Metrics/Logs
    math mirrors the main Wall of Shame (`MetricsCode` 2=ON/1=OFF/0=`-`, OFF only
    when `is_active` and not reporting). `I`/`L` targets filter `node!=""` to drop
    the node-less full node.
  - **GOTCHA — the Prometheus value column is `Value`, the Loki one is `Value #L`
    (NOT `Value #I`).** With frames V (Infinity, no Value field), I (Prometheus),
    L (Loki), Grafana keeps the FIRST value frame's name bare (`Value` ← Prometheus)
    and only suffixes the colliding second (`Value #L` ← Loki). Reference `Value`
    for metrics and `Value #L` for logs. Symptom of getting this wrong: the node
    pushes fine, the join matches (Node Version populates), but Metrics stays `-`
    while Logs shows ON — because `Value #I` doesn't exist so `hasm0` is always 0.
    (This — NOT any address case mismatch — was the real "my node reports but Metrics
    shows -" bug; the join/lowercasing was always fine.)
  - **GOTCHA — `joinByField` renames Infinity-frame field NAMES to `<field> V`
    (the frame's refId), not just displayName.** The join key (`node`) and
    post-join `calculateField` aliases (`MetricsCode`, `LogsCode`) keep clean
    names, but the `V` target's own fields become `name V` / `statuscode V` /
    `stake V` / `operator V` / `activeflag V` / `rowflag V` / `sortweight V`. ALL
    transform refs AND field overrides for those must use the ` V` suffix; column
    renames are done via **field overrides** (`byName "name V"` → `displayName
    "Name"`), because `organize.renameByName` sets displayName but does NOT win over
    the join's displayName reliably. `renameByName` / `renameByRegex` operate on
    `field.name` and did NOT help here.
  - **GOTCHA — after a full `overwrite`, panel INDEX shifts.** This board is
    `[100,10,11,12,13,14,15,1]` so the **table is `panels[7]`** (id 1), not
    `panels[6]` (the Epoch stat). Patch ops must resolve the index from the LIVE
    dashboard (`$.dashboard.panels | to_entries[] | {idx,id}`) — I burned a long
    loop editing the Epoch stat thinking it was the table, and misread a stale
    image renderer as "caching" (busting cache via `theme=light` confirmed the
    table was simply never being changed).
- `genlayer-foundation-overview-v4` → `validator_overview.json` — display title
  **"GenLayer Foundation | Validator Overview"**; first committed 2026-10-21 (was
  UI-only). Table names come from the portal roster (`bradbury2`), Metrics/Logs from
  native Prometheus/Loki targets joined on lowercased `node`. Until v7 it called
  Grafana's `/api/ds/query` with a service-account token pasted into the Infinity
  header — never put a credential in a dashboard; use the native datasources.
  Default `network` is `bradbury-phase2` (was `bradbury-phase1` until 2026-10-24);
  the hidden `explorer_url` lookup maps it to `https://scan.testnet-chain.genlayer.com`.
- `gl-validator-status` → `validator_status.json` — display title **"Testnet |
  Validator Status"** (formerly "Wall of Shame" — display titles renamed 2026-07
  for validator-facing neutrality; uid + filenames + generator renamed too on
  2026-07-30, old uid was `gl-wall-of-shame`; displayed "SHAME" strings replaced
  2026-07-31 — stat titles are now "Not reporting (metrics/logs)" and table/stat
  cells show ON/OFF/-. The `wall-of-shame` tag and the internal shorthand
  "Wall of Shame"/"WoS"/"SHAME" in THIS DOC deliberately keep the old name).
  Portal↔Grafana reconciliation table,
  with **four summary stat rows** above it (all per-`$network`):
  1. **Validators** — `Total` (union roster ∪ reporting ∪ on-chain active, via the
     A+B+E join, count `node`), `Internal` (roster name/account_name matches
     `genlayer`, case-insensitive), `On-chain active` (live `selectableValidators()`
     since Phase 2 — EXCLUDES quarantined nodes and is empty until the first epoch
     advance; was `activeValidators()`, which included them),
     `Quarantined` (live **on-chain** `getAllQuarantinedValidators()`, NOT the
     portal), portal-status counts `Portal: active` / `Inactive` / `Banned`, and
     `Missing` (graduated validators with no wallet linked on this network — see
     the "Missing graduated validators" note below).
     Note on-chain-active (live) routinely differs from portal-active (portal
     syncs periodically) — showing both is the point.
  2. **Metrics** — `Reporting (metrics)` (`count(genlayer_node_info{…})`),
     `Not reporting (metrics)` (on-chain active ∖ reporting metrics; was
     "Metrics SHAME").
  3. **Logs** — `Reporting (logs)`, `Not reporting (logs)` (on-chain active ∖
     shipping logs; was "Logs SHAME"). Symmetric with the Metrics row.
     `Reporting (logs)` is a **Loki**
     stat: `count(sum by (node) (count_over_time({job="genlayer-node"} | json |
     network="$network" [5m])))` (count distinct nodes shipping logs in 5m).
     Reporting(logs) usually EXCEEDS Reporting(metrics) — some nodes ship logs
     but not metrics (e.g. BlockPro), which is exactly why logs are joined by
     the `node`/`operator` address from the log JSON, never `validator_name`.
  4. **Versions** (scoped to the on-chain active set, so the three sum to it):
     `Version OK` (active ∩ latest `$latest_version`), `Version behind`
     (active ∩ reporting ∩ older), `Version unknown` (active ∖ reporting — no
     metrics so version can't be read; same set as `Not reporting (metrics)`).
  - **Roster status/Internal counts** = single **Infinity `jq-backend`** query on
    the `/grafana/` endpoint returning `[{"c": (… | length)}]`; `$network`
    **interpolates inside `root_selector`** (filter `select(.network=="$network")`),
    confirmed working. Reduce `lastNotNull` on field `c`.
  - **Roster dedupe (datasource-side, 2026-07-02)**: operators who re-register get
    a NEW validator wallet; the old one stays in the portal roster as `inactive`,
    so the raw roster held ~91 rows for ~39 Asimov accounts and the table showed
    "duplicate" validators. The roster query A (table + `Total` + `Inactive` stat)
    is now `jq-backend` with a `root_selector` that groups by
    `account → name → node` (first non-empty wins, prefixed `a:`/`n:`/`x:` to
    avoid key collisions) and per group keeps all non-`inactive` wallets, or the
    LAST wallet if the whole group is inactive (fully-gone operator = one row).
    `(add // [])` guards the empty-network case. An operator can still legitimately
    show twice (e.g. one `active` + one on-chain `quarantined` wallet — both live).
    The table's `rone` flag moved from `computed_columns` into the jq
    (`map(. + {rone: 1})`) because computed columns aren't reliable with
    `jq-backend`. Don't "fix" this by filtering `status` in a transformation —
    dedupe must happen before the `joinByField` merge.
  - **`Name` column — one merged display name (2026-07-03)**: the three old name
    columns (On-chain / Portal / Metrics name) are collapsed into a single `Name`,
    priority **portal account name > on-chain identity moniker > metrics
    `validator_name` > node address**. When the portal name wins it's tagged
    `" (portal)"` so you can see the source. Built in two layers: query A's jq
    computes `pref_name` = `account_name+" (portal)" // moniker` (null otherwise;
    portal-vs-identity resolved here); after the join a `calculateField` copies
    roster `name A` into `addr_last` (a computed field, which Grafana appends
    **last** in field order), then `Name` = `reduceRow firstNotNull` over
    `[pref_name A, validator_name, addr_last]`. **Why addr_last**: `reduceRow`
    `firstNotNull` picks the first non-null in *frame field order*, and ALL frame-A
    (roster) fields precede frame-B (`validator_name`) — so a roster fallback would
    always outrank the metrics name. Re-emitting the address as a trailing computed
    field forces the intended `pref_name > validator_name > address` order.
    `firstNotNull` **does work on string fields** (verified). The three source
    columns are `excludeByName`-hidden; `Name` is organize index 1.
    **Default sort = Health severity (2026-10-24, replaced the 2026-08-11 `Name`
    sort)**: the panel's `options.sortBy` is now EMPTY on purpose — the table's own
    sort runs last on the rendered frame and used to override the `severity`
    transform sort with `Name`. With it empty, the `sortBy` transform (`severity`
    desc) is the default order; clicking a header still sorts. `severity` now
    includes `hrank_s` = portal health rank × 1e14 (red 5 > orange 4 > yellow 3 >
    gray 2 > green 1 > absent 0), which dominates every older component
    (`mis_s` 1e13 …), so rows sort by Health first and by the old worst-first
    signals within a colour. The `sortBy` transform only takes ONE field, hence one
    combined number. Sorting by `Name` (header click) only behaves because of the
    trailing `convertFieldType` — see the reduceRow/NaN gotcha below; don't remove it.
  - **`Health` column (2026-10-24, `testnet/HEALTH-STATUS-PLAN.md`)**: the
    portal's unified verdict, displayed, never computed here. Query A's jq turns
    the roster's `health` object into `health_txt` = `"<color>|<label>"` (label
    falls back to the color; `-` when `health` is absent or not an object) and
    `hrank` (numeric rank above), then `del(.health)`. Overrides colour the cell
    with regex mappings `^red\|(.*)$` → red, text `$1` (same for orange / yellow /
    `gr[ae]y` → grey / green). Organize index 2 (right after `Name`). Until the
    portal deploys the field every row reads `-` and `hrank` is 0, so the old
    worst-first order is unchanged.
    **(2026-07-28, "null" Names regression + fix)**: the `validator_name` field
    in this chain is supplied by target **D** — the 2026-07-10 fix had trimmed D
    to `max by (node, version)`, silently dropping it, so every reporting node
    with no roster row rendered a literal `null` Name (Ivan's report, spotted on
    the public dashboard). D is now `max by (node, version, validator_name)(…)`
    — keep `validator_name` in the `by()` (safe: an aggregation can't hit the
    duplicate-series error, and no node carries two validator_names — verified;
    worst case a dup name adds a row, it doesn't blank columns). Additionally a
    trailing `node_last` computed field (reduceRow firstNotNull over `node`,
    created after `addr_last`, before `Name`) gives a **full-node-address last
    resort** for rows with neither roster row nor metrics (`addr_last` = roster
    minified address only covers roster rows). Name include is now
    `[pref_name A, validator_name, addr_last, node_last]`; `node_last` is
    excludeByName-hidden. Note the merge
    fully depends on the roster's raw `moniker` (points PR #881) for the identity
    tier — until that deploys, non-portal rows fall straight to `validator_name` or
    the address.
  - **`Identity` + `Linked` columns — verdicts computed IN GRAFANA from raw
    roster facts (2026-07-03, design decision)**: the roster endpoint ships raw
    fields only (`linked` bool — wallet attributed to a portal account, safe for
    non-visible operators; raw `moniker` / `logo_uri`; `has_description` bool —
    points PR #881); query A's jq computes the display tokens and `del()`s the
    raw fields so they never enter the join. `linked_txt`: `-` if `linked` is
    null (no wallet / backend not deployed), else `linked` / `NOT LINKED`.
    `identity`: `-` when all three raw fields are null, `OK` when moniker+logo+
    description are all set, else `missing: moniker, logo, description` (subset).
    Note `portal` linkage is NOT part of Identity — it has its own `Linked`
    column. After the join they're `identity A` / `linked_txt A`, renamed
    `Identity` / `Linked`, colored via mappings (green / grey `-` / regex
    `(missing:.*)` yellow / `NOT LINKED` yellow — both were orange/red until
    2026-10-24, aligned with the shared health rule table). Until PR #881 reaches production
    both columns show `-` everywhere by design. (An earlier backend-computed
    `identity_missing` field was scrapped — verdict logic belongs in Grafana.)
  - **GOTCHA — Infinity `columns` whitelist eats jq-added fields**: table target
    A declares an explicit `columns` list; any field the jq adds (`misone`,
    `linked_txt`, `pref_name`, …) must ALSO be appended there or the frame silently
    drops it (organize/reduceRow then no-op with no error — `Linked` column simply
    never appeared until `linked_txt` was whitelisted).
  - **Missing graduated validators (2026-07-03)**: the roster endpoint appends one
    synthetic `status='missing'` row per network for each graduated portal
    validator (visible Validator role user) with no wallet linked there (points
    PR #881; until it reaches production nothing changes — 0 missing rows). On
    those rows `node` = the **account address** (unique join key only; matches no
    metric/on-chain series) and `operator` is null. Dashboard wiring: query A's jq
    adds `misone` (1 iff `status=="missing"`); transformations build `misflag`
    (reduceRow with `zeroU`, null-safe) → `mis4` feeds `PartCode` (now
    `aflag + 2*qflag + 4*misflag`, mapping `4 → MISSING`, red) and `mis_s`
    (`misflag*1e13`, added to `severity` so missing sorts above metrics-shame).
    New `Missing` stat (id 26, roster count of `status=="missing"`, always-red
    like the SHAME stats); row-1 stats are all w3 now (Total shrank from w6).
    A wallet of ANY status (incl. inactive) suppresses the missing row; an
    unlinked wallet does NOT (portal can't attribute it), so an operator can
    legitimately show both an account-less real row and a MISSING row — that
    pair means "running but unlinked". Factory `getWalletsForOperator` stays the
    definitive absence check.
  - **Gotcha — `Value #<refId>` naming**: a stat that joins Infinity(E) + a
    **single** Prometheus target does NOT get the value column suffixed
    (`Value #F` won't exist → filter matches nothing → 0). Give the panel a
    **second** Prometheus target so the suffix appears. That's why `Version OK`
    carries a dummy `B` target alongside `F` even though only `F` is filtered.
  - Removed the old `Max blocks behind` and `Not in portal` stats.
  - **`Participating` column = ON-CHAIN, not portal.** The table's status column
    reads the chain, not the roster. Two Infinity RPC targets feed it: `E` =
    `selectableValidators()` (`0x2d2f135d`; was the retired `activeValidators()`
    `0xd2d49c4b` before Phase 2) and `Q` =
    `getAllQuarantinedValidators(0,100)` (`0x510a6f26`). On Phase 2 a quarantined
    validator is NOT in the selectable set (aflag=0, qflag=1 → `2`); under the old
    `activeValidators()` it was (→ `3`). Both map to `quarantined`, and
    **quarantine takes precedence** in the label. Since 2026-10-24 `Q` also emits
    `onchain_perm` (the `permanentlyBanned` word) → `pflag`, `p8 = 8*pflag` is added
    to `PartCode`, and `10`/`11` map to red **no longer participating**; `0`/null
    (not participating) is now **red** (was grey) per the rule table. Missing
    Metrics/Logs (`m1`/`m3`) are now gated on `live1 = max(onchain_active E,
    onchain_quarantined Q) - pflag` instead of `onchain_active E`, so quarantined
    nodes show OFF too (permanently quarantined ones don't), and OFF is yellow
    (was red). `universalone` also includes `onchain_quarantined Q` so a
    quarantined-only row gets a `zeroU`. The `Not reporting` STATS are unchanged
    (still on-chain active only). Encoded as `PartCode = aflag + 2*qflag` (aflag/qflag =
    reduceRow-sum of `onchain_active E` / `onchain_quarantined Q` with `zeroU`):
    `1 → active` (green), `2`/`3 → quarantined` (orange), `0`/null →
    `not participating` (grey, e.g. reporting-but-not-in-set spectators like
    `genlayerlabs-full-1`). The top `Quarantined` stat counts the same (filtered)
    `Q` set.
  - **Decoding `getAllQuarantinedValidators` (and `getAllBannedValidators`
    `0x6461cf56`)**: return is a dynamic array of `(address, uint256
    untilEpochBanned, bool permanentlyBanned)` — 3 words (192 hex) per element,
    vs `activeValidators()`' 1 word. jq-backend `root_selector` skips the
    offset+length header (`.[128:]`), strides **192** hex/element, and now reads
    **all three** words per element: address (word 0), `until_epoch` (word 1),
    `perm` (word 2). Body `data` = selector + 32-byte `startIndex=0` + 32-byte
    `size=100` (100 is ample for testnet; more needs pagination). NOTE: right now
    `getAllBannedValidators` returns the SAME set as quarantined (all current bans
    are temporary, `permanentlyBanned:false`), so banned is NOT wired separately —
    using it would double-count.
  - **EXPIRY FILTER — the raw quarantine list contains LAPSED entries; filter by
    epoch (2026-07-04, Ivan's "explorer says 3, dashboard says 4" report)**:
    `getAllQuarantinedValidators` returns entries whose `untilEpochBanned` may
    already be in the past. A quarantine is only *current* while
    `until_epoch > currentEpoch` (or `permanentlyBanned`); once it lapses the
    validator drops out of `activeValidators()` and the explorer stops showing it
    quarantined. Both the `Q` table target AND the `Quarantined` stat now decode
    `until_epoch` (via a jq `hexval` def — `ascii_downcase | ltrimstr("0") |
    explode | reduce …` 64-hex → int) and `select(.perm or (.until_epoch >
    $cur))`. **Since Phase 2 (2026-10-20) `$cur` is read ON-CHAIN**: both
    quarantine targets POST a batch `[{id:1, epoch() 0x900cf0cf}, {id:2,
    getAllQuarantinedValidators}]` and the jq takes the epoch from `.id==1`. The
    old hidden `$current_epoch` Prometheus var
    (`max(epoch_monitor_current_epoch{network="$network"})`) was deleted: the epoch
    monitor only ever reported Asimov, so on any other network the var was empty
    and the jq failed to parse. Verified: Bradbury had 4 raw / 3 live (one at
    `until_epoch=73` vs epoch 89, also absent from `activeValidators()`); Asimov
    unaffected (all `until_epoch=125` > epoch 124). Don't revert to counting the
    raw list — it over-reports quarantines for ~one epoch (~24h) after each lapse.
- `gl-validator-status-public` → `validator_status_public.json` — display title
  **"Testnet | Validator Status (Public)"**, the **PUBLIC** Wall-of-Shame
  variant (Grafana public dashboard, no login):
  `https://genlayerfoundation.grafana.net/public-dashboards/71f94ef49b8340cc8a6707aa00cd68d9`.
  The access token **survived the 2026-07-30 uid rename** (old uid
  `gl-wos-public`): Grafana's public-dashboards create API accepts an explicit
  `accessToken`, so the share was deleted on the old uid and recreated on the
  new one with the SAME token — the shared URL never changed. Same trick works
  for any future uid move.
  A self-contained, variable-free variant of `gl-validator-status` with one section
  (row) per network — since 2026-10-20 only **Bradbury Phase 2** (panel ids +200;
  it was Asimov +200 / Bradbury +400) — because
  **public dashboards do not interpolate template variables**: Prometheus exprs
  keep the literal `$network` and silently return EMPTY (no error), Infinity RPC
  bodies keep `${staking_addr}` and the jq errors; only Infinity `root_selector`
  gets interpolated (with the saved current value). Do NOT hand-edit it —
  **generated** from `validator_status.json` by
  `scripts/build_public_validator_status.py` (run from repo root, then upload
  `validator_status_public.json` as uid `gl-validator-status-public`, folder
  `fkpd6m`); rerun after any material Wall of Shame change. What the
  generator does (2026-07-28):
  - Hardcodes `$network` / `$staking_addr` per section (Bradbury Phase 2
    `bradbury-phase2` / `0xD8fB…7113`).
  - The quarantine targets already use the batch `[epoch(), getAllQuarantined…]`
    JSON-RPC call in the source board, so they copy through unchanged (the new
    Orbit RPC supports batch — verified 2026-10-20). Until Phase 2 the generator
    rewrote them itself, because the source used a `$current_epoch` var.
  - **Drops the Version OK/behind logic** (stats 30/31/32, table target F,
    `VersionCode` + related transforms/overrides) — it needs the
    `$latest_version` query var, which cannot exist publicly. The raw
    `Node Version` column stays. Removing F keeps the `Value #B/#C/#D` suffixes
    (multiple Prometheus targets remain, so Prometheus still suffixes all).
  - Rewrites the Legend once at top; sections are plain uncollapsed rows.
- `gl-network-status` → `network_status.json` — per-network fleet health
  (metrics-only).
- `gl-validator-profile` → `validator_profile.json` — per-validator drill-down;
  select by **`validator_name`** (primary), node derives from it; ⚠️ both vars come
  from `genlayer_node_info`, so the profile cannot select a validator that does not
  push metrics (true of every Phase 2 validator as of 2026-10-20); has an
  on-chain identity + validator-status (Wall-of-Shame) row + health + logs.
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

- **Networks**: the `network` label value is `bradbury-phase2` (documented — see the
  top section; NOT the portal key `bradbury2`). Sunset 2026-10-20:
  `asimov-phase5` / `bradbury-phase1`. Deprecated `exported_network` label is
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
- **Loki METRIC queries must carry `| __error__=""` right after `| json`
  (2026-07-28)**: one node shipping a malformed (non-JSON) log line makes Loki
  hard-error the ENTIRE metric query for that network (`pipeline error:
  'JSONParserErr'` — the error series reaches the aggregation), so Reporting
  (logs) / Not reporting (logs) / the table's Logs column all break at once. A Bradbury
  node triggered exactly this; all Loki metric exprs in `gl-validator-status`,
  `gl-validator-status-public`, and `gl-preclarke-status` now filter
  `__error__=""`. Any NEW
  Loki metric query needs the same filter. (Plain log-browsing queries are fine
  without it.)

## Live on-chain "participating" (Wall of Shame)

We read the consensus set **directly from the chain**, not from the portal cache.

- Infinity `url`/POST to RPC `https://rpc.testnet-chain.genlayer.com`, body:
  ```json
  {"jsonrpc":"2.0","id":1,"method":"eth_call","params":[{"to":"${staking_addr}","data":"0x2d2f135d"},"latest"]}
  ```
  (`0x2d2f135d` = `selectableValidators()` → `address[]`. Before 2026-10-20:
  `activeValidators()` `0xd2d49c4b` on the ZKsync RPC — retired, it reverts.)
- Parser MUST be **`jq-backend`** (plain `backend` treats `root_selector` as
  JSONata and fails). Tested decoder (skip offset+length words, chunk 64 hex,
  last 40 = address, drop the zero address to match the portal's own filtering):
  ```jq
  .result | ltrimstr("0x") | .[128:] | [range(0;(length/64)) as $i | .[$i*64:($i+1)*64]] | map(select(length==64) | {node:("0x"+(.[24:64]|ascii_downcase)), onchain_active:1}) | map(select(.node != "0x0000000000000000000000000000000000000000"))
  ```
- **Staking contract**: Bradbury Phase 2 `0xD8fBa96C0dBB0257028dBc0107060b958e5c7113`
  (sunset: Asimov `0x63Fa…687A`, Bradbury Phase 1 `0x4A44…21A5`). Per-network target
  via a hidden `staking_addr` template var: Prometheus
  `query_result(topk(1, count by (staking_address)(genlayer_node_info{network="$network"}) or label_replace(vector(0), "staking_address", "0xD8fB…7113", "", "")))`
  + regex `/staking_address="([^"]+)"/`. topk self-corrects a mislabeled node; the
  `or label_replace(vector(0), …)` arm is a **fallback default** (value 0, so any
  real reporting count wins) — without it the var is EMPTY while no node reports,
  and every RPC target fails with `Invalid params`. Verified both ways 2026-10-20.

## active vs reporting (DIFFERENT axes — expected to differ)

- **Active** = in the on-chain consensus set (`selectableValidators()` since
  Phase 2; `activeValidators()` before).
- **Reporting** = node pushing metrics to Grafana now.
- **Active ∖ Reporting** = the core SHAME (validating but no telemetry).
- **Reporting ∖ Active** = up but not in the set (low stake / infra full-node
  like `genlayerlabs-full-1`, or synced spectators like Nodes.Guru / Finoa).

## Wall of Shame — node version columns ("Node Version" + "Version")

Two columns flag nodes running an outdated release (added in dashboard v14+):

- **Node Version** — the node's actual running version string, from the
  `genlayer_node_info.version` label. Sourced from **query D**
  (`max by (node, version)(genlayer_node_info{…}) * 0 - 1`); the `version` field is
  un-hidden in the `organize` transform. `-` if not reporting. (Was query B's
  `group_left(version)` until 2026-07-10 — that vector-match erred out on a
  duplicate `validator_name`, see the "vector-match duplicate" gotcha below.)
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
- **A Prometheus vector-match (`* on(x) group_left(...)`) that hits a DUPLICATE
  series on the right ERRORS the WHOLE query → the target returns nothing → its
  columns silently vanish (2026-07-10).** The WoS `Blocks Behind` + `Node Version`
  columns were blank because target B was
  `genlayer_node_blocks_behind * on(validator_name) group_left(node,version) genlayer_node_info`
  and `[NODERS]` runs two scrape instances reporting the SAME `node`, so
  `on(validator_name)` found duplicate right-hand series and the query erred out for
  every node. Fix: `genlayer_node_blocks_behind` ALREADY carries a `node` label —
  read it directly, deduped: **B = `max by (node)(genlayer_node_blocks_behind{network="$network"})`**,
  and source the version string from **D = `max by (node, version, validator_name)(genlayer_node_info{…}) * 0 - 1`**
  (D was `max by(node)` — adding `version` gives the `Node Version` column its
  field without a second vector-match; `validator_name` re-added 2026-07-28, the
  Name merge needs it — see the null-Names note above). Never join genlayer metrics on
  `validator_name` — it is NOT unique (operators reuse it across nodes); join on
  `node`.
- **`Value #<refId>` column naming is NOT always suffixed — the FIRST value-bearing
  frame can stay bare `Value`.** Observed: with exactly two value frames
  (1 Prometheus + 1 Loki, as in `gl-preclarke-status`) the Prometheus value is bare
  **`Value`** and Loki is **`Value #L`**; with four (WoS B/C/D/F) they are all
  suffixed `Value #B/#C/#D/#F`. So verify per-panel: if a tri-state silently shows
  `-`/blank while the node reports, the calc is likely referencing the wrong value
  column name. `filterFieldsByName` matches `field.name` (often NOT the displayed
  `Value #X`, which is a displayName) — don't use it to probe; strip to
  `[formatString, joinByField]` and read the rendered headers, or bust the image
  renderer's aggressive cache with `theme=light`.
- Wall of Shame Metrics/Logs are **tri-state**: ON (reporting) / OFF (on-chain
  active but not reporting; displayed "SHAME" until 2026-07-31) / `-` (not
  active & not reporting → not expected).
- **`calculateField` output is always TYPED number — a reduceRow-built STRING
  column (e.g. the merged `Name`) sorts "randomly" until you re-type it
  (2026-07-10, Ivan's "can't order by name" report).** The values render fine,
  but the table's sort comparator picks numeric compare from the declared field
  type → every string is NaN → clicking the header shuffles arbitrarily. Fix:
  append a `convertFieldType` transform (`targetField: "Name"`,
  `destinationType: "string"`) — placed last, after `organize`, since organize
  doesn't rename `Name`. Any future reduceRow/calculateField string column needs
  the same re-type or its sort (and substring filtering) will misbehave.
- **`reduceRow firstNotNull` respects FRAME FIELD ORDER, not `include` order**, and
  all frame-A (Infinity) fields precede frame-B (Prometheus) which precede computed
  fields. To make a later-frame or fallback value rank *below* an earlier one, force
  order by re-emitting the loser as a trailing `calculateField` (Grafana appends
  computed fields last) — that's the `addr_last` trick behind the merged `Name`
  column. It DOES work on string fields.
- **MCP `update_dashboard` `operations` "add" at a numeric array index REPLACES that
  element, it does NOT insert-before** (RFC-6902 insert semantics are not honored).
  To insert mid-array, append with `/-` and reorder, or replace the whole array.
  (Learned the hard way clobbering the table's `organize` transform.)

## Reference docs in this repo

- `DASHBOARD-AUDIT.md` — full inventory of all ~42 dashboards + ownership + which
  are dead/duplicate.
- `FOUNDATION-DASHBOARDS-PLAN.md` — identity model, roster decision, dashboard plan.

## Alerts

- `grafana-alerts/*.json` — 9 rules synced from live Grafana; multi-network via
  the `network` label; routing labels `component`/`severity`/`threshold` (legacy
  `asimov-alert` label was dropped). **Label-agnostic** (re-checked 2026-10-20 for
  Phase 2): no expr filters on a `network` value, so a new label needs no change.

## Convention

Keep THIS file updated whenever a dashboard/query/convention/gotcha changes —
future sessions rely on it.
