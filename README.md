# GenLayer Monitoring & Alerting

This repository contains monitoring and alerting configurations for GenLayer infrastructure, including Grafana alert rules, dashboards, and notification policies.

## Overview

GenLayer uses Grafana Cloud for comprehensive monitoring and alerting across the validator network. This repository serves as the source of truth for:

- Alert rule configurations
- Notification policies
- Monitoring documentation
- Grafana dashboard configurations (when added)

## Infrastructure

### Grafana Cloud Stack
- **Instance**: `genlayerfoundation.grafana.net`
- **Organization**: GenLayer Foundation

### Datasources
- **Prometheus** (`grafanacloud-prom`): Metrics collection - Default datasource
- **Loki** (`grafanacloud-logs`): Log aggregation
- **Tempo** (`grafanacloud-traces`): Distributed tracing
- **Pyroscope** (`grafanacloud-profiles`): Continuous profiling

### Contact Points
- **GenLayerLabs Slack** (`af9yk9dbw5af4f`): Primary notification channel for alerts

## Alert Rules

### Validator Memory Alerts

Located in: `grafana-alerts/`

Three alert rules monitor Go memory usage across validators:

#### 1. High Memory Usage: 3+ Validators Above 1GB
- **File**: `alert-1gb-memory-threshold.json`
- **UID**: `dfa1nyolt0cg0b`
- **Severity**: Warning
- **Condition**: Triggers when ≥3 validators exceed 1GB memory allocation
- **Query**: `count(go_memstats_alloc_bytes{validator_name!=""} > 1e9)`

#### 2. High Memory Usage: 3+ Validators Above 2GB
- **File**: `alert-2gb-memory-threshold.json`
- **UID**: `efa1nyp7dfxfkb`
- **Severity**: Critical
- **Condition**: Triggers when ≥3 validators exceed 2GB memory allocation
- **Query**: `count(go_memstats_alloc_bytes{validator_name!=""} > 2e9)`

#### 3. High Memory Usage: 3+ Validators Above 3GB
- **File**: `alert-3gb-memory-threshold.json`
- **UID**: `dfa1nypsvkglcc`
- **Severity**: Critical
- **Condition**: Triggers when ≥3 validators exceed 3GB memory allocation
- **Query**: `count(go_memstats_alloc_bytes{validator_name!=""} > 3e9)`

### Alert Configuration

All validator memory alerts:
- **Evaluation interval**: Every 1 minute
- **Pending duration**: 5 minutes (alert fires after condition persists)
- **Folder**: GenLayer Labs (`dfa1v9yck3ny8b`)
- **Rule Group**: Validator Memory Alerts

**Labels:**
- `asimov-alert`: "true" (routing label)
- `component`: "validator"
- `severity`: "warning" or "critical"
- `threshold`: "1gb", "2gb", or "3gb"

## Notification Routing

Alerts are routed to Slack using label-based matching:

```
Matcher: asimov-alert = true
Contact Point: GenLayerLabs slack
Grouping: alertname, threshold
Group Wait: 30s
Group Interval: 5m
Repeat Interval: 4h
```

This ensures all validator memory alerts are sent to the GenLayerLabs Slack channel with appropriate grouping to avoid notification spam.

## Dashboards

Located in: `dashboards/`

- **general_monitor.json**: General monitoring dashboard for GenLayer infrastructure
- **whoispushing.json**: Dashboard for tracking deployment and push activity

To import dashboards into Grafana:
1. Go to **Dashboards** → **Import**
2. Upload the JSON file or paste its contents
3. Select the appropriate datasources

## Monitored Metrics

### Go Runtime Metrics

The following Go runtime metrics are available from validators via `go_memstats_*`:

**Memory Allocation:**
- `go_memstats_alloc_bytes` - Currently allocated bytes
- `go_memstats_alloc_bytes_total` - Total bytes allocated (cumulative)
- `go_memstats_heap_alloc_bytes` - Heap bytes allocated
- `go_memstats_heap_inuse_bytes` - Heap bytes in use

**Garbage Collection:**
- `go_gc_duration_seconds` - GC pause duration
- `go_memstats_next_gc_bytes` - Target heap size for next GC
- `go_memstats_last_gc_time_seconds` - Last GC completion time

**Concurrency:**
- `go_goroutines` - Number of goroutines
- `go_threads` - Number of OS threads

See `grafana-alerts/README.md` for a complete list of available Go metrics.

## Repository Structure

```
monitoring/
├── README.md                           # This file
├── dashboards/                         # Grafana dashboard configurations
│   ├── general_monitor.json
│   └── whoispushing.json
└── grafana-alerts/                     # Alert rule configurations
    ├── README.md                       # Detailed alert documentation
    ├── alert-1gb-memory-threshold.json
    ├── alert-2gb-memory-threshold.json
    └── alert-3gb-memory-threshold.json
```

## Managing Alerts

### Via Grafana UI
1. Navigate to `https://genlayerfoundation.grafana.net`
2. Go to **Alerting** → **Alert rules**
3. Filter by folder: "GenLayer Labs"

### Via API

Export Grafana API key:
```bash
export GRAFANA_API_KEY="your-api-key"
export GRAFANA_URL="https://genlayerfoundation.grafana.net"
```

List all alerts:
```bash
curl -H "Authorization: Bearer $GRAFANA_API_KEY" \
  "$GRAFANA_URL/api/v1/provisioning/alert-rules"
```

Get specific alert:
```bash
curl -H "Authorization: Bearer $GRAFANA_API_KEY" \
  "$GRAFANA_URL/api/v1/provisioning/alert-rules/dfa1nyolt0cg0b"
```

### Via MCP (Model Context Protocol)

This repository was configured using Claude Code with the Grafana MCP server, which provides programmatic access to Grafana resources.

## Contributing

When adding new alerts or dashboards:

1. Create/modify the resource in Grafana
2. Export the JSON configuration
3. Save to the appropriate directory in this repo
4. Update relevant README documentation
5. Commit and push changes

## Support

For issues with monitoring or alerting:
- Check the GenLayerLabs Slack channel for active alerts
- Review alert history in Grafana Cloud
- Contact the infrastructure team

## License

Internal GenLayer Foundation repository.
