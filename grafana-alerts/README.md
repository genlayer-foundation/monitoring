# Grafana Alert Rules

This folder contains Grafana alert rule configurations for monitoring GenLayer nodes and validators.

## Alert Rules

### Node Sync Alerts

#### 1. Node Falling Behind: Blocks Behind Increasing
- **File**: `alert-node-blocks-behind-increasing.json`
- **UID**: `afa2b791io0sgb`
- **Severity**: Critical
- **Condition**: Triggers when any node's `genlayer_node_blocks_behind` metric has increased over the last 5 minutes
- **Duration**: 5 minutes (pending after condition is met)
- **Query**: `count(increase(genlayer_node_blocks_behind[5m]) > 0)`
- **Description**: Detects when one or more nodes are falling behind blockchain sync by checking if the blocks_behind metric increased over a 5-minute window. Any increase indicates the node is falling further behind.

### Node Performance Alerts

#### 1. GenVM Permits Exhausted: Permits Reached Zero
- **File**: `alert-genvm-permits-exhausted.json`
- **UID**: `bfa2cinxy13wgf`
- **Severity**: Critical
- **Condition**: Triggers when any validator's `genlayer_node_genvm_permits_current` metric equals 0
- **Duration**: 1 minute (pending after condition is met)
- **Query**: `count(genlayer_node_genvm_permits_current == 0)`
- **Description**: Detects when validators have exhausted their GenVM execution permits. When permits reach zero, the GenVM execution pool is saturated and cannot process new requests, indicating severe resource contention.

### Validator Memory Alerts

#### 1. High Memory Usage: 3+ Validators Above 1GB
- **File**: `alert-1gb-memory-threshold.json`
- **UID**: `dfa1nyolt0cg0b`
- **Severity**: Warning
- **Condition**: Triggers when at least 3 validators have `go_memstats_alloc_bytes` above 1GB
- **Duration**: 5 minutes
- **Query**: `count(go_memstats_alloc_bytes{validator_name!=""} > 1e9)`

#### 2. High Memory Usage: 3+ Validators Above 2GB
- **File**: `alert-2gb-memory-threshold.json`
- **UID**: `efa1nyp7dfxfkb`
- **Severity**: Critical
- **Condition**: Triggers when at least 3 validators have `go_memstats_alloc_bytes` above 2GB
- **Duration**: 5 minutes
- **Query**: `count(go_memstats_alloc_bytes{validator_name!=""} > 2e9)`

#### 3. High Memory Usage: 3+ Validators Above 3GB
- **File**: `alert-3gb-memory-threshold.json`
- **UID**: `dfa1nypsvkglcc`
- **Severity**: Critical
- **Condition**: Triggers when at least 3 validators have `go_memstats_alloc_bytes` above 3GB
- **Duration**: 5 minutes
- **Query**: `count(go_memstats_alloc_bytes{validator_name!=""} > 3e9)`

## Alert Structure

Each alert uses a two-step query structure:
1. **Query A**: Instant Prometheus query that counts validators exceeding the memory threshold
2. **Expression B**: Classic condition that evaluates if the count is greater than 3

All alerts are configured to:
- Use the `grafanacloud-prom` datasource
- Fire after the condition persists for 5 minutes
- Alert on execution errors
- Return to "NoData" state when no data is available

## Labels

All alerts include the `asimov-alert: "true"` label for routing to Slack.

**Node Sync Alerts:**
- `component`: "node-sync"
- `severity`: "critical"

**Node Performance Alerts:**
- `component`: "genvm"
- `severity`: "critical"

**Validator Memory Alerts:**
- `component`: "validator"
- `severity`: "warning" (1GB) or "critical" (2GB, 3GB)
- `threshold`: "1gb", "2gb", or "3gb"
