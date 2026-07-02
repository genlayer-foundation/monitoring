# Foundation Dashboards — Plan & Data Model (rev. 2026-06-30)

Goal: a Foundation-owned set of Grafana dashboards for Testnet **Asimov** and **Bradbury**,
all under the **GenLayer Foundation** folder, leaving Darien's GenLayer Labs / Heartbeat
folders untouched (we may *copy* from them, not move).

> **Major update:** the roster/identity data source is **already built and public** in the
> `points` repo (`genlayer-foundation/points`, branch `dev`, app `backend/validators`). We do
> **not** need the 5Elements `validators.json` or the leaderboard endpoint for the roster.

## Identity model (validated against code + live data)

A validator has **three distinct addresses** — the points `validators` app models them precisely:

| Concept | points model field | Roster endpoint field | Metric label | Example |
|---|---|---|---|---|
| **validator / node address** | `ValidatorWallet.address` | `address` | **`genlayer_node_info.node`** ← JOIN KEY | `0x5473…d9b9` |
| **operator wallet** (runs the node) | `ValidatorWallet.operator_address` | `operator_address` | — | `0x4d92…f006` |
| **account / owner** (portal login) | `User.address` (1:1 `Validator`) | `operator_user.address` | — | `0x0768…99ca` |

- The on-chain sync (`validators/genlayer_validators_service.py`) reads the **Staking contract's
  `activeValidators()`** per network → each is a `ValidatorWallet.address`. For each it calls
  `operator()` (→ `operator_address`), `getIdentity()` (→ `moniker`, `logo_uri`, `website`,
  `description`), and `validatorView()` (→ stake, status). The wallet is linked to a portal
  `User`/`Validator` by matching `operator_address` ↔ `User.address`.
- The Grafana Wall-of-Shame sync (`validators/grafana_service.py`) confirms the join:
  it matches the Prometheus **`node`** label (lowercased) to `ValidatorWallet.address`.

### Answers to the open questions
1. **What does a node push?** The `genlayer_node_info` metric labels: `node` (validator/wallet
   address — the reliable key), `validator_name` (operator-set display string, inconsistent —
   not a key), `network`, `staking_address` (consensus contract), `version`, `commit`,
   `genvm_version`, `protocol_version`, `rpc_url`, `instance`, `job`, `address_manager`; plus the
   `genlayer_node_*` time-series. The node's **identity (moniker/logo/website) is NOT in
   Prometheus** — it is set **on-chain** via `getIdentity()` and surfaced by the portal roster.
2. **Is a node the operator or the validator address?** The node pushes its **validator (wallet)
   address** in the `node` label (= `ValidatorWallet.address`). The **operator** is a separate
   wallet (`operator_address`); the **account/owner** is a third (`operator_user.address`).
3. **Do they push the network correctly?** `network` is **self-reported by the node** (operator
   config) — usually right but **not authoritative**: at least one node reports
   `network="bradbury-phase1"` while carrying the Asimov `staking_address` (`0x63Fa…687A`).
   The **authoritative** network membership is on-chain (which staking contract lists the
   validator), which the portal roster already reflects. → Trust the **roster** for who/where;
   use **metrics** only for "is it reporting / what version / how healthy."

Live cross-check (Asimov, 2026-06-30): roster 52, reporting metrics 33 (all join by node
address, 0 orphans), 19 registered-but-silent = the Wall of Shame.

## Roster source — RESOLVED (dedicated Grafana endpoint)

