#!/usr/bin/env python3
"""
Validator Telemetry Report Generator

Generates a comprehensive report of validator status by querying:
1. On-chain staking contract for active/banned validators
2. Grafana public dashboard for metrics and logs data (no auth required)

Usage:
    python validator_telemetry_report.py [--output FILE] [--format json|markdown|both]

Requirements:
    - requests library (pip install requests)

Environment Variables:
    GRAFANA_URL          - Grafana instance URL (default: https://genlayerfoundation.grafana.net)
    RPC_URL              - GenLayer RPC URL (default: https://genlayer-testnet.rpc.caldera.xyz/http)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

try:
    import requests
except ImportError:
    print("Error: requests library required. Install with: pip install requests")
    sys.exit(1)


# Configuration
DEFAULT_RPC_URL = "https://genlayer-testnet.rpc.caldera.xyz/http"
DEFAULT_GRAFANA_URL = "https://genlayerfoundation.grafana.net"
STAKING_CONTRACT = "0x10eCB157734c8152f1d84D00040c8AA46052CB27"
VALIDATOR_WALLET_FACTORY = "0x2e198119E639D1063180f281617f64Dd788D78d2"
CHAIN_ID = 4221

# Public dashboard for telemetry data (no auth required)
PUBLIC_DASHBOARD_TOKEN = "66a372d856ea44e78cf9ac21a344f792"
METRICS_PANEL_ID = 2
LOGS_PANEL_ID = 1

# Function selectors
GET_VALIDATORS_SELECTOR = "0x16e7d513"  # getValidatorsAtCurrentEpoch()
GET_BANNED_SELECTOR = "0x1972f9ce"  # getAllBannedValidators()
GET_WALLETS_FOR_OPERATOR_SELECTOR = "0xf31fa988"  # getWalletsForOperator(address)
GET_IDENTITY_SELECTOR = "0x36afc6fa"  # getIdentity()


def eth_call(rpc_url: str, contract: str, data: str) -> str:
    """Make an eth_call to the RPC endpoint."""
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_call",
        "params": [{"to": contract, "data": data}, "latest"],
        "id": 1,
    }

    response = requests.post(
        rpc_url, json=payload, headers={"Content-Type": "application/json"}, timeout=30
    )
    response.raise_for_status()
    result = response.json()

    if "error" in result:
        raise Exception(f"RPC error: {result['error']}")

    return result.get("result", "0x")


def decode_address_array(hex_result: str) -> list[str]:
    """Decode an ABI-encoded address[] from hex result."""
    hex_data = hex_result[2:]  # Remove 0x prefix
    if len(hex_data) < 128:
        return []

    offset = int(hex_data[0:64], 16) * 2
    length = int(hex_data[offset : offset + 64], 16)

    addresses = []
    for i in range(length):
        start = offset + 64 + i * 64
        addr = "0x" + hex_data[start + 24 : start + 64]
        # Filter out zero address
        if addr.lower() != "0x0000000000000000000000000000000000000000":
            addresses.append(addr)

    return addresses


def get_wallet_for_operator(rpc_url: str, operator: str) -> str | None:
    """Get the validator wallet address for an operator."""
    # Pad address to 32 bytes
    operator_padded = operator.lower().replace("0x", "").zfill(64)
    data = GET_WALLETS_FOR_OPERATOR_SELECTOR + operator_padded

    try:
        result = eth_call(rpc_url, VALIDATOR_WALLET_FACTORY, data)
        wallets = decode_address_array(result)
        return wallets[0] if wallets else None
    except Exception:
        return None


def get_validator_moniker(rpc_url: str, wallet_address: str) -> str | None:
    """Get the moniker from a validator wallet's identity."""
    try:
        result = eth_call(rpc_url, wallet_address, GET_IDENTITY_SELECTOR)
        hex_data = result[2:]

        if len(hex_data) < 128:
            return None

        # Parse the struct: first word is outer offset to struct
        outer_offset = int(hex_data[0:64], 16)
        struct_start = outer_offset * 2  # Position in hex string
        struct_hex = hex_data[struct_start:]

        # First field offset in struct points to moniker
        moniker_offset = int(struct_hex[0:64], 16)
        moniker_pos = moniker_offset * 2

        # Read moniker length and data
        moniker_len = int(struct_hex[moniker_pos : moniker_pos + 64], 16)

        if moniker_len == 0 or moniker_len > 1000:
            return None

        moniker_bytes = bytes.fromhex(
            struct_hex[moniker_pos + 64 : moniker_pos + 64 + moniker_len * 2]
        )
        return moniker_bytes.decode("utf-8")
    except Exception:
        return None


