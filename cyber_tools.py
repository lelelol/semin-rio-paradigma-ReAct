"""
Cybersecurity Tools — Simulated mitigation actions for the ReAct agent.

These tools replicate the actions described in the paper:
- UFW firewall rules (block/unblock IPs)
- Host isolation
- Traffic analysis
- Vulnerability checking

In a production environment, these would execute real commands
via SSH (paramiko) on target hosts, as shown in the paper's Box 3.
"""

import datetime
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# In-memory firewall state (simulates UFW rules)
_firewall_rules: list[dict] = []
_isolated_hosts: list[str] = []
_action_log: list[dict] = []


def get_action_log() -> list[dict]:
    """Return the full action log."""
    return _action_log.copy()


def get_firewall_rules() -> list[dict]:
    """Return current firewall rules."""
    return _firewall_rules.copy()


def _log_action(tool_name: str, args: dict, result: dict):
    """Log an action for audit trail."""
    entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tool": tool_name,
        "arguments": args,
        "result": result,
    }
    _action_log.append(entry)
    logger.info(f"Action executed: {tool_name} | Args: {args} | Result: {result}")


def execute_ufw(source_ip: str, action: str = "deny", target_host: str = "localhost") -> dict:
    """
    Simulate executing a UFW (Uncomplicated Firewall) command.

    In production, this would SSH into the target host and run:
        ufw deny from <source_ip>

    Args:
        source_ip: The IP address to block/allow.
        action: 'deny' or 'allow'. Default is 'deny'.
        target_host: The host where the rule should be applied.

    Returns:
        dict with status and message.
    """
    rule = {
        "id": len(_firewall_rules) + 1,
        "action": action,
        "source_ip": source_ip,
        "target_host": target_host,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    _firewall_rules.append(rule)

    result = {
        "status": "success",
        "message": f"Ran command on {target_host}, stdout:\nRules updated\n"
                   f"Rule added: ufw {action} from {source_ip}",
        "rule_id": rule["id"],
    }

    _log_action("execute_ufw", {"source_ip": source_ip, "action": action, "target_host": target_host}, result)
    return result


def analyze_traffic(source_ip: str, dest_ip: str = "178.128.236.118", dest_port: int = 0) -> dict:
    """
    Simulate traffic analysis for a given source IP.

    In production, this would query Suricata/Wazuh logs or
    run packet capture analysis.

    Args:
        source_ip: The source IP to analyze.
        dest_ip: The destination IP being targeted.
        dest_port: The destination port being targeted.

    Returns:
        dict with analysis results.
    """
    # Simulate analysis based on port
    port_services = {
        22: ("SSH", "high", "Possible brute-force attack"),
        80: ("HTTP", "medium", "Web scanning activity"),
        443: ("HTTPS", "medium", "Encrypted traffic probe"),
        3306: ("MySQL", "high", "Database reconnaissance"),
        5432: ("PostgreSQL", "high", "Database reconnaissance"),
        8080: ("HTTP-Alt", "medium", "Application scanning"),
        6667: ("IRC", "critical", "Possible botnet C2 channel"),
    }

    service, severity, description = port_services.get(
        dest_port, ("Unknown", "low", "General port probe")
    )

    result = {
        "status": "success",
        "source_ip": source_ip,
        "dest_ip": dest_ip,
        "dest_port": dest_port,
        "service": service,
        "severity": severity,
        "description": description,
        "packet_count": 1247,
        "connection_attempts": 89,
        "recommendation": f"Block {source_ip} — {description} detected on port {dest_port} ({service})",
    }

    _log_action("analyze_traffic", {"source_ip": source_ip, "dest_port": dest_port}, result)
    return result


def isolate_host(host_ip: str, reason: str = "Suspected compromise") -> dict:
    """
    Simulate isolating a host from the network.

    In production, this would modify network ACLs or VLAN assignments
    to quarantine the host.

    Args:
        host_ip: The IP of the host to isolate.
        reason: The reason for isolation.

    Returns:
        dict with isolation status.
    """
    _isolated_hosts.append(host_ip)

    result = {
        "status": "success",
        "message": f"Host {host_ip} has been isolated from the network. Reason: {reason}",
        "isolated_hosts": _isolated_hosts.copy(),
    }

    _log_action("isolate_host", {"host_ip": host_ip, "reason": reason}, result)
    return result


def check_vulnerability(port: int, service: str = "") -> dict:
    """
    Simulate checking for known vulnerabilities on a given port/service.

    In production, this would query CVE databases or run vulnerability
    scanners like OpenVAS.

    Args:
        port: The port number to check.
        service: Optional service name.

    Returns:
        dict with vulnerability assessment.
    """
    known_vulns = {
        22: [{"cve": "CVE-2024-6387", "severity": "high", "description": "OpenSSH RegreSSHion RCE"}],
        3306: [{"cve": "CVE-2024-21047", "severity": "medium", "description": "MySQL Server privilege escalation"}],
        5432: [{"cve": "CVE-2024-10978", "severity": "high", "description": "PostgreSQL SET ROLE privilege escalation"}],
        80: [{"cve": "CVE-2024-38476", "severity": "medium", "description": "Apache HTTP Server SSRF"}],
    }

    vulns = known_vulns.get(port, [])

    result = {
        "status": "success",
        "port": port,
        "service": service or f"port-{port}",
        "vulnerabilities_found": len(vulns),
        "vulnerabilities": vulns,
        "recommendation": "Patch immediately" if vulns else "No known vulnerabilities",
    }

    _log_action("check_vulnerability", {"port": port, "service": service}, result)
    return result


# Tool registry for the ReAct agent
TOOLS = {
    "execute_ufw": {
        "function": execute_ufw,
        "description": (
            "Block or allow an IP address using UFW firewall. "
            "Use this to block malicious IPs detected in alerts. "
            "Parameters: source_ip (required), action ('deny' or 'allow', default 'deny'), "
            "target_host (default 'localhost')."
        ),
    },
    "analyze_traffic": {
        "function": analyze_traffic,
        "description": (
            "Analyze network traffic from a specific source IP. "
            "Returns severity assessment and recommendations. "
            "Parameters: source_ip (required), dest_ip, dest_port."
        ),
    },
    "isolate_host": {
        "function": isolate_host,
        "description": (
            "Isolate a compromised host from the network. "
            "Use for critical threats where a host may be compromised. "
            "Parameters: host_ip (required), reason."
        ),
    },
    "check_vulnerability": {
        "function": check_vulnerability,
        "description": (
            "Check for known CVE vulnerabilities on a specific port/service. "
            "Parameters: port (required), service (optional)."
        ),
    },
}


def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict:
    """
    Execute a cybersecurity tool by name with given arguments.

    Args:
        tool_name: Name of the tool to execute.
        arguments: Dictionary of arguments to pass to the tool.

    Returns:
        dict with execution results.
    """
    if tool_name not in TOOLS:
        return {"status": "error", "message": f"Unknown tool: {tool_name}"}

    try:
        func = TOOLS[tool_name]["function"]
        return func(**arguments)
    except TypeError as e:
        return {"status": "error", "message": f"Invalid arguments for {tool_name}: {e}"}
    except Exception as e:
        return {"status": "error", "message": f"Tool execution failed: {e}"}
