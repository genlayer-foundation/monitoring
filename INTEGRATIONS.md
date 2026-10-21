# Integrations

How this repo talks to the outside world. Internal structure is not in scope (see ARCHITECTURE.md if present); which systems exist and who owns what data is cluster-level (see the parent CLAUDE.md).

This repo is mostly **declarative**: the integration surface lives in Grafana dashboard JSON (datasource bindings and Infinity HTTP/JSON-RPC targets) and alert-rule JSON, not in imperative code. A dashboard's Infinity target *is* an outbound HTTP call — it is executed by the Grafana Cloud backend (`parser: jq-backend`, so server-side), on every dashboard load/refresh, on behalf of whoever is viewing. Two small Python scripts are the only imperative code.

## Outbound — we call them

### Grafana Cloud stack (vendor — `genlayerfoundation.grafana.net`)
- **Direction**: read/write
- **Transport**: HTTP REST
- **Auth**: `GRAFANA_API_KEY` (Bearer), or the Grafana MCP server's service-account token held in local Claude config — neither is stored in this repo
- **Endpoint**: `${GRAFANA_URL}/api/v1/provisioning/alert-rules`, dashboard import via UI or the Grafana MCP server
- **Cadence**: on-demand, manual. **There is no CI** — no `.github/workflows`, no deploy script, no provisioning sidecar. The documented flow is: change the resource in Grafana → export JSON → commit it here (`README.md:226`). The repo is a mirror of live Grafana, not its source of truth.
- **We consume**: dashboard + alert-rule definitions on export; we write the same on import
- **Degrades**: nothing in this repo runs unattended, so an outage only blocks a human/agent edit round-trip. Committed JSON and live Grafana drift silently — nothing verifies they match.
- **Code**: `README.md:202` (API recipes), `CLAUDE.md:3` (the "always save back to JSON" rule), `CLAUDE.md:18` (MCP token location)