def get_onchain_validators(rpc_url: str) -> dict[str, Any]:
    """Fetch active and banned validators from on-chain contract."""
    print("Fetching on-chain validators...")

    active_result = eth_call(rpc_url, STAKING_CONTRACT, GET_VALIDATORS_SELECTOR)
    active_validators = decode_address_array(active_result)
    print(f"  Found {len(active_validators)} active validators")

    banned_result = eth_call(rpc_url, STAKING_CONTRACT, GET_BANNED_SELECTOR)
    banned_validators = decode_address_array(banned_result)
    print(f"  Found {len(banned_validators)} banned validators")

    # Create sets for lookup
    active_set = set(addr.lower() for addr in active_validators)
    banned_set = set(addr.lower() for addr in banned_validators)

    # Combine all unique addresses
    all_addresses = set(active_validators + banned_validators)

    # Fetch monikers for active validators
    print("  Fetching validator monikers from on-chain...")
    address_to_moniker = {}
    moniker_to_address = {}
    for addr in active_validators:
        wallet = get_wallet_for_operator(rpc_url, addr)
        if wallet:
            moniker = get_validator_moniker(rpc_url, wallet)
            if moniker:
                address_to_moniker[addr.lower()] = moniker
                moniker_to_address[moniker] = addr
    print(f"    Found {len(address_to_moniker)} validators with monikers")

    validators = []
    for addr in sorted(all_addresses, key=str.lower):
        addr_lower = addr.lower()
        is_active = addr_lower in active_set
        is_banned = addr_lower in banned_set

        if is_active and not is_banned:
            status = "active"
        elif is_banned and not is_active:
            status = "banned"
        elif is_active and is_banned:
            status = "active_and_banned"
        else:
            status = "unknown"

        validators.append(
            {
                "address": addr,
                "moniker": address_to_moniker.get(addr_lower),
                "status": status,
                "is_active": is_active,
                "is_banned": is_banned,
            }
        )

    return {
        "validators": validators,
        "address_to_moniker": address_to_moniker,
        "moniker_to_address": moniker_to_address,
        "summary": {
            "total_unique": len(validators),
            "active_count": sum(1 for v in validators if v["is_active"]),
            "banned_count": sum(1 for v in validators if v["is_banned"]),
            "active_only": sum(1 for v in validators if v["status"] == "active"),
            "banned_only": sum(1 for v in validators if v["status"] == "banned"),
            "active_and_banned": sum(
                1 for v in validators if v["status"] == "active_and_banned"
            ),
            "with_moniker": len(address_to_moniker),
        },
    }


