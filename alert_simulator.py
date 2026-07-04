"""
Alert Simulator — Generates realistic Wazuh/Suricata security alerts.

Simulates the monitoring module described in the paper (Section III-B):
- Wazuh agent alerts (file integrity, auth failures, system events)
- Suricata IDS alerts (port scans, intrusion attempts, botnet traffic)

Alerts follow the exact JSON structure shown in the paper's Table I and Box 1.
"""

import datetime
import random
import uuid


# Realistic source IPs (simulated attackers from various geolocations)
ATTACKER_IPS = [
    "99.242.37.73",    # Canada
    "185.220.101.34",  # Germany (Tor exit node)
    "45.33.32.156",    # US (known scanner)
    "103.152.118.24",  # Indonesia
    "91.240.118.172",  # Russia
    "112.85.42.187",   # China
    "177.54.150.200",  # Brazil
    "23.129.64.130",   # US (Tor exit)
    "194.26.192.64",   # Netherlands
    "80.82.77.139",    # Netherlands (Censys scanner)
]

# Target infrastructure IPs
TARGET_IPS = [
    "178.128.236.118",
    "178.128.236.119",
    "178.128.236.120",
]

# Alert templates based on the paper's real observations
ALERT_TEMPLATES = [
    # Port scanning alerts (Suricata)
    {
        "type": "suricata",
        "rule_id": "86601",
        "rule_level": 3,
        "description": "Suricata: Alert- ET SCAN Suspicious inbound to mySQL port 3306",
        "dest_port": 3306,
        "groups": ["ids", "suricata"],
        "severity": "medium",
        "category": "port_scan",
    },
    {
        "type": "suricata",
        "rule_id": "86601",
        "rule_level": 3,
        "description": "Suricata: Alert- ET SCAN Suspicious inbound to PostgreSQL port 5432",
        "dest_port": 5432,
        "groups": ["ids", "suricata"],
        "severity": "medium",
        "category": "port_scan",
    },
    {
        "type": "suricata",
        "rule_id": "86602",
        "rule_level": 5,
        "description": "Suricata: Alert- ET SCAN Potential SSH Scan OUTBOUND",
        "dest_port": 22,
        "groups": ["ids", "suricata"],
        "severity": "high",
        "category": "port_scan",
    },
    # SSH brute-force alerts (Wazuh)
    {
        "type": "wazuh",
        "rule_id": "5710",
        "rule_level": 5,
        "description": "sshd: Attempt to login using a non-existent user",
        "dest_port": 22,
        "groups": ["syslog", "sshd", "authentication_failed"],
        "severity": "high",
        "category": "brute_force",
    },
    {
        "type": "wazuh",
        "rule_id": "5763",
        "rule_level": 10,
        "description": "sshd: Brute force attack - multiple authentication failures",
        "dest_port": 22,
        "groups": ["syslog", "sshd", "authentication_failures"],
        "severity": "critical",
        "category": "brute_force",
    },
    # Botnet / C2 alerts (Suricata)
    {
        "type": "suricata",
        "rule_id": "86610",
        "rule_level": 8,
        "description": "Suricata: Alert- ET TROJAN Possible Botnet C2 Channel Detected",
        "dest_port": 6667,
        "groups": ["ids", "suricata", "malware"],
        "severity": "critical",
        "category": "botnet",
    },
    {
        "type": "suricata",
        "rule_id": "86611",
        "rule_level": 7,
        "description": "Suricata: Alert- ET MALWARE Known Botnet Command Structure",
        "dest_port": 8443,
        "groups": ["ids", "suricata", "malware"],
        "severity": "critical",
        "category": "botnet",
    },
    # Web scanning
    {
        "type": "suricata",
        "rule_id": "86603",
        "rule_level": 3,
        "description": "Suricata: Alert- ET SCAN Nikto Web Scanner Activity",
        "dest_port": 80,
        "groups": ["ids", "suricata", "web"],
        "severity": "medium",
        "category": "web_scan",
    },
    # DDoS indicator
    {
        "type": "suricata",
        "rule_id": "86620",
        "rule_level": 9,
        "description": "Suricata: Alert- ET DOS Possible SYN Flood Attack Detected",
        "dest_port": 80,
        "groups": ["ids", "suricata", "dos"],
        "severity": "critical",
        "category": "ddos",
    },
    # Intrusion attempt
    {
        "type": "wazuh",
        "rule_id": "31101",
        "rule_level": 6,
        "description": "Web server 400 error code - Possible attack attempt",
        "dest_port": 443,
        "groups": ["web", "accesslog", "attack"],
        "severity": "medium",
        "category": "intrusion",
    },
]


