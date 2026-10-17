"""
Weather risk rules, route summaries and route recommendation.

Thresholds (base severity = MAX across wind / rain / snow):

| Condition | Low       | Moderate  | High      | Severe    | No Travel |
|-----------|-----------|-----------|-----------|-----------|-----------|
| Wind      | <25 mph   | 25-34     | 35-44     | 45-54     | >=55 mph  |
| Rain      | <0.10 in/h| 0.10-0.25 | 0.25-0.50 | 0.50-1.00 | >1.00     |
| Snow      | <0.5 in/h | 0.5-1.0   | 1.0-2.0   | 2.0-3.0   | >3.0      |

Boundary convention: a value equal to a shared boundary belongs to the higher
band (e.g. rain 0.25 -> High), except the No-Travel bands for rain/snow which
are strictly greater-than (rain 1.00 -> Severe, 1.01 -> No Travel).

Load rules (applied after the base level, can only upgrade):
  * wind >= 55 mph                    -> No Travel (any load)
  * wind 45-54 mph and load > 30,000  -> No Travel
  * wind 35-44 mph and load > 40,000  -> Severe
"""

LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = 1, 2, 3, 4, 5

LEVEL_LABELS = {
    LOW: "Low",
    MODERATE: "Moderate",
    HIGH: "High",
    SEVERE: "Severe",
    NO_TRAVEL: "No Travel",
}
LEVEL_KEYS = {
    LOW: "low",
    MODERATE: "moderate",
    HIGH: "high",
    SEVERE: "severe",
    NO_TRAVEL: "no_travel",
}


def wind_level(mph):
    if mph >= 55:
        return NO_TRAVEL
    if mph >= 45:
        return SEVERE
    if mph >= 35:
        return HIGH
    if mph >= 25:
        return MODERATE
    return LOW


def rain_level(in_per_hr):
    if in_per_hr > 1.00:
        return NO_TRAVEL
    if in_per_hr >= 0.50:
        return SEVERE
    if in_per_hr >= 0.25:
        return HIGH
    if in_per_hr >= 0.10:
        return MODERATE
    return LOW


def snow_level(in_per_hr):
    if in_per_hr > 3.0:
        return NO_TRAVEL
    if in_per_hr >= 2.0:
        return SEVERE
    if in_per_hr >= 1.0:
        return HIGH
    if in_per_hr >= 0.5:
        return MODERATE
    return LOW


def apply_load_rules(level, wind_mph, load_lb):
    """Upgrade `level` according to wind + load rules (never downgrades)."""
    if wind_mph >= 55:
        return NO_TRAVEL
    if 45 <= wind_mph < 55 and load_lb > 30_000:
        return max(level, NO_TRAVEL)
    if 35 <= wind_mph < 45 and load_lb > 40_000:
        return max(level, SEVERE)
    return level


def risk_level(wind_mph, rain_in_hr, snow_in_hr, load_lb):
    """Final integer risk level (1-5) for one set of conditions."""
    base = max(wind_level(wind_mph), rain_level(rain_in_hr), snow_level(snow_in_hr))
    return apply_load_rules(base, wind_mph, load_lb)