def query_public_dashboard_panel(
    grafana_url: str, dashboard_token: str, panel_id: int, time_from: str = "now-1h"
) -> list[str]:
    """Query a panel from a public Grafana dashboard (no auth required)."""
    url = f"{grafana_url}/api/public/dashboards/{dashboard_token}/panels/{panel_id}/query"
    headers = {"Content-Type": "application/json"}
    payload = {"from": time_from, "to": "now"}

    response = requests.post(url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    result = response.json()

    # Extract validator_name labels from the response frames
    validators = set()
    frames = result.get("results", {}).get("A", {}).get("frames", [])
    for frame in frames:
        fields = frame.get("schema", {}).get("fields", [])
        for field in fields:
            labels = field.get("labels", {})
            if "validator_name" in labels:
                validators.add(labels["validator_name"])

    return sorted(list(validators))


def get_telemetry_data(grafana_url: str) -> dict[str, Any]:
    """Fetch telemetry data from Grafana public dashboard (no auth required)."""
    print("Fetching telemetry data from public dashboard...")

    # Query metrics panel (panel ID 2)
    print("  Querying metrics panel...")
    try:
        metrics_names = query_public_dashboard_panel(
            grafana_url, PUBLIC_DASHBOARD_TOKEN, METRICS_PANEL_ID, "now-15m"
        )
        print(f"    Found {len(metrics_names)} validators pushing metrics")
    except Exception as e:
        print(f"    Warning: Failed to query metrics panel: {e}")
        metrics_names = []

    # Query logs panel (panel ID 1)
    print("  Querying logs panel...")
    try:
        logs_names = query_public_dashboard_panel(
            grafana_url, PUBLIC_DASHBOARD_TOKEN, LOGS_PANEL_ID, "now-1h"
        )
        print(f"    Found {len(logs_names)} validators pushing logs")
    except Exception as e:
        print(f"    Warning: Failed to query logs panel: {e}")
        logs_names = []

    return {
        "metrics": {
            "validators": metrics_names,
            "count": len(metrics_names),
        },
        "logs": {
            "validators": logs_names,
            "count": len(logs_names),
        },
    }


def generate_report(
    onchain_data: dict, telemetry_data: dict, rpc_url: str, grafana_url: str
) -> dict[str, Any]:
    """Generate the combined report."""
    metrics_set = set(telemetry_data["metrics"]["validators"])
    logs_set = set(telemetry_data["logs"]["validators"])

    # 4 categories of telemetry status
    fully_configured = metrics_set & logs_set  # Both metrics AND logs
    metrics_only = metrics_set - logs_set  # Only metrics, no logs
    logs_only = logs_set - metrics_set  # Only logs, no metrics
    all_with_telemetry = metrics_set | logs_set  # Any telemetry at all

    # Match on-chain validators with telemetry data using monikers
    moniker_to_address = onchain_data.get("moniker_to_address", {})
    address_to_moniker = onchain_data.get("address_to_moniker", {})

    # Find validators with no telemetry by comparing monikers
    active_monikers = set(
        v["moniker"]
        for v in onchain_data["validators"]
        if v["is_active"] and v["moniker"]
    )
    no_telemetry_monikers = active_monikers - all_with_telemetry

    # Find active validators without monikers (can't match to telemetry)
    validators_without_monikers = [
        v for v in onchain_data["validators"] if v["is_active"] and not v["moniker"]
    ]

    # Create detailed no_telemetry list with addresses
    no_telemetry_list = []
    for moniker in sorted(no_telemetry_monikers):
        addr = moniker_to_address.get(moniker, "unknown")
        no_telemetry_list.append({"moniker": moniker, "address": addr})

    # Add validators without monikers (unknown names)
    for v in validators_without_monikers:
        no_telemetry_list.append({"moniker": None, "address": v["address"]})

    onchain_count = onchain_data["summary"]["active_count"]

    report = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "description": "Validator telemetry status report",
            "sources": {
                "on_chain": {
                    "contract": STAKING_CONTRACT,
                    "factory": VALIDATOR_WALLET_FACTORY,
                    "rpc": rpc_url,
                    "chain_id": CHAIN_ID,
                },
                "telemetry": {
                    "grafana_url": grafana_url,
                    "dashboard": f"{grafana_url}/d/agfnnmw/who-is-pushing",
                    "public_dashboard": f"{grafana_url}/public-dashboards/{PUBLIC_DASHBOARD_TOKEN}",
                },
            },
        },
        "summary": {
            "on_chain_validators": onchain_data["summary"],
            "telemetry_status": {
                "fully_configured": len(fully_configured),
                "metrics_only": len(metrics_only),
                "logs_only": len(logs_only),
                "no_telemetry": len(no_telemetry_list),
                "total_with_any_telemetry": len(all_with_telemetry),
            },
        },
        "validators": {
            "fully_configured": {
                "description": "Validators pushing both metrics AND logs",
                "count": len(fully_configured),
                "names": sorted(list(fully_configured)),
            },
            "metrics_only": {
                "description": "Validators pushing metrics but NOT logs",
                "count": len(metrics_only),
                "names": sorted(list(metrics_only)),
                "recommendation": "Configure Grafana Alloy to push logs",
            },
            "logs_only": {
                "description": "Validators pushing logs but NOT metrics",
                "count": len(logs_only),
                "names": sorted(list(logs_only)),
                "recommendation": "Configure Prometheus metrics forwarding",
            },
            "no_telemetry": {
                "description": "On-chain validators with no telemetry data",
                "count": len(no_telemetry_list),
                "validators": no_telemetry_list,
                "recommendation": "Configure Grafana Alloy for metrics and logs",
            },
        },
        "on_chain_validators": {
            "active_and_healthy": [
                {"address": v["address"], "moniker": v["moniker"]}
                for v in onchain_data["validators"]
                if v["status"] == "active"
            ],
            "active_but_banned": [
                {"address": v["address"], "moniker": v["moniker"]}
                for v in onchain_data["validators"]
                if v["status"] == "active_and_banned"
            ],
            "banned_only": [
                {"address": v["address"], "moniker": v["moniker"]}
                for v in onchain_data["validators"]
                if v["status"] == "banned"
            ],
        },
        "analysis": {
            "telemetry_adoption_rate": f"{len(all_with_telemetry) / max(onchain_count, 1) * 100:.1f}%",
            "full_observability_rate": f"{len(fully_configured) / max(onchain_count, 1) * 100:.1f}%",
        },
    }

    return report


