# Foundation node LLM telemetry

The node-side half of the `gl-llm-providers` board
(`dashboards/foundation/llm_providers.json`). These files run ON the Foundation
node (`ssh genlayer-node`), not in Grafana. Alloy already ships every
`/opt/genlayer-node/data/node/logs/node*.log` file, so nothing here touches Alloy.

| File | Installed at | Writes |
|---|---|---|
| `genvm-llm-rotate.lua` | `/opt/genlayer-node/<node-version>/opt/genvm/<genvm-version>/config/genvm-llm-rotate.lua` | `node-llm-calls.log`: one `attempt` line per provider try, one `prompt` line per prompt |
| `unhardcoded-usage-poll.py` | `/opt/genlayer-node/llm-telemetry/` | `node-llm-unhardcoded.log`: the model and upstream unhardcoded actually served, from its `/v1/usage` |
| `unhardcoded-usage-poll.{service,timer}` | `/etc/systemd/system/` | runs the poller every 5 min as `genlayer` |

The unhardcoded key stays on the node: the poller reads `UNHARDCODEDKEY` from
`/opt/genlayer-node/.env` at runtime. Grafana only reads the log.

## ⚠️ Re-apply after every node upgrade

A node or GenVM upgrade ships a fresh `genvm-llm-rotate.lua` and the board
silently drops to 0. The lua is the stock rotation script plus logging. Diff it
against the new stock file before copying: if upstream changed the rotation
(`ROTATE`, providers, policy), port the logging onto the new file instead of
overwriting it.

```bash
F=$(ssh genlayer-node 'find /opt/genlayer-node/$(basename $(dirname $(readlink -f /opt/genlayer-node/.env)))/opt/genvm -name genvm-llm-rotate.lua')
scp node-telemetry/genvm-llm-rotate.lua genlayer-node:/tmp/
ssh genlayer-node "sudo cp $F $F.orig && sudo install -o genlayer -g genlayer -m 644 /tmp/genvm-llm-rotate.lua $F && sudo systemctl restart genlayer-node"
```

Check it took: the startup self-test writes one `attempt` and one `prompt`
line to `node-llm-calls.log` within seconds of the restart.

Rollback: copy `$F.orig` back and restart. The 2026-11-03 originals are in
`/opt/genlayer-node/config-backups/llm-telemetry-20261103/`.