def assess(wind_mph, rain_in_hr, snow_in_hr, load_lb):
    """Full risk breakdown for a checkpoint (used for popups / debugging)."""
    factors = {
        "wind": wind_level(wind_mph),
        "rain": rain_level(rain_in_hr),
        "snow": snow_level(snow_in_hr),
    }
    base = max(factors.values())
    final = apply_load_rules(base, wind_mph, load_lb)

    drivers = [name for name, lvl in factors.items() if lvl == base and base > LOW]
    if final > base:
        reason = (
            f"Load rule: {wind_mph:.0f} mph wind with {load_lb:,.0f} lb load "
            f"upgrades {LEVEL_LABELS[base]} to {LEVEL_LABELS[final]}"
        )
    elif drivers:
        reason = f"Driven by {', '.join(drivers)}"
    else:
        reason = "Conditions within safe limits"

    return {
        "level": final,
        "label": LEVEL_LABELS[final],
        "base_level": base,
        "factors": {k: LEVEL_LABELS[v] for k, v in factors.items()},
        "load_adjusted": final > base,
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Route summary
# ---------------------------------------------------------------------------
def summarize_route(checkpoints, total_miles, total_duration_min):
    """
    Attribute route miles to risk levels.

    Each checkpoint "owns" the road nearest to it: half of the segment before
    it and half of the segment after it. So the miles always add up to
    total_miles and the final (often shorter) segment is weighted correctly.
    avg_risk_score is the mile-weighted mean of the 1-5 risk scores.
    """
    miles_by_level = {lvl: 0.0 for lvl in LEVEL_LABELS}
    n = len(checkpoints)
    for i, cp in enumerate(checkpoints):
        before = (cp["mile"] - checkpoints[i - 1]["mile"]) / 2 if i > 0 else 0.0
        after = (checkpoints[i + 1]["mile"] - cp["mile"]) / 2 if i < n - 1 else 0.0
        miles_by_level[cp["risk"]["level"]] += before + after

    covered = sum(miles_by_level.values()) or 1.0
    avg = sum(lvl * mi for lvl, mi in miles_by_level.items()) / covered
    worst = max(cp["risk"]["level"] for cp in checkpoints)

    summary = {f"{LEVEL_KEYS[lvl]}_miles": round(mi, 1) for lvl, mi in miles_by_level.items()}
    summary.update(
        {
            "severe_or_worse_miles": round(
                miles_by_level[SEVERE] + miles_by_level[NO_TRAVEL], 1
            ),
            "avg_risk_score": round(avg, 2),
            "max_risk_level": worst,
            "max_risk_label": LEVEL_LABELS[worst],
            "total_miles": round(total_miles, 1),
            "total_duration_min": round(total_duration_min, 1),
            "checkpoint_count": n,
        }
    )
    return summary


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------
# Priority order. Each tuple: (summary key, phrase used in the reason, formatter).
CRITERIA = [
    ("severe_or_worse_miles", "fewest Severe + No-Travel miles", lambda v: f"{v:g} mi"),
    ("high_miles", "fewest High-risk miles", lambda v: f"{v:g} mi"),
    ("avg_risk_score", "lowest average risk", lambda v: f"{v:.2f}"),
    ("total_duration_min", "shortest travel time", lambda v: f"{v / 60:.1f} h"),
]


def sort_key(route):
    s = route["summary"]
    return tuple(s[key] for key, _, _ in CRITERIA)


def recommend(routes):
    """
    Rank routes by the 4-step priority:
      1. fewest Severe + No-Travel miles
      2. fewest High miles
      3. lowest average risk score
      4. shortest travel time
    Returns (ranked route ids, best id, human-readable reason).
    """
    ranked = sorted(routes, key=sort_key)
    best = ranked[0]
    if len(ranked) == 1:
        return [best["id"]], best["id"], f"{best['name']} is the only route available."

    # The deciding step is the first criterion (in priority order) on which the
    # winner beats the runner-up; earlier steps are reported as ties. Only routes
    # still in contention at the deciding step are quoted for comparison.
    contenders, runner_up = ranked[1:], ranked[1]
    ties = []
    reason = f"{best['name']} selected: routes are equivalent on every criterion"
    for key, label, fmt in CRITERIA:
        best_val = best["summary"][key]
        if runner_up["summary"][key] == best_val:
            ties.append(f"{label.split(' ', 1)[1]} ({fmt(best_val)})")
            contenders = [r for r in contenders if r["summary"][key] == best_val]
            continue
        vs = " and ".join(fmt(r["summary"][key]) for r in contenders)
        reason = f"{best['name']} selected: {label} ({fmt(best_val)} vs {vs})"
        break
    if ties:
        reason += f". Tied with {runner_up['name']} on " + ", ".join(ties)
    return [r["id"] for r in ranked], best["id"], reason + "."