def generate_markdown(report: dict) -> str:
    """Generate a markdown version of the report."""
    summary = report["summary"]
    telemetry = summary["telemetry_status"]
    onchain = summary["on_chain_validators"]
    validators = report["validators"]
    analysis = report["analysis"]

    md = f"""# Validator Telemetry Report

**Generated:** {report['metadata']['generated_at']}

## Executive Summary

| Category | Count |
|----------|-------|
| On-chain active validators | {onchain['active_count']} |
| **Fully configured** (metrics + logs) | {telemetry['fully_configured']} |
| **Metrics only** (missing logs) | {telemetry['metrics_only']} |
| **Logs only** (missing metrics) | {telemetry['logs_only']} |
| **No telemetry** | {telemetry['no_telemetry']} |

**Telemetry adoption rate:** {analysis['telemetry_adoption_rate']}
**Full observability rate:** {analysis['full_observability_rate']}

---

## 1. Fully Configured (Metrics + Logs) - {validators['fully_configured']['count']} validators

{chr(10).join(f"- {name}" for name in validators['fully_configured']['names']) or "_None_"}

---

## 2. Metrics Only (Missing Logs) - {validators['metrics_only']['count']} validators

> **Recommendation:** {validators['metrics_only'].get('recommendation', 'N/A')}

{chr(10).join(f"- {name}" for name in validators['metrics_only']['names']) or "_None_"}

---

## 3. Logs Only (Missing Metrics) - {validators['logs_only']['count']} validators

> **Recommendation:** {validators['logs_only'].get('recommendation', 'N/A')}

{chr(10).join(f"- {name}" for name in validators['logs_only']['names']) or "_None_"}

---

## 4. No Telemetry - {validators['no_telemetry']['count']} validators

> **Recommendation:** {validators['no_telemetry'].get('recommendation', 'N/A')}

{chr(10).join(f"- {v['moniker'] or 'Unknown'} (`{v['address'][:10]}...{v['address'][-6:]}`)" for v in validators['no_telemetry'].get('validators', [])) or "_None_"}

---

## On-Chain Status

- **Active only:** {onchain['active_only']}
- **Active + Banned:** {onchain['active_and_banned']}
- **Banned only:** {onchain['banned_only']}

---

## Data Sources

- **On-chain:** `{report['metadata']['sources']['on_chain']['contract']}`
- **Dashboard:** {report['metadata']['sources']['telemetry']['dashboard']}
"""
    return md


def main():
    parser = argparse.ArgumentParser(
        description="Generate validator telemetry report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output",
        "-o",
        default="validator-telemetry-report.json",
        help="Output file path (default: validator-telemetry-report.json)",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["json", "markdown", "both"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--rpc-url",
        default=os.environ.get("RPC_URL", DEFAULT_RPC_URL),
        help=f"RPC URL (default: {DEFAULT_RPC_URL})",
    )
    parser.add_argument(
        "--grafana-url",
        default=os.environ.get("GRAFANA_URL", DEFAULT_GRAFANA_URL),
        help=f"Grafana URL (default: {DEFAULT_GRAFANA_URL})",
    )
    parser.add_argument(
        "--skip-telemetry",
        action="store_true",
        help="Skip Grafana telemetry queries (on-chain data only)",
    )

    args = parser.parse_args()

    # Fetch on-chain data
    onchain_data = get_onchain_validators(args.rpc_url)

    # Fetch telemetry data from public dashboard (no auth required)
    if args.skip_telemetry:
        telemetry_data = {
            "metrics": {"validators": [], "count": 0},
            "logs": {"validators": [], "count": 0},
        }
    else:
        telemetry_data = get_telemetry_data(args.grafana_url)

    # Generate report
    report = generate_report(
        onchain_data, telemetry_data, args.rpc_url, args.grafana_url
    )

    # Output
    if args.format in ("json", "both"):
        output_path = args.output
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nJSON report saved to: {output_path}")

    if args.format in ("markdown", "both"):
        md_output = args.output.replace(".json", ".md")
        if args.format == "markdown":
            md_output = args.output
        markdown = generate_markdown(report)
        with open(md_output, "w") as f:
            f.write(markdown)
        print(f"Markdown report saved to: {md_output}")

    # Print summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"On-chain active validators: {onchain_data['summary']['active_count']}")
    if not args.skip_telemetry:
        telemetry_status = report["summary"]["telemetry_status"]
        print(f"\nTelemetry Status:")
        print(f"  1. Fully configured (metrics + logs): {telemetry_status['fully_configured']}")
        print(f"  2. Metrics only (missing logs):       {telemetry_status['metrics_only']}")
        print(f"  3. Logs only (missing metrics):       {telemetry_status['logs_only']}")
        print(f"  4. No telemetry:                      {telemetry_status['no_telemetry']}")
        print(f"\nTelemetry adoption: {report['analysis']['telemetry_adoption_rate']}")
        print(f"Full observability: {report['analysis']['full_observability_rate']}")


if __name__ == "__main__":
    main()
