#!/usr/bin/env python3
"""Generate the public (variable-free) Validator Status dashboard (formerly "Wall of Shame") from validator_status.json.

Run from the monitoring repo root: python3 scripts/build_public_validator_status.py
Then upload dashboards/foundation/validator_status_public.json to Grafana (uid
gl-validator-status-public, folder fkpd6m) — rerun this whenever
validator_status.json changes materially.

Public Grafana dashboards do not interpolate template variables (Prometheus exprs
silently match nothing; Infinity bodies keep the literal ${var}). So this bakes
$network / $staking_addr in per-section and drops the $latest_version-dependent
Version OK/behind logic (panels 30/31/32 and the table's F target / VersionCode
column). The quarantine targets need no rework: since Bradbury Phase 2
(2026-10-20) the source board itself reads the epoch on-chain in the same batch
JSON-RPC call as getAllQuarantinedValidators(), so there is no $current_epoch var.
"""
import copy
import json
import sys

SRC = 'dashboards/foundation/validator_status.json'
OUT = 'dashboards/foundation/validator_status_public.json'

# Asimov (asimov-phase5) and Bradbury Phase 1 (bradbury-phase1) were sunset
# 2026-10-20 when the testnet moved to Arbitrum Orbit (RPC
# https://rpc.testnet-chain.genlayer.com); Bradbury Phase 2 is the only network.
NETWORKS = [
    dict(label='Bradbury Phase 2', network='bradbury-phase2',
         staking='0xD8fBa96C0dBB0257028dBc0107060b958e5c7113', offset=200, row_id=199),
]

DROP_PANELS = {30, 31, 32, 100}  # version stats + legend (legend re-added once, rewritten)
VERSION_ALIASES = {'onlatest0', 'hasrep0', 'VersionCode', 'behindFlag', 'ver_s'}
VERSION_FIELDS = VERSION_ALIASES | {'Value #F'}


LEGEND = """**GenLayer Validator Status board — public view.** Testnet **Bradbury Phase 2** (Asimov and Bradbury Phase 1 were sunset in 2026-10). Three summary rows reconcile who *should* be validating against what is *actually* observable, then the table drills down per validator. Read-only; data is queried live on each load.

**Validators** — the roster & on-chain picture. *Total* = every known node (portal roster ∪ reporting ∪ on-chain active). The roster is deduped in the query itself: operators who re-registered keep only their live wallet(s); superseded inactive wallets are dropped, and a fully-inactive operator keeps one row. *Internal* = Foundation/Labs nodes (name contains 'GenLayer'). *On-chain active* = live Staking.selectableValidators() set (strict consensus-duty eligibility; excludes quarantined; empty until the first epoch advance). *Quarantined* = live on-chain Staking.getAllQuarantinedValidators() (NOT the portal). *Portal: active / Inactive / Banned* = portal roster status counts (Inactive is deduped the same way). *Missing* = graduated portal validators (past the waitlist) with no wallet linked on this network — either not running here at all, or running an unlinked wallet the portal can't attribute. Note: on-chain active often differs from portal active because the portal syncs periodically.

**Metrics** — *Reporting (metrics)* = nodes emitting Prometheus in the last 5 min. *Not reporting (metrics)* = on-chain active but silent on metrics.

**Logs** — *Reporting (logs)* = nodes shipping logs to Loki in the last 5 min. *Not reporting (logs)* = on-chain active but silent on logs.

**Table columns** — *Name* one merged display name, in priority order portal account name (tagged '(portal)') > on-chain identity moniker > metrics validator_name > node address · *Health* the portal's overall verdict for the node (green / yellow / orange / red / gray, with its label) — computed by the portal from the shared rule table, displayed here as-is; '-' = no verdict from the portal yet · *Identity* OK / missing: … (on-chain getIdentity() moniker/logo/description completeness) · *Linked* linked / NOT LINKED (whether the wallet is attributed to a portal account) · *In Portal* Yes/No (has a roster row on this network) · *Participating* active (green) / quarantined (orange) / no longer participating (red, permanently quarantined) / MISSING (red, graduated but no wallet on this network) / not participating (red) (live, on-chain) · *Metrics/Logs* ON/OFF/- (OFF = active or quarantined on-chain but silent; yellow) · *Node Version* as reported by the node's metrics · *Blocks Behind* from metrics. Per-column colours follow the same rule table (identity missing, not linked and missing telemetry are yellow). Rows sorted by Health (red > orange > yellow > gray > green), then worst-first by this board's own signals."""


