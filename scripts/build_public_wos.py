#!/usr/bin/env python3
"""Generate the public (variable-free) Wall of Shame dashboard from wall_of_shame.json.

Run from the monitoring repo root: python3 scripts/build_public_wos.py
Then upload dashboards/foundation/wos_public.json to Grafana (uid gl-wos-public,
folder fkpd6m) — rerun this whenever wall_of_shame.json changes materially.

Public Grafana dashboards do not interpolate template variables (Prometheus exprs
silently match nothing; Infinity bodies keep the literal ${var}). So this bakes
$network / $staking_addr in per-section, replaces the $current_epoch var with a
batch JSON-RPC call (epoch() + getAllQuarantinedValidators() in one request), and
drops the $latest_version-dependent Version OK/behind logic (panels 30/31/32 and
the table's F target / VersionCode column).
"""
import copy
import json
import re
import sys

SRC = 'dashboards/foundation/wall_of_shame.json'
OUT = 'dashboards/foundation/wos_public.json'

NETWORKS = [
    dict(label='Asimov', network='asimov-phase5',
         staking='0x63Fa5E0bb10fb6fA98F44726C5518223F767687A', offset=200, row_id=199),
    dict(label='Bradbury', network='bradbury-phase1',
         staking='0x4A4449E617F8D10FDeD0b461CadEf83939E821A5', offset=400, row_id=399),
]

DROP_PANELS = {30, 31, 32, 100}  # version stats + legend (legend re-added once, rewritten)
VERSION_ALIASES = {'onlatest0', 'hasrep0', 'VersionCode', 'behindFlag', 'ver_s'}
VERSION_FIELDS = VERSION_ALIASES | {'Value #F'}

QUAR_HEAD_RE = re.compile(r'\.result\s*\|\s*ltrimstr\("0x"\)\s*\|\s*\.\[128:\]\s+as\s+\$h')
QUAR_HEAD_NEW = ('(map(select(.id==1)) | .[0].result | ltrimstr("0x") | hexval) as $cur\n'
                 '| (map(select(.id==2)) | .[0].result | ltrimstr("0x") | .[128:]) as $h')
QUAR_DATA_RE = re.compile(r'"data":"(0x510a6f26[0-9a-fA-F]*)"')

LEGEND = """**GenLayer Wall of Shame — public view.** One section per testnet (**Asimov**, **Bradbury**). Three summary rows reconcile who *should* be validating against what is *actually* observable, then the table drills down per validator. Read-only; data is queried live on each load.

**Validators** — the roster & on-chain picture. *Total* = every known node (portal roster ∪ reporting ∪ on-chain active). The roster is deduped in the query itself: operators who re-registered keep only their live wallet(s); superseded inactive wallets are dropped, and a fully-inactive operator keeps one row. *Internal* = Foundation/Labs nodes (name contains 'GenLayer'). *On-chain active* = live Staking.activeValidators() set (includes quarantined). *Quarantined* = live on-chain Staking.getAllQuarantinedValidators() (NOT the portal). *Portal: active / Inactive / Banned* = portal roster status counts (Inactive is deduped the same way). *Missing* = graduated portal validators (past the waitlist, expected on BOTH testnets) with no wallet linked on this network — either not running here at all, or running an unlinked wallet the portal can't attribute. Note: on-chain active often differs from portal active because the portal syncs periodically.

**Metrics** — *Reporting (metrics)* = nodes emitting Prometheus in the last 5 min. *Metrics SHAME* = on-chain active but silent on metrics.

**Logs** — *Reporting (logs)* = nodes shipping logs to Loki in the last 5 min. *Logs SHAME* = on-chain active but silent on logs.

**Table columns** — *Name* one merged display name, in priority order portal account name (tagged '(portal)') > on-chain identity moniker > metrics validator_name > node address · *Identity* OK / missing: … (on-chain getIdentity() moniker/logo/description completeness) · *Linked* linked / NOT LINKED (whether the wallet is attributed to a portal account) · *In Portal* Yes/No (has a roster row on this network) · *Participating* active / quarantined / MISSING (graduated but no wallet on this network) / not participating (live, on-chain) · *Metrics/Logs* ON/SHAME/- · *Node Version* as reported by the node's metrics · *Blocks Behind* from metrics. Rows sorted worst-first."""


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


def rework_quarantine_target(t, staking):
    """Batch body: id 1 = epoch() 0x900cf0cf, id 2 = getAllQuarantinedValidators."""
    m = QUAR_DATA_RE.search(t['url_options']['data'])
    if not m:
        sys.exit('quarantine target: data payload not found')
    quar_data = m.group(1)
    t['url_options']['data'] = (
        '[{"jsonrpc":"2.0","id":1,"method":"eth_call","params":[{"to":"%s","data":"0x900cf0cf"},"latest"]},'
        '{"jsonrpc":"2.0","id":2,"method":"eth_call","params":[{"to":"%s","data":"%s"},"latest"]}]'
        % (staking, staking, quar_data))
    rs = t['root_selector']
    rs, n = QUAR_HEAD_RE.subn(QUAR_HEAD_NEW, rs)
    if n != 1:
        sys.exit('quarantine target: root_selector head not matched')
    if '$current_epoch' not in rs:
        sys.exit('quarantine target: $current_epoch not found in root_selector')
    t['root_selector'] = rs.replace('$current_epoch', '$cur')


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
        for t in p.get('targets', []):
            if '0x510a6f26' in (t.get('url_options') or {}).get('data', ''):
                rework_quarantine_target(t, net['staking'])
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
        'title': 'Testnet | Wall of Shame (Public)',
        'uid': 'gl-wos-public',
        'weekStart': src.get('weekStart', ''),
    }
    with open(OUT, 'w') as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write('\n')
    print(f'wrote {OUT}: {len(panels)} panels, '
          f'{sum(len(p.get("targets", [])) for p in panels)} targets')


if __name__ == '__main__':
    main()