### Points portal — validator roster (`genlayer-foundation/points`)
- **Direction**: read
- **Transport**: HTTP REST (via the Grafana **Infinity** datasource `grafanacloud-infinity`)
- **Auth**: none (public endpoint, cached 60s upstream)
- **Endpoint**: `GET https://portal-admin.genlayer.foundation/api/v1/validators/wallets/grafana/?network=bradbury2` — filtered **server-side** by the portal network key `bradbury2` (Bradbury Phase 2; the portal's `asimov`/`bradbury` keys are retired and return `[]`). The key is hardcoded in the URL, not a variable: public dashboards don't interpolate Infinity URLs, and the portal key is not the Grafana `network` label. The jq no longer filters on `.network`. Verified 2026-10-20: prod returns 2 rows, both `inactive`
- **Cadence**: per dashboard load + auto-refresh — 1m (`validator_status`, `validator_status_public`, `index`), 30s (`validator_profile`)
- **We consume**: `network` (the portal key `bradbury2`, NOT the Grafana label — only displayed), `node` (lowercased validator address — the join key), `name`, `status`, `operator`, `account`, `account_name`, `explorer_url`, `linked`, `moniker`, `logo_uri`, `has_description`, plus synthetic `status:"missing"` rows
- **Degrades**: the Infinity target returns no frame; the `joinByField` outer join still emits the Prometheus/Loki side, so roster-derived columns (`Name`, `Identity`, `Linked`, `In Portal`) go blank and roster stat panels read 0/No data. No retry, no cache, no alert.
- **Consumed by 5 dashboards** (each declares its own copy of the target):
  - `dashboards/foundation/validator_status.json:127` (7 targets: table `A` + stats `Total`/`Internal`/`Portal: active`/`Inactive`/`Banned`/`Missing`)
  - `dashboards/foundation/validator_status_public.json:145` (7 targets — one network section)
  - `dashboards/foundation/validator_profile.json:176`
  - `dashboards/foundation/index.json:221` (validator directory table, `parser: backend`; its profile deep-link hardcodes `var-network=bradbury-phase2`)
  - `dashboards/foundation/validator_overview.json:213` (`Monitoring Overview` table `A`: one row per operator, `node` + name; replaced the dead explorer `/api/v1/validators` source on 2026-10-21 — no explorer serves Phase 2)

### GenLayer testnet chain — Bradbury Phase 2 (public RPC, Arbitrum Orbit / Conduit)
- **Direction**: read
- **Transport**: JSON-RPC over HTTP POST (Infinity datasource, `Content-Type: application/json`)
- **Auth**: none (public RPC)
- **Endpoint**: `https://rpc.testnet-chain.genlayer.com` (chainId 4221), method `eth_call` only, single and batch requests (batch verified 2026-10-20). Replaced `https://zksync-os-testnet-genlayer.zksync.dev` on 2026-10-20.
- **Cadence**: per dashboard load + auto-refresh (30s–1m)
- **We consume**: `selectableValidators()` (`0x2d2f135d` — replaced the retired `activeValidators()` `0xd2d49c4b`, which now reverts), `getAllQuarantinedValidators(0,100)` (`0x510a6f26`), `epoch()` (`0x900cf0cf`), all on the staking proxy; `getIdentity()` (`0x36afc6fa`) on the validator wallet. ABI decoding is done entirely in the target's jq `root_selector` — there is no ABI file and no chain SDK in this repo.
- **Degrades**: a jq decode error or RPC failure blanks the on-chain columns/stats for that panel. The `Participating` column falls to `not participating` (grey) rather than erroring. Known failure modes: an uninterpolated `${staking_addr}` produces `ltrimstr("0x") cannot be applied to: null`; an EMPTY `$staking_addr` produces RPC `Invalid params` — which is why the var now falls back to the Phase 2 staking proxy while no node reports (`CLAUDE.md`, "Live on-chain participating").
- **Code**: `dashboards/foundation/validator_status.json:171` (`selectableValidators`), `:543` and `:2507` (batch `[epoch(), getAllQuarantinedValidators()]` in one POST — the epoch feeds the lapsed-quarantine filter); `dashboards/foundation/network_status.json:97`; `dashboards/foundation/validator_profile.json:88` (`getIdentity` on `${node}`); `dashboards/foundation/validator_status_public.json:189` (`selectableValidators`) and `:561`/`:1959` (the same batch, staking address baked in)

### Explorer chain-indexer API (GenLayer internal explorer) — Pre-Clarke only
- **Direction**: read
- **Transport**: HTTP REST (Infinity datasource)
- **Auth**: none (public, no auth)
- **Endpoint**: `GET https://internal-explorer.genlayer.com/api/v1/validators?page_size=100`
- **Cadence**: per load + 1m refresh
- **We consume**: `total`, and per validator `validator_address`, `self_stake`, `delegated_stake`, `banned_until_epoch`, `is_active`, `is_primed_next_epoch`, `status`, `operator_address`, `owner_address`, `metadata.name`
- **Degrades**: the Pre-Clarke validator table and its Validators/Active/Primed stats go empty; the Prometheus/Loki stats still render (`or on() vector(0)`)
- **Why this and not the chain**: `activeValidators()` on the Pre-Clarke staking contract is **empty at epoch 0** (new validators are inactive until the next epoch boundary), so RPC would show nothing while the explorer lists 9. This dashboard is deliberately **portal-free** — Pre-Clarke has no portal roster at all.
- **Code**: `dashboards/foundation/preclarke_status.json:107`, `:181`, `:255`, `:836`

### Bradbury chain RPC — Pre-Clarke epoch (⚠ old ZKsync chain)
- **Direction**: read
- **Transport**: JSON-RPC over HTTP POST (Infinity datasource)
- **Auth**: none
- **Endpoint**: `https://rpc-bradbury.genlayer.com`, `eth_call` `epoch()` (`0x900cf0cf`) to the Pre-Clarke staking contract `0x500261a6b5F93Bc940Fb05624a3f1B9A3CE843e3`
- **Cadence**: per load + 1m refresh
- **We consume**: current epoch, hex-decoded via a jq `hexval` def
- **Degrades**: the Epoch stat shows No data; nothing else depends on it (unlike the Validator Status boards, Pre-Clarke does not use the epoch for quarantine expiry filtering)
- **⚠ Stale since 2026-10-20**: this host still answers but serves the OLD ZKsync chain (same head as `zksync-os-testnet-genlayer.zksync.dev`; Pre-Clarke `epoch()` = 139), and no telemetry carries `network="pre-clarke"`. Left unchanged pending a decision on whether Pre-Clarke is retired.
- **Code**: `dashboards/foundation/preclarke_status.json:455`

### Grafana Cloud Prometheus (`grafanacloud-prom`)
- **Direction**: read
- **Transport**: HTTP REST (PromQL, via the datasource binding — dashboards never address it by URL)
- **Auth**: handled by Grafana Cloud; no credential in this repo
- **Endpoint**: datasource uid `grafanacloud-prom` (the org default)
- **Cadence**: per dashboard load + refresh; per alert-rule evaluation
- **We consume**: `genlayer_node_info` (labels `node`, `validator_name`, `version`, `commit`, `genvm_version`, `staking_address`, `network`), `genlayer_node_blocks_behind`, `_synced`, `_latest_block`, `_synced_block`, `_cpu_usage_percent`, `_memory_percent`, `_disk_usage_percent`, `_genvm_permits_current`, `_genvm_executions`, `_transactions_activated_total`, `_uptime_seconds`, `up`, `go_memstats_alloc_bytes`. Dashboards select `network="bradbury-phase2"` — the documented label (`NETWORK_NAME`, docs.genlayer.com/validators/monitoring), not yet observed: as of 2026-10-20 no series carries it (`epoch_monitor_current_epoch` is no longer read; the epoch comes from the chain)
- **Degrades**: hard dependency for every alert rule and most panels — `noDataState: OK` on all 9 rules means a Prometheus outage **silently resolves** alerts rather than firing
- **Code**: `dashboards/foundation/validator_status.json:136`; every `grafana-alerts/alert-*.json` (`datasourceUid: grafanacloud-prom`), e.g. `grafana-alerts/alert-validator-down.json`

### Grafana Cloud Loki (`grafanacloud-logs`)
- **Direction**: read
- **Transport**: HTTP REST (LogQL, via the datasource binding)
- **Auth**: handled by Grafana Cloud; no credential in this repo
- **Endpoint**: datasource uid `grafanacloud-logs`
- **Cadence**: per dashboard load + refresh; per alert-rule evaluation
- **We consume**: `{job="genlayer-node"} | json | network=…` — the `node`/`operator` address and `level` fields; distinct-node counts for "Reporting (logs)"
- **Degrades**: **one node shipping a malformed non-JSON line hard-errors the entire metric query for that network** (`JSONParserErr`), taking out Reporting (logs), Not reporting (logs) and the table's Logs column at once. Mitigated by `| __error__=""` immediately after `| json` in every Loki *metric* query — any new one needs it too (`CLAUDE.md:383`).
- **Code**: `dashboards/foundation/validator_status.json:1012`; `grafana-alerts/alert-error-burst.json`, `grafana-alerts/alert-warning-burst.json`

### Grafana public-dashboard query API (`validator_telemetry_report.py`)
- **Direction**: read
- **Transport**: HTTP REST
- **Auth**: none at the HTTP layer — the public-dashboard **access token is the credential and it is hardcoded in the script** (see Security notes below; value deliberately not recorded here)
- **Endpoint**: `POST ${GRAFANA_URL}/api/public/dashboards/<token>/panels/{2,1}/query` — panel 2 = metrics (`now-15m`), panel 1 = logs (`now-1h`), against the "Who is pushing?" dashboard (uid `agfnnmw`, `dashboards/whoispushing.json`)
- **Cadence**: on-demand, manual CLI run; no scheduler anywhere in this repo
- **We consume**: `validator_name` labels off the returned frame schemas
- **Degrades**: each panel query is individually wrapped — a failure prints `Warning: Failed to query …` and continues with an empty list, so the report silently under-reports telemetry rather than failing
- **Code**: `validator_telemetry_report.py:215 (query_public_dashboard_panel)`, `validator_telemetry_report.py:42`

### Caldera GenLayer testnet RPC (`validator_telemetry_report.py`)
- **Direction**: read
- **Transport**: JSON-RPC over HTTP POST
- **Auth**: none
- **Endpoint**: `${RPC_URL}`, default `https://genlayer-testnet.rpc.caldera.xyz/http`, method `eth_call`, 30s timeout
- **Cadence**: on-demand, manual CLI run
- **We consume**: `getValidatorsAtCurrentEpoch()` (`0x16e7d513`) and `getAllBannedValidators()` (`0x1972f9ce`) on staking `0x10eCB157734c8152f1d84D00040c8AA46052CB27`; `getWalletsForOperator(address)` (`0xf31fa988`) on factory `0x2e198119E639D1063180f281617f64Dd788D78d2`; `getIdentity()` (`0x36afc6fa`) per wallet
- **Degrades**: `eth_call` raises on RPC error and the exception propagates out of `get_onchain_validators` — the script aborts. The per-validator moniker lookups swallow all exceptions and return `None`.
- **⚠ Stale**: this endpoint, both contract addresses and both selectors are **from an older testnet deployment** and match nothing else in this repo — the dashboards use the Phase 2 Orbit RPC, a different staking address, and `selectableValidators()`/`getAllQuarantinedValidators()`. Treat this script as legacy/unverified until re-pointed.
- **Code**: `validator_telemetry_report.py:53 (eth_call)`, `validator_telemetry_report.py:35-49`

### 5ElementsNodes validator feeds (third-party operator — reference dashboards only)
- **Direction**: read
- **Transport**: HTTP REST (Infinity datasource)
- **Auth**: none
- **Endpoint**: `GET https://asimov.5elementsnodes.com/genlayer/validators.json`, `GET https://bradbury.5elementsnodes.com/genlayer/validators-bradbury.json`
- **Cadence**: per dashboard load
- **We consume**: 5Elements' own validator name/address mapping
- **Degrades**: unknown — these are 5Elements-authored boards vendored here as reference (`CLAUDE.md:27`), not maintained by the Foundation
- **Code**: `dashboards/5ElementsNodes/Chain Metrics | Smart Contract | Asimov.json:258`, `dashboards/5ElementsNodes/WOS | Internal.json:878` (a `CollectionLookup` template var switching feed by `$network`)
- **⚠ Stale since 2026-10-20 (left unchanged — third-party)**: both Chain Metrics boards POST to the sunset ZKsync RPC `https://zksync-os-testnet-genlayer.zksync.dev/` against the old Asimov/Bradbury Phase 1 staking addresses; `WOS | Internal` switches on `asimov-phase5`/`bradbury-phase1` and the asimov/bradbury 5elements feeds. None of them knows Bradbury Phase 2. `Validator Ops Radar` is label-agnostic and unaffected.

### Google Cloud Storage — node release bucket (5Elements dashboard only)
- **Direction**: read
- **Transport**: HTTP REST (Infinity datasource)
- **Auth**: none (public bucket listing)
- **Endpoint**: `GET https://storage.googleapis.com/storage/v1/b/gh-af/o?prefix=genlayer-node/bin/amd64&maxResults=1000`
- **Cadence**: per dashboard load
- **We consume**: object names, to derive the latest published `genlayer-node` release tag
- **Degrades**: unknown (third-party board). Note the Foundation dashboards deliberately do **not** do this — their "latest version" is the max version seen in the fleet via the `$latest_version` Prometheus variable (`CLAUDE.md:436`).
- **Code**: `dashboards/5ElementsNodes/WOS | Internal.json:800`, `dashboards/foundation/validator_overview.json:638` (`$allowed_versions_regex` — this Foundation board does derive versions from the bucket)

### Grafana `/api/ds/query` — self-call (5Elements dashboard only)
- **Direction**: read
- **Transport**: HTTP REST
- **Auth**: `Authorization` header whose value is the literal placeholder `<APIKEY>` — **not a working credential in the committed JSON**; the live board must carry a real one
- **Endpoint**: `POST https://genlayerfoundation.grafana.net/api/ds/query`, wrapping a PromQL query against `grafanacloud-prom`
- **Cadence**: per dashboard load
- **We consume**: `max by(validator_name, node)(genlayer_node_info{…})`
- **Degrades**: as committed, this target cannot authenticate — it returns 401 and the panel is empty
- **Code**: `dashboards/5ElementsNodes/WOS | Internal.json:131` (headers at `:138`)

## Inbound — they call us

This repo exposes **no server and no endpoint of its own**. Everything below consumes artifacts this repo produces, served by Grafana or read out of git.

### Validators and the public (via Grafana public dashboards)
- **Transport**: HTTP REST (Grafana-hosted public dashboard, no login)
- **Auth**: unauthenticated share link gated by a `public-dashboards` access token (token URLs are recorded in `CLAUDE.md`, not repeated here)
- **Endpoint we expose**: `https://genlayerfoundation.grafana.net/public-dashboards/<token>` for uid `gl-validator-status-public` (Bradbury Phase 2) and uid `gl-preclarke-status` (Pre-Clarke)
- **They consume**: per-validator reconciliation of on-chain participation vs metrics/logs reporting, node version, blocks behind
- **Note**: the share **token survived the 2026-07-30 uid rename** (`gl-wos-public` → `gl-validator-status-public`) — Grafana's public-dashboards create API accepts an explicit `accessToken`, so the share was deleted on the old uid and recreated on the new one with the same token; the public URL never changed
- **Code**: `dashboards/foundation/validator_status_public.json:2605` (uid), `dashboards/foundation/preclarke_status.json:1243` (uid), `CLAUDE.md:287`, `CLAUDE.md:49`

### Grafana Alerting → contact point (Slack)
- **Transport**: webhook (Grafana-managed Alertmanager → Slack)
- **Auth**: held in Grafana; no credential in this repo
- **Endpoint we expose**: n/a — we emit alert instances carrying labels `component`, `severity`, `threshold` (+ `network` from the query), plus `summary`/`description` annotations that deep-link `https://genlayerfoundation.grafana.net/d/validator-overview/validator-overview?var-validator_name=…`
- **They consume**: the 9 rules in `grafana-alerts/`, all in folder `dfa1v9yck3ny8b` (**GenLayer Labs**, not the Foundation folder), rule groups `Validator Memory Alerts`, `Node Sync Alerts`, `Node Performance Alerts`, `Log Analysis Alerts`
- **⚠ Routing is not in this repo**: none of the 9 rule files has a `notification_settings` block, so each is routed by the **live notification policy**, which is not exported here. `README.md:106` documents a matcher `asimov-alert = true` → contact point **GenLayerLabs Slack** (`af9yk9dbw5af4f`) — but that label was **dropped from every rule** (`CLAUDE.md:522`), so the documented matcher can no longer match anything. The actual current routing for `component`/`severity`/`threshold` is **unknown from this repo** and must be read from live Grafana.
- **Pending durations** (`for`): 5m memory/blocks-behind, 2m log bursts, 1m genvm-permits and validator-down, 0s validator-restart. All rules set `noDataState: OK` and are `isPaused: false`. Evaluation interval is a rule-group property and is **not stored in these files**.
- **Code**: `grafana-alerts/alert-1gb-memory-threshold.json`, `grafana-alerts/README.md`, `README.md:106`

### `testnet` management repo (parent, `genlayer-foundation/testnet`)
- **Transport**: git submodule pointer
- **Auth**: git over HTTPS to `github.com/genlayer-foundation/monitoring`
- **They consume**: this repo's `CLAUDE.md` as the authoritative Grafana/dashboard reference, and the dashboard/alert JSON
- **Code**: parent `/Users/rasca/Dev/genlayer/testnet/.gitmodules`, parent `CLAUDE.md`

### Report files (humans / outreach)
- **Transport**: local files, not a network surface
- **Endpoint we expose**: `validator-telemetry-report.json` and `.md` written to the CWD (`--output`, `--format json|markdown|both`); both are gitignored in practice (untracked)
- **They consume**: per-validator telemetry buckets (fully configured / metrics-only / logs-only / none) plus adoption-rate percentages, used for validator outreach
- **Code**: `validator_telemetry_report.py:472 (main)`, `validator_telemetry_report.py:399 (generate_markdown)`

## On-chain

- **Networks**:
  - **Bradbury Phase 2** (`network` label `bradbury-phase2`, per docs.genlayer.com/validators/monitoring, not yet observed; portal key `bradbury2`) — staking proxy `0xD8fBa96C0dBB0257028dBc0107060b958e5c7113`, via `https://rpc.testnet-chain.genlayer.com` (chainId 4221, Arbitrum Orbit / Conduit)
  - Sunset 2026-10-20, no longer queried: Asimov (`asimov-phase5`, staking `0x63Fa5E0bb10fb6fA98F44726C5518223F767687A`) and Bradbury Phase 1 (`bradbury-phase1`, staking `0x4A4449E617F8D10FDeD0b461CadEf83939E821A5`), both on `https://zksync-os-testnet-genlayer.zksync.dev`
  - **Pre-Clarke** (`pre-clarke`) — separate consensus deployment on the Bradbury chain (chainId 4221), staking `0x500261a6b5F93Bc940Fb05624a3f1B9A3CE843e3`, RPC `https://rpc-bradbury.genlayer.com`
  - Legacy, in the report script only: chainId 4221 via Caldera, staking `0x10eCB157734c8152f1d84D00040c8AA46052CB27`, factory `0x2e198119E639D1063180f281617f64Dd788D78d2`
- **Access**: **read-only**. Only `eth_call`; no transaction is ever signed and no signing key or mnemonic exists or is expected in this repo.
- **Address source of truth**: upstream `genlayer-consensus` `deployments/bradbury-phase-2.json`; none as a file here. The staking address is resolved **at runtime** from telemetry — hidden Prometheus template var `$staking_addr` = `query_result(topk(1, count by (staking_address)(genlayer_node_info{network="$network"}) or label_replace(vector(0), "staking_address", "<Phase 2 staking>", "", "")))` with regex `/staking_address="([^"]+)"/` — and falls back to the Phase 2 literal while no node reports. It appears as a literal in that fallback (`validator_status.json`, `network_status.json`), the generated public dashboard and the generator's `NETWORKS` table.
- **SDK**: none. No `web3`, `viem`, `ethers` or `genlayer-js` anywhere — raw JSON-RPC, with ABI decoding done in jq inside Infinity `root_selector` expressions (dashboards) or hand-rolled hex slicing in Python (`decode_address_array`).
- **Code**: `scripts/build_public_validator_status.py:27 (NETWORKS)`, `dashboards/foundation/validator_status.json:171`, `CLAUDE.md:406`, `validator_telemetry_report.py:74 (decode_address_array)`

## Environment variables

The repo has **no `.env.example`**; `.env` is gitignored (`.gitignore:1`) and no code loads one. Only two variables are read at runtime, both by the report script; the third is documented for manual `curl` use only.

| Var | Used for | Required | Default |
|---|---|---|---|
| `GRAFANA_URL` | Grafana base URL for the public-dashboard query API | no | `https://genlayerfoundation.grafana.net` (`validator_telemetry_report.py:36`) |
| `RPC_URL` | Chain RPC for the report script's `eth_call`s | no | `https://genlayer-testnet.rpc.caldera.xyz/http` (`validator_telemetry_report.py:35`) |
| `GRAFANA_API_KEY` | Bearer token for the Grafana provisioning API — **documented in `README.md:204` only, never read by any code here** | no | — |

Dashboard-side credentials (Prometheus/Loki/Infinity datasource auth, the Grafana MCP service-account token, Slack contact-point webhook) all live in Grafana Cloud or local Claude config, never in this repo (`CLAUDE.md:18`).

## Not integrated

- **No CI/CD.** No `.github/`, no workflow, no Makefile, no deploy script. Dashboards and alerts are pushed to Grafana **by hand** (UI import, the Grafana MCP server, or `curl` against the provisioning API). Nothing in this repo verifies that committed JSON matches live Grafana.
- **No scheduler.** No cron, no systemd timer, no Celery/APScheduler. `validator_telemetry_report.py` and `scripts/build_public_validator_status.py` are both manual one-shot CLI runs. All "cadence" in this file is Grafana's own dashboard refresh or alert evaluation.
- **No server, no database, no queue, no object store.** This repo stores JSON and two scripts; it exposes no port and owns no schema.
- **No chain writes and no signing key** — read-only `eth_call` everywhere.
- **No PagerDuty / Opsgenie / email**; Slack is the only documented alert channel — and the routing that binds rules to it is **not** in this repo (see the Grafana Alerting entry).
- **No direct scraping of validator nodes.** This repo never talks to a node's `:9153/health` or `:9151` RPC — node telemetry arrives only through Grafana Cloud Prometheus/Loki, which the nodes push to themselves.
- **`gl-preclarke-status` deliberately does NOT call the portal.** Pre-Clarke has no roster; its validator list comes from the explorer indexer API, and `activeValidators()` would return empty at epoch 0.
- **`gl-network-status` does not call the portal either** — it is Prometheus + on-chain `selectableValidators()` only. The portal roster is used by exactly four dashboards: `index`, `validator_profile`, `validator_status`, `validator_status_public`.
- **`dashboards/5ElementsNodes/*` are third-party reference boards**, vendored for reference and not maintained by the Foundation; their integrations (5elementsnodes.com feeds, the GCS bucket, the `/api/ds/query` self-call) are documented above but are not Foundation-owned surface. They are stored in Grafana's `dashboard.grafana.app/v2beta1` resource envelope, unlike the Foundation boards which are unwrapped dashboard models.
- **`dashboards/grafana_metrics.json` is a stock Grafana Cloud board** bound to `grafanacloud-ml-metrics`; it monitors Grafana itself and carries no GenLayer integration.

## Security notes (not integrations)

- `validator_telemetry_report.py:42` contains a **hardcoded Grafana public-dashboard access token** as a literal. It is a capability URL credential for the "Who is pushing?" board (uid `agfnnmw`) — anyone with the file can query that dashboard's panels. Rotate via Grafana's public-dashboards API and move to an env var if this script is revived.
- `dashboards/5ElementsNodes/WOS | Internal.json:139` carries an `Authorization` header with the placeholder value `<APIKEY>` — harmless as committed, but a reminder that re-exporting that board from live Grafana may capture a real key. Check before committing any 5Elements re-export.

<!-- scanned: e16a614 2026-08-12; Bradbury Phase 2 cut-over 2026-10-20 -->
