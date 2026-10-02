"""MIRROR's deterministic world model, forecaster, and allocation optimiser.

The engine deliberately contains no LLM calls: every number rendered by the
interface is traceable to the rules below. A language model can safely be
added later as a presentation layer without influencing the calculation.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping


ZONES = ("A", "B", "C")
RESOURCE_TYPES = ("rescue_teams", "boats", "ambulances")


@dataclass(frozen=True)
class Scenario:
    disaster: str
    population: int
    rescue_teams: int
    boats: int
    ambulances: int
    hospitals: int
    roads_blocked: int
    weather_intensity: int

    @property
    def resources(self) -> Dict[str, int]:
        return {"rescue_teams": self.rescue_teams, "boats": self.boats, "ambulances": self.ambulances}


def _round(value: float) -> int:
    return int(value + 0.5)


def get_severity_status(severity: float) -> str:
    """Categorises severity into 4 operational color codes: Red, Orange, Yellow, Green."""
    if severity >= 80:
        return "RED"
    if severity >= 60:
        return "ORANGE"
    if severity >= 40:
        return "YELLOW"
    return "GREEN"


def build_world(s: Scenario) -> dict:
    """Create entities and initial state from the command panel inputs."""
    disaster_factor = {"Flood": 1.0, "Cyclone": 1.12, "Earthquake": 1.28, "Wildfire": 0.88}[s.disaster]
    risk_rate = min(0.48, 0.18 + s.weather_intensity * 0.019 + s.roads_blocked * 0.0018) * disaster_factor
    weights = {"A": 0.42, "B": 0.33, "C": 0.25}
    severity = {"A": 45, "B": 35, "C": 55}
    # A compact, legible proxy for a road-network model. Zone C becomes
    # increasingly isolated as the transport network is disrupted.
    accessibility = {"A": s.roads_blocked < 85, "B": s.roads_blocked < 60, "C": s.roads_blocked < 27}
    zones = {}
    for zone, weight in weights.items():
        pop = _round(s.population * weight)
        sev_val = min(95, severity[zone] + _round(s.weather_intensity * 2.4) + (12 if not accessibility[zone] else 0))
        zones[zone] = {
            "population": pop,
            "people_in_danger": _round(pop * risk_rate * (1.18 if zone == "C" else 1)),
            "severity": sev_val,
            "status": get_severity_status(sev_val),
            "road_access": accessibility[zone],
            "flood_depth": round(0.25 + s.weather_intensity * 0.12 + (0.35 if zone == "C" else 0), 1),
        }
    hospital_map = {}
    assignments = {"A": [], "B": [], "C": []}
    for index in range(s.hospitals):
        hospital_id = f"H{index + 1}"
        served = [ZONES[index % 3]]
        if s.hospitals == 1:
            served = list(ZONES)
        # Capacity is deliberately scaled to the city size so that a standard
        # demo reaches a warning-level load over several hours, not instantly.
        capacity = _round(600 + s.population / max(s.hospitals, 1) * 0.018)
        load = _round(capacity * (0.48 + s.weather_intensity * 0.025))
        hospital_map[hospital_id] = {"capacity": capacity, "load": min(capacity, load), "serves": served}
        for z in served:
            assignments[z].append(hospital_id)
    return {"zones": zones, "hospitals": hospital_map, "zone_hospitals": assignments}


def empty_allocation() -> dict:
    return {zone: {resource: 0 for resource in RESOURCE_TYPES} for zone in ZONES}


def allocation_totals(allocation: Mapping[str, Mapping[str, int]]) -> dict:
    return {resource: sum(allocation[zone].get(resource, 0) for zone in ZONES) for resource in RESOURCE_TYPES}


def validate_allocation(allocation: Mapping[str, Mapping[str, int]], resources: Mapping[str, int]) -> None:
    totals = allocation_totals(allocation)
    for resource, total in totals.items():
        if total > resources[resource]:
            raise ValueError(f"Allocation uses {total} {resource}, but only {resources[resource]} are available.")


def _marginal_score(zone: str, world: dict, allocation: dict, resource: str) -> float:
    z = world["zones"][zone]
    assigned = allocation[zone][resource]
    diminishing = 0.84 ** assigned
    urgency = (1 + z["severity"] / 100) * (1 + z["people_in_danger"] / max(1, z["population"]))
    if resource == "rescue_teams":
        return (42 if z["road_access"] else 0) * urgency * diminishing
    if resource == "boats":
        # Water access is particularly valuable where roads are unavailable.
        return 29 * urgency * (1.55 if not z["road_access"] else 1) * diminishing
    loads = [world["hospitals"][h]["load"] / world["hospitals"][h]["capacity"] for h in world["zone_hospitals"][zone]]
    return (18 * (sum(loads) / len(loads) if loads else 0.3) * urgency * diminishing) if z["road_access"] else 0


def optimise(world: dict, resources: Mapping[str, int]) -> dict:
    """Greedy marginal-benefit allocation, with a transparent objective."""
    allocation = empty_allocation()
    remaining = dict(resources)
    while any(remaining.values()):
        candidates = [
            (_marginal_score(zone, world, allocation, resource), zone, resource)
            for zone in ZONES for resource in RESOURCE_TYPES if remaining[resource] > 0
        ]
        score, zone, resource = max(candidates)
        if score <= 0:
            break
        allocation[zone][resource] += 1
        remaining[resource] -= 1
    return allocation


def manual_zone_share(world: dict, resources: Mapping[str, int], zone: str, share_pct: int) -> dict:
    """Reserve a share of each resource for a zone, then optimise the rest."""
    allocation = empty_allocation()
    remaining = dict(resources)
    for resource, total in resources.items():
        reserved = _round(total * share_pct / 100)
        allocation[zone][resource] = reserved
        remaining[resource] -= reserved
    rest = optimise(world, remaining)
    for z in ZONES:
        for r in RESOURCE_TYPES:
            allocation[z][r] += rest[z][r]
    return allocation


def simulate(world: dict, allocation: Mapping[str, Mapping[str, int]], hours: int = 12) -> List[dict]:
    """Forecast the state hour by hour under a fixed resource plan."""
    state = deepcopy(world)
    snapshots, cumulative = [], 0
    for hour in range(1, hours + 1):
        rescued_per_zone = {}
        for zone, z in state["zones"].items():
            plan = allocation[zone]
            ground = plan["rescue_teams"] * 42 if z["road_access"] else 0
            water = plan["boats"] * 29
            rescued = min(z["people_in_danger"], ground + water)
            rescued_per_zone[zone] = rescued
            z["people_in_danger"] -= rescued
            if rescued == 0 and z["people_in_danger"]:
                z["severity"] = min(100, z["severity"] + 3.5)
            else:
                z["severity"] = max(0, z["severity"] - rescued * 0.045)
            
            # Update live zone status code based on dynamic severity calculation
            z["status"] = get_severity_status(z["severity"])

        cumulative += sum(rescued_per_zone.values())
        for hospital_id, hospital in state["hospitals"].items():
            incoming = _round(sum(rescued_per_zone[z] for z in hospital["serves"]) * 0.24)
            ambulances = sum(allocation[z]["ambulances"] for z in hospital["serves"] if state["zones"][z]["road_access"])
            discharged = _round(hospital["load"] * 0.055) + ambulances * 6
            hospital["load"] = max(0, min(hospital["capacity"], hospital["load"] + incoming - discharged))
            
        zone_view = {z: {**data, "rescued_this_hour": rescued_per_zone[z]} for z, data in state["zones"].items()}
        hospital_view = {h: {**data, "load_percent": _round(100 * data["load"] / data["capacity"])} for h, data in state["hospitals"].items()}
        
        # Color & Evacuation Condition Classifications
        critical = [z for z, data in zone_view.items() if data["severity"] >= 80]
        strained = [z for z, data in zone_view.items() if 60 <= data["severity"] < 80]
        warning = [z for z, data in zone_view.items() if 40 <= data["severity"] < 60]
        stabilising = [z for z, data in zone_view.items() if data["severity"] < 40]

        # Evacuation flag: True if severity >= 80 (Red) or if severity >= 60 (Orange) with no road access
        evacuation_zones = [
            z for z, data in zone_view.items() 
            if data["severity"] >= 80 or (data["severity"] >= 60 and not data["road_access"])
        ]
        
        snapshots.append({
            "hour": hour,
            "cumulative_rescued": cumulative,
            "zones": deepcopy(zone_view),
            "hospitals": deepcopy(hospital_view),
            "critical_zones": critical,
            "strained_zones": strained,
            "warning_zones": warning,
            "stabilising_zones": stabilising,
            "evacuation_required": len(evacuation_zones) > 0,
            "evacuation_zones": evacuation_zones,
        })
    return snapshots


def plan_summary(world: dict, allocation: dict, forecast: List[dict]) -> List[str]:
    final = forecast[-1]
    highest = max(ZONES, key=lambda z: world["zones"][z]["severity"])
    constrained = [z for z in ZONES if not world["zones"][z]["road_access"]]
    hospital = max(final["hospitals"].items(), key=lambda item: item[1]["load_percent"])
    access_note = f"Zone {constrained[0]} is road-isolated, so boats are its primary lifeline." if constrained else "All zones retain road access for ground teams and ambulances."
    
    summary = [
        f"Prioritise Zone {highest}: it begins with the highest combined hazard and demand score.",
        access_note,
        f"At hour 12, {hospital[0]} is projected at {hospital[1]['load_percent']}% capacity; keep diversion and triage ready above 85%.",
    ]
    
    # Append evacuation warnings if active in forecast
    if final["evacuation_required"]:
        summary.append(f"⚠️ Evacuation Warning: Zone(s) {', '.join(final['evacuation_zones'])} require immediate relocation order.")
        
    return summary