def replace_strings(obj, mapping):
    if isinstance(obj, dict):
        return {k: replace_strings(v, mapping) for k, v in obj.items()}
    if isinstance(obj, list):
        return [replace_strings(v, mapping) for v in obj]
    if isinstance(obj, str):
        for old, new in mapping.items():
            obj = obj.replace(old, new)
        return obj
    return obj


def strip_version_logic(table):
    table['targets'] = [t for t in table['targets'] if t.get('refId') != 'F']
    trs = []
    for tr in table['transformations']:
        if tr['id'] == 'calculateField' and tr['options'].get('alias') in VERSION_ALIASES:
            continue
        if tr['id'] == 'calculateField' and tr['options'].get('alias') == 'severity':
            tr['options']['reduce']['include'] = [
                f for f in tr['options']['reduce']['include'] if f != 'ver_s']
        if tr['id'] == 'organize':
            for section in ('excludeByName', 'indexByName', 'renameByName'):
                for f in VERSION_FIELDS:
                    tr['options'][section].pop(f, None)
        trs.append(tr)
    table['transformations'] = trs
    table['fieldConfig']['overrides'] = [
        o for o in table['fieldConfig']['overrides']
        if not (o['matcher']['id'] == 'byName' and o['matcher']['options'] == 'Version')]


def build_section(src_panels, net, y_base):
    mapping = {'${staking_addr}': net['staking'], '$staking_addr': net['staking'],
               '$network': net['network']}
    panels = [{
        'collapsed': False, 'gridPos': {'h': 1, 'w': 24, 'x': 0, 'y': y_base},
        'id': net['row_id'], 'panels': [], 'title': net['label'], 'type': 'row',
    }]
    for p in src_panels:
        if p['id'] in DROP_PANELS:
            continue
        p = copy.deepcopy(p)
        if p['type'] == 'table':
            strip_version_logic(p)
        p = replace_strings(p, mapping)
        p['id'] += net['offset']
        g = p['gridPos']
        rel_y = g['y'] - 7            # stats rows at rel 0/4/8
        if p['type'] == 'table':
            rel_y = 12                # versions row dropped -> table moves up
        g['y'] = y_base + 1 + rel_y
        panels.append(p)
    return panels


def main():
    src = json.load(open(SRC))
    panels = [{
        'gridPos': {'h': 7, 'w': 24, 'x': 0, 'y': 0}, 'id': 100, 'title': 'Legend',
        'type': 'text', 'transparent': True,
        'options': {'code': {'language': 'plaintext', 'showLineNumbers': False,
                             'showMiniMap': False},
                    'content': LEGEND, 'mode': 'markdown'},
    }]
    y = 7
    for net in NETWORKS:
        section = build_section(src['panels'], net, y)
        panels.extend(section)
        y = max(p['gridPos']['y'] + p['gridPos']['h'] for p in section)

    leftovers = [s for s in ('$network', '$staking_addr', '$current_epoch', '$latest_version')
                 if s in json.dumps(panels)]
    if leftovers:
        sys.exit(f'unreplaced variables remain: {leftovers}')

    out = {
        'annotations': src['annotations'],
        'editable': True,
        'fiscalYearStartMonth': src.get('fiscalYearStartMonth', 0),
        'graphTooltip': src.get('graphTooltip', 0),
        'links': [],
        'liveNow': False,
        'panels': panels,
        'refresh': src.get('refresh', '1m'),
        'schemaVersion': src['schemaVersion'],
        'tags': ['testnet', 'wall-of-shame', 'foundation', 'public'],
        'templating': {'list': []},
        'time': src['time'],
        'timepicker': {},
        'timezone': src.get('timezone', ''),
        'title': 'Testnet | Validator Status (Public)',
        'uid': 'gl-validator-status-public',
        'weekStart': src.get('weekStart', ''),
    }
    with open(OUT, 'w') as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write('\n')
    print(f'wrote {OUT}: {len(panels)} panels, '
          f'{sum(len(p.get("targets", [])) for p in panels)} targets')


if __name__ == '__main__':
    main()
