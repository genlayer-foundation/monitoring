# Grafana Alert Rules

This folder contains Grafana alert rule configurations for monitoring validator memory usage.

## Alert Rules

### 1. High Memory Usage: 3+ Validators Above 1GB
- **File**: `alert-1gb-memory-threshold.json`
- **UID**: `dfa1nyolt0cg0b`
- **Severity**: Warning
- **Condition**: Triggers when at least 3 validators have `go_memstats_alloc_bytes` above 1GB
- **Duration**: 5 minutes
- **Query**: `count(go_memstats_alloc_bytes{validator_name!=""} > 1e9)`

### 2. High Memory Usage: 3+ Validators Above 2GB
- **File**: `alert-2gb-memory-threshold.json`
- **UID**: `efa1nyp7dfxfkb`
- **Severity**: Critical
- **Condition**: Triggers when at least 3 validators have `go_memstats_alloc_bytes` above 2GB
- **Duration**: 5 minutes
- **Query**: `count(go_memstats_alloc_bytes{validator_name!=""} > 2e9)`

### 3. High Memory Usage: 3+ Validators Above 3GB
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

All alerts include the following labels:
- `component`: "validator"
- `severity`: "warning" (1GB) or "critical" (2GB, 3GB)
- `threshold`: "1gb", "2gb", or "3gb"