A **purpose-built minimal endpoint** was added to `points` (PR
[#855](https://github.com/genlayer-foundation/points/pull/855), branch
`feature/grafana-validators-endpoint` → `dev`) so dashboards do NOT depend on the in-flux
Wall-of-Shame endpoint:

**`GET https://portal-admin.genlayer.foundation/api/v1/validators/wallets/grafana/?network=asimov|bradbury`**
— public, cached 60s. Flat array, one row per validator wallet, all statuses, no shame fields:

```jsonc
{ "network": "asimov-phase5",   // Grafana label value — exact join
  "node":    "0x…",             // on-chain validator address == genlayer_node_info `node` (lowercased)
  "name":    "AURORAX",         // moniker → visible account name → short addr
  "status":  "active",          // active|quarantined|banned|inactive
  "operator":"0x…",             // per-network operator wallet
  "account": "0x…",             // stable cross-network identity; null if operator not visible
  "account_name": "AuroraX",
  "explorer_url": "https://…" }
```

**Operator address is per-network** (12/14 multi-network operators differ across testnets), and
node addresses are per-network too — so the dashboards group an operator across Asimov+Bradbury
by **`account`**, not by operator/node address.

> The richer `wall-of-shame` endpoint still exists if we ever want the portal's own
> metrics/logs status. Reference shape (`{ network, last_grafana_check_at, stats, wallets[],
> validators[] }`), each `wallets[]` row:

```jsonc
{
  "address": "0xf8ca…6574",          // validator/node address  → JOIN KEY (metric `node`)
  "network": "asimov",                // short code; metric label is "asimov-phase5" (map in dashboard)
  "status": "active",                 // on-chain: active/quarantined/banned/inactive
  "moniker": "AURORAX",               // on-chain getIdentity() — node-operator-set
  "logo_uri": "http://…/logo.png",    // on-chain getIdentity()
  "operator_address": "0xfc39…ac77",
  "operator_user": { "name": "AuroraX", "address": "0x0c84…e232",
                     "profile_image_url": "https://…", "visible": true },
  "explorer_url": "https://explorer-asimov.genlayer.com/",
  "metrics_status": "on|shame", "logs_status": "on|shame",
  "last_grafana_check_at": "…", "metrics_shame_started_at": "…",
  "logs_shame_started_at": "…", "version_shame_started_at": "…"
}
```

This already provides everything the dashboards need: node address (join key), network, on-chain
status, node-set identity (moniker/logo), operator + account identity (name/avatar), explorer
link. The running **version** comes from the metric itself (`genlayer_node_info.version`), so it
need not be in the roster. **No leaderboard or 5Elements dependency required.**

### Architectural note
The portal **already computes a Wall of Shame server-side** by querying our Grafana
(`grafana_service.py`, 5-min cron). So data flows portal → Grafana today. Our Grafana dashboards
will go the other way: **Grafana Infinity → portal roster endpoint**, joined to Prometheus by
node address. Both can coexist (portal = canonical store/API; Grafana = operator-facing viz).

## Does this need a PR to `points`? (assessment)

The endpoint is **sufficient for v1 as-is** — recommend building dashboards against it first.
Candidate PR enhancements only if friction shows up (target branch `dev`):
- Add the **Grafana network label** value (`asimov-phase5`) alongside the short `network` code,
  to make the Infinity↔Prometheus join label-exact (avoids per-dashboard mapping).
- Optionally expose the **running node version per wallet** (the sync already knows it) so the
  roster is self-contained for version-compliance without a metric join.
- Optionally a neutral alias (e.g. `/validators/wallets/roster/`) and/or `?network=all` to fetch
  both testnets in one call for the index.
- These are conveniences, not blockers. Decide after the first dashboard is wired.

## Folder & ownership target
- **GenLayer Foundation** folder (`fkpd6m`) = home for everything we build.
- Leave **GenLayer Labs** (`dfa1v9yck3ny8b`) and **Heartbeat** (`heartbeat`) as-is (Darien);
  copy (not move) anything we want to build on.
- 5Elements + Albert/Federico/Foundation dashboards are ours.
- Retire the broken root orphans (`asimov-wall-of-shame` stub, `genlayer-fleet-overview`).

## Dashboards to build (all in Foundation folder)
1. **Index / landing** — "GenLayer Testnets". Validator directory (name, network, status,
   version, reporting?) from the roster endpoint, with data-links deep-linking into each
   Profile, plus links to every other dashboard.
2. **Wall of Shame** — `$network`-templated; roster (portal endpoint) LEFT-JOIN metrics by node
   address → shame = active on-chain but not reporting; plus version compliance from
   `genlayer_node_info.version`. Re-pointed off 5Elements onto the portal roster.
3. **Network Status (general)** — per-network fleet health (reporting vs registered, synced vs
   behind, version spread, current epoch via `eth_call`, validator-set joined/banned/quarantined).
   Metrics-only — no roster dependency.
4. **Validator Profile** — per-validator drill-down (`$node` var). Identity header from roster
   (moniker/logo, operator, account name/avatar, explorer + portal links) + health panels
   adapted from Darien's 49-panel `validator-overview`. Co-design the panel set.

## Sequence
1. ✅ Roster source identified (portal `wall-of-shame` endpoint).
2. Set up Foundation folder + copy reference dashboards in.
3. Build **Network Status** first (metrics-only, no roster).
4. Build **Wall of Shame** against the portal roster via Infinity.
5. Build **Validator Profile** (co-design panels).
6. Build **Index** last (ties everything together).
7. Decide on the optional `points` PR after wiring the first roster-backed dashboard.