def generate_alert() -> dict:
    """
    Generate a single realistic security alert.

    Returns a JSON structure matching the format shown in the paper's
    Table I and Box 1, including Wazuh metadata and Suricata event details.
    """
    template = random.choice(ALERT_TEMPLATES)
    src_ip = random.choice(ATTACKER_IPS)
    dest_ip = random.choice(TARGET_IPS)
    src_port = random.randint(1024, 65535)
    now = datetime.datetime.now(datetime.timezone.utc)

    alert = {
        "id": str(uuid.uuid4())[:12],
        "index": f"wazuh-alerts-4.x-{now.strftime('%Y.%m.%d')}",
        "timestamp": now.isoformat(),
        "rule": {
            "level": template["rule_level"],
            "description": template["description"],
            "id": template["rule_id"],
            "firedtimes": random.randint(1, 50),
            "groups": template["groups"],
        },
        "agent": {
            "id": f"00{random.randint(1, 3)}",
            "name": random.choice(["targetbox", "webserver", "dbserver"]),
            "ip": dest_ip,
        },
        "data": {
            "src_ip": src_ip,
            "src_port": str(src_port),
            "dest_ip": dest_ip,
            "dest_port": str(template["dest_port"]),
            "proto": "TCP",
        },
        "severity": template["severity"],
        "category": template["category"],
        "alert_type": template["type"],
    }

    return alert


def generate_alert_batch(count: int = 5) -> list[dict]:
    """Generate a batch of alerts."""
    return [generate_alert() for _ in range(count)]


# Predefined attack scenarios for demonstrations
ATTACK_SCENARIOS = {
    "port_scan": {
        "name": "Port Scanning Attack",
        "description": "Systematic port scanning targeting database services",
        "alerts_per_wave": 3,
        "interval_seconds": 5,
        "templates": [t for t in ALERT_TEMPLATES if t["category"] == "port_scan"],
    },
    "brute_force": {
        "name": "SSH Brute-Force Attack",
        "description": "Automated SSH login attempts with multiple credentials",
        "alerts_per_wave": 5,
        "interval_seconds": 3,
        "templates": [t for t in ALERT_TEMPLATES if t["category"] == "brute_force"],
    },
    "botnet": {
        "name": "Botnet Intrusion",
        "description": "Suspected botnet C2 communication detected",
        "alerts_per_wave": 2,
        "interval_seconds": 8,
        "templates": [t for t in ALERT_TEMPLATES if t["category"] == "botnet"],
    },
    "mixed": {
        "name": "Mixed Threat Scenario",
        "description": "Multiple simultaneous attack vectors",
        "alerts_per_wave": 4,
        "interval_seconds": 6,
        "templates": ALERT_TEMPLATES,
    },
}


def generate_scenario_alert(scenario_name: str = "mixed") -> dict:
    """Generate an alert from a specific attack scenario."""
    scenario = ATTACK_SCENARIOS.get(scenario_name, ATTACK_SCENARIOS["mixed"])
    template = random.choice(scenario["templates"])

    src_ip = random.choice(ATTACKER_IPS)
    dest_ip = random.choice(TARGET_IPS)
    src_port = random.randint(1024, 65535)
    now = datetime.datetime.now(datetime.timezone.utc)

    alert = {
        "id": str(uuid.uuid4())[:12],
        "index": f"wazuh-alerts-4.x-{now.strftime('%Y.%m.%d')}",
        "timestamp": now.isoformat(),
        "rule": {
            "level": template["rule_level"],
            "description": template["description"],
            "id": template["rule_id"],
            "firedtimes": random.randint(1, 50),
            "groups": template["groups"],
        },
        "agent": {
            "id": f"00{random.randint(1, 3)}",
            "name": random.choice(["targetbox", "webserver", "dbserver"]),
            "ip": dest_ip,
        },
        "data": {
            "src_ip": src_ip,
            "src_port": str(src_port),
            "dest_ip": dest_ip,
            "dest_port": str(template["dest_port"]),
            "proto": "TCP",
        },
        "severity": template["severity"],
        "category": template["category"],
        "alert_type": template["type"],
        "scenario": scenario_name,
    }

    return alert
