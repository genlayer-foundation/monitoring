# GenLayer Grafana — Dashboard Audit (2026-06-30)

Live audit of all 42 dashboards in `genlayerfoundation.grafana.net`. Each dashboard's
data was queried live. Networks today: **`asimov-phase5`** (33 nodes, epoch 120),
**`bradbury-phase1`** (~29 nodes, epoch 85).

Canonical conventions used by the *good* dashboards:
- Metric namespace `genlayer_node_*`; per-testnet selector is the **`network`** label
  (values `asimov-phase5` / `bradbury-phase1`). The deprecated `exported_network` label
  is broken — avoid it.
- Node version/identity from `genlayer_node_info`.
- Logs in Loki `{job="genlayer-node"}` with a `network` label.

## Ownership map

| Owner / editor handle | Folder(s) | Ours? |
|---|---|---|
| **5Elements Nodes** (`d5en12eb`) | 5ElementsNodes, Asimov, Bradbury | No — 3rd-party operator |
| **Darien** (`darien-mcp`/`darien5`) | GenLayer Labs, Heartbeat | No — GenLayer Labs ops |
| **Agustin** (`agustin-cli`) | "Who is pushing?" | No — per your note |
| **Albert** (`albertdd03`) | GenLayer Foundation | **Yes — Foundation** |
| **Federico** (`federicoaa6f`) | General Monitor, fede/* | Ours (scratch/basic) |
| **Anonymous / service-acct** | root, GrafanaCloud, IRM | Mixed (built-ins + orphans) |

---

## Bucket 1 — NOT ours (leave alone)

### 5Elements Nodes (`d5en12eb`)
| Dashboard | uid | Panels | Data | Purpose |
|---|---|---|---|---|
| WOS \| Internal | `incsb8s` | 3 | live | **Master "wall of shame"** — `$network`-templated, dynamic version-allow-list from the GCS release bucket, per-network roster via `CollectionLookup`. v69, best-engineered. |
| Shared WOS \| Asimov | `shincsb8s` | 3 | live (33) | Published Asimov derivative of Internal; network pinned, version list hardcoded. |
| Shared WOS \| Bradbury | `shdectd47` | 3 | live (29) | Same for Bradbury (`network="bradbury-phase1"`). |
| Chain Metrics \| Asimov | `debmglh` | 13 | live (ep 120) | On-chain epoch/validator-set/slashing via Infinity `eth_call` to consensus contract `0x63Fa…687A`. |
| Chain Metrics \| Bradbury | `dezbt57` | 11 | live (ep 85) | Same, contract `0x4A44…21A5`. |
| Validator Ops Radar \| Errors & Warnings | `innbs44` | 7 | live (667 err/1h) | Loki error/warn triage — piecharts + top signatures + drilldown. |
| LLM \| Internal | `llmsb8s` | 3 | live (159k/1h) | LLM/GenVM error analysis from node logs, `$network`-templated. |

### GenLayer Labs / Darien
| Dashboard | uid | Panels | Data | Purpose |
|---|---|---|---|---|
| Validator Overview | `validator-overview` | 49 | live | **Definitive per-validator deep-dive** — sync, tx lifecycle, transact-manager, GenVM, resources, logs. `network_filter` templated. |
| Validator Fleet Overview | `validator-fleet-overview` | 1 | live | Fleet roll-up table (one row/validator) — companion to above. |
| RPC Provider Health | `857c3522…` | 35 | live (152 rps) | RPC-provider SLA (availability/latency/errors/WS) with `fault` dimension; 99.75% SLO. Most actively maintained. |
| Alert Health | `alert-health` | 4 | **partial** | Grafana alerting health. The 2 Prometheus panels are **dead** (`grafana_alerting_*` not in `grafanacloud-prom`); the alert-rule-status table works. |
| Heartbeat Monitor | `heartbeat-monitor` | 19 | live | Deploy/write heartbeat cycle vs contracts (success rate, TPS, latency). |
| Balance Monitor | `balance-monitor` | 6 | live (24 wallets) | Operator/validator wallet balances w/ warn/crit thresholds. |
| Epoch Monitor | `epoch-monitor` | 22 | live (ep 120/85) | Epoch lifecycle + validator population (joined/active/banned/quarantined). Most-iterated (v54). |
| Heartbeat — Service | `heartbeat-service` | 26 | live | Node.js runtime health of the heartbeat service. |
| Balance Monitor — Service | `balance-monitor-service` | 21 | live | Runtime health of balance-monitor service. |
| Ban Monitor — Service | `ban-monitor-service` | 21 | live | Runtime health of ban-monitor (no domain twin exists). |
| Epoch Monitor — Service | `epoch-monitor-service` | 28 | live | **Canonical** Epoch service board (v11, real edits). |

### Agustin / Federico (small, not testnet-status)
- **Who is pushing?** `agfnnmw` (2p, live, 54 up) — telemetry-coverage check (metrics vs logs per validator). Agustin's. *(Tracked in our repo as `whoispushing.json`.)*

---

## Bucket 2 — OURS / Foundation (the set to curate)

| Dashboard | uid | Panels | Data | Verdict |
|---|---|---|---|---|
| **GenLayer Foundation \| Validator Overview** | `genlayer-foundation-overview-v4` | 2 | live (33/29) | **Keep.** Albert's. Compliance view: who's reporting (ON/SHAME) + node versions, `$network` selectable. Small but purposeful. |
| **General Monitor** | `f2b2564c…` | 4 | live | Basic node time-series (genvm exec, leader-proposed, blocks-behind, uptime). Network-agnostic. Useful complement, not a status board. *(repo `general_monitor.json`)* |
| **GenLayer Validator Fleet Overview** | `genlayer-fleet-overview` | 8 | **broken grouping** | **Retire/rebuild.** Anonymous, root, never edited since 2026-04-09. Duplicates the Labs fleet table but uses the deprecated `exported_network` label → by-network panels collapse. |
| **Asimov Wall of Shame** | `asimov-wall-of-shame` | 1 | **dead** | **Throwaway stub.** Points at non-existent datasource `grafanacloud-genlayerfoundation-prom`; renders nothing. Schema 38 (oldest). Rebuild, don't extend. *(repo `asimov_wall_of_shame.json`)* |
| Grafana metrics | `isFoa0z7k` | 11 | n/a | Grafana self-monitoring built-in. Tracked in repo (`grafana_metrics.json`) but not GenLayer content. |
| fede/* (`logs`, `New dashboard`, `Synced`) | — | 1–3 | mixed | **Personal scratch.** `New dashboard` is dead; `Synced` has reusable node sync/height signal. Not authoritative. |

---

## Duplicates & dead dashboards (cleanup targets)

- **3× "Epoch Monitor — Service"** → keep `epoch-monitor-service` (v11, real edits); `55128aaa…` and `738e30b3…` are Anonymous v1 import clones. *(Darien's folder — coordinate before deleting.)*
- **Two fleet overviews** → `validator-fleet-overview` (Labs, good) vs `genlayer-fleet-overview` (ours, broken label). Ours is the dup to retire.
- **Dead data:** `asimov-wall-of-shame` (bad datasource), `fede/New dashboard` (no data), `alert-health` Prometheus panels.

---

## Wall of Shame / testnet-status — the path forward

**The four "WOS" dashboards are one design in four forms**, all 5Elements:
`WOS | Internal` (master, both networks, dynamic version detection) → `Shared WOS | Asimov` + `Shared WOS | Bradbury` (pinned, published copies). Our `asimov-wall-of-shame` only shares the *name* — it's a broken stub.

**Recommendation for a Foundation-owned Asimov + Bradbury status dashboard:**
1. **Model it on `WOS | Internal` (`incsb8s`)** — it already solves both-networks-in-one (`$network`), automatic "is this node on an acceptable version" from the real release bucket, and per-network rosters.
2. **Re-point external deps to Foundation-owned sources.** The WOS boards depend on the **Infinity datasource** and **5Elements-hosted** `validators.json` (`asimov.5elementsnodes.com`, `bradbury.5elementsnodes.com`). A Foundation rebuild must use our own roster endpoint.
3. **Borrow the chain-status pattern** from `debmglh`/`dezbt57` (Infinity `eth_call` + `jq` against the consensus contracts) for live epoch/validator-set/slashing.
4. **Add node-health time-series** (`up`, `genlayer_node_latest_block`, `genlayer_node_synced`, `genlayer_node_blocks_behind`) — the WOS tables lack trend panels; `Synced` and `General Monitor` show the shape.
5. **Treat `asimov-wall-of-shame` as throwaway** — at minimum fix its datasource to `grafanacloud-prom`, but better to rebuild fresh.
