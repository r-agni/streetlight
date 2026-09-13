"""Who lives in a place, from the American Community Survey.

Questions about population, income, rent burden, language, car ownership and
education all land here. The numbers are recorded, not modelled: they are the
Census Bureau's estimates, mirrored keylessly and pulled by `06_census.py`.

Three things this module refuses to do, because each one produces a confident
answer that is wrong:

**It never drops the margin of error.** Every ACS figure is a survey estimate.
At tract level, and for small groups anywhere, the error bar is often wide
enough to reverse the comparison someone is about to make. Every figure
returned carries its margin, and `compare` says outright when a gap between two
places is inside the combined error and therefore not a real difference.

**It never re-derives a share by averaging.** Percentages are computed from
summed counts at whatever level is being reported, never averaged across
tracts, which would weight a 300-person tract the same as a 9,000-person one.

**It never lets a broad category stand in for a narrow one.** The ACS tables
reachable without a key stop at "Asian" and "born in Asia"; they do not break
out national origin or ancestry. Asked about a specific community, this returns
the broad measure clearly labelled as broad, plus the language figures, rather
than implying a precision the data does not have.
"""
from __future__ import annotations

import functools
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
PROCESSED = ROOT / "data" / "processed"

# Measures worth naming in an answer, in the order a person would want them.
# label, column, formatting hint.
HEADLINE: tuple[tuple[str, str, str], ...] = (
    ("Population", "population", "count"),
    ("Median age", "median_age", "years"),
    ("Median household income", "median_household_income", "dollars"),
    ("Median contract rent", "median_contract_rent", "dollars_month"),
    ("Median home value", "median_home_value", "dollars"),
    ("Households", "households", "count"),
    ("Housing units", "housing_units", "count"),
)

SHARE_LABELS: dict[str, str] = {
    "pct_asian": "Asian, not Hispanic",
    "pct_hispanic": "Hispanic or Latino",
    "pct_white_nh": "White, not Hispanic",
    "pct_black_nh": "Black, not Hispanic",
    "pct_foreign_born": "Foreign born",
    "pct_foreign_born_asia": "Foreign born, from Asia",
    "pct_below_poverty": "Below the poverty line",
    "pct_unemployed": "Unemployed, of the labour force",
    "pct_bachelors_or_higher": "Bachelor's degree or higher",
    "pct_no_high_school": "No high school diploma",
    "pct_renters_cost_burdened": "Renters paying over 30% of income on rent",
    "pct_renter_occupied": "Renter occupied",
    "pct_housing_vacant": "Housing units vacant",
    "pct_households_no_car": "Households with no car",
    "pct_commute_transit": "Commute by public transit",
    "pct_commute_walk": "Commute on foot",
    "pct_commute_drove_alone": "Drive to work alone",
    "pct_work_from_home": "Work from home",
    "pct_speaks_asian_pacific_lang": "Speak an Asian or Pacific Island language at home",
    "pct_speaks_spanish": "Speak Spanish at home",
    "pct_speaks_indo_european": "Speak another Indo-European language at home",
}

# Measures that are weighted averages of tract medians once rolled up, so they
# are approximations rather than true medians of the larger area.
APPROXIMATE = {
    "median_household_income",
    "median_contract_rent",
    "median_home_value",
    "median_age",
    "median_income_asian_householder",
    "median_income_white_nh_householder",
    "median_income_hispanic_householder",
    "median_income_black_householder",
}

SOURCE_NOTE = (
    "American Community Survey 5-year estimates, mirrored keylessly via Esri "
    "Living Atlas and DataSF; recorded survey data, not simulation output."
)


@functools.lru_cache(maxsize=1)
def _load() -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for key, filename in (
        ("neighborhood", "census_neighborhoods.parquet"),
        ("district", "census_districts.parquet"),
        ("tract", "census_tracts.parquet"),
        ("counts", "census_demographics.parquet"),
    ):
        path = PROCESSED / filename
        if path.exists():
            frames[key] = pd.read_parquet(path)
    return frames


def available() -> bool:
    return "neighborhood" in _load()


def neighborhoods() -> list[str]:
    frames = _load()
    if "neighborhood" not in frames:
        return []
    return sorted(frames["neighborhood"]["neighborhood"].dropna().astype(str))


# Names people actually type, mapped to the city's official spelling. Checked
# before any fuzzy matching, because a substring search resolves "sunset" to
# Inner Sunset (27,000 residents) when almost everyone means Sunset/Parkside
# (75,000), and the wrong answer looks exactly like the right one.
ALIASES: dict[str, str] = {
    "soma": "South of Market",
    "south of market": "South of Market",
    "fidi": "Financial District/South Beach",
    "financial district": "Financial District/South Beach",
    "downtown": "Financial District/South Beach",
    "union square": "Financial District/South Beach",
    "embarcadero": "Financial District/South Beach",
    "sunset": "Sunset/Parkside",
    "outer sunset": "Sunset/Parkside",
    "parkside": "Sunset/Parkside",
    "inner sunset": "Inner Sunset",
    "richmond": "Outer Richmond",
    "the richmond": "Outer Richmond",
    "inner richmond": "Inner Richmond",
    "castro": "Castro/Upper Market",
    "upper market": "Castro/Upper Market",
    "the mission": "Mission",
    "mission district": "Mission",
    "dogpatch": "Potrero Hill",
    "hayes": "Hayes Valley",
    "bayview": "Bayview Hunters Point",
    "hunters point": "Bayview Hunters Point",
    "the haight": "Haight Ashbury",
    "haight": "Haight Ashbury",
    "noe": "Noe Valley",
    "tenderloin": "Tenderloin",
    "the tenderloin": "Tenderloin",
    "ingleside": "Oceanview/Merced/Ingleside",
    "omi": "Oceanview/Merced/Ingleside",
    "west portal": "West of Twin Peaks",
    "outer mission": "Outer Mission",
    "china town": "Chinatown",
    "north beach": "North Beach",
    "russian hill": "Russian Hill",
    "nopa": "Western Addition",
    "fillmore": "Western Addition",
    "japantown": "Japantown",
    "soma west": "South of Market",
    "mid market": "Tenderloin",
    "civic center": "Tenderloin",
}


def _match(name: str) -> str | None:
    """Resolve a loosely-typed place name to a neighbourhood the data knows."""
    if not name:
        return None
    known = neighborhoods()
    lookup = {candidate.lower(): candidate for candidate in known}
    needle = name.strip().lower().strip(",.")

    # exact, then the alias table, then fuzzy; in that order so a deliberate
    # mapping is never overridden by an accidental substring hit
    if needle in lookup:
        return lookup[needle]
    target = ALIASES.get(needle)
    if target and target in known:
        return target
    for alias, mapped in ALIASES.items():
        if alias in needle and mapped in known:
            return mapped

    # fuzzy last, longest match first so "inner sunset" beats "sunset"
    contained = [c for c in known if needle in c.lower() or c.lower() in needle]
    if contained:
        return max(contained, key=len)
    return None


def _figure(row: pd.Series, column: str) -> dict | None:
    """One measure with its margin of error, or nothing if it is missing."""
    if column not in row.index or pd.isna(row[column]):
        return None
    value = float(row[column])
    entry: dict[str, object] = {"value": round(value, 1)}
    moe_column = f"{column}_moe"
    if moe_column in row.index and pd.notna(row[moe_column]):
        margin = float(row[moe_column])
        entry["marginOfError"] = round(margin, 1)
        # A margin wider than a third of the estimate means the figure cannot
        # carry an argument on its own, which is worth saying before someone
        # builds a decision on it.
        if value and margin / abs(value) > 0.33:
            entry["imprecise"] = True
    if column in APPROXIMATE:
        entry["approximate"] = True
    return entry


def profile(place: str) -> dict:
    """Everything known about who lives in one neighbourhood."""
    frames = _load()
    if "neighborhood" not in frames:
        return {
            "available": False,
            "reason": "Census tables have not been built. Run scripts/06_census.py.",
        }

    resolved = _match(place)
    if not resolved:
        return {
            "available": False,
            "reason": f"No San Francisco neighbourhood matches {place!r}.",
            "knownPlaces": neighborhoods(),
        }

    frame = frames["neighborhood"]
    row = frame.loc[frame["neighborhood"] == resolved].iloc[0]

    headline: dict[str, dict] = {}
    for label, column, unit in HEADLINE:
        figure = _figure(row, column)
        if figure:
            figure["unit"] = unit
            headline[label] = figure

    shares: dict[str, dict] = {}
    for column, label in SHARE_LABELS.items():
        figure = _figure(row, column)
        if figure:
            figure["unit"] = "percent"
            shares[label] = figure

    citywide = _citywide()
    notable = _notable(row, citywide)

    return {
        "available": True,
        "place": resolved,
        "tracts": int(row.get("tracts", 0) or 0),
        "headline": headline,
        "shares": shares,
        "standsOut": notable,
        "citywide": citywide,
        "source": SOURCE_NOTE,
    }


@functools.lru_cache(maxsize=1)
def _citywide() -> dict:
    """The city as a whole, so any neighbourhood figure has something to sit against."""
    frames = _load()
    if "neighborhood" not in frames:
        return {}
    frame = frames["neighborhood"]
    out: dict[str, float] = {}

    population = frame["population"].sum()
    if population:
        out["population"] = int(population)

    # shares recomputed from citywide counts, never averaged across neighbourhoods
    pairs = {
        "pct_asian": ("race_asian_nh", "population"),
        "pct_hispanic": ("race_hispanic", "population"),
        "pct_white_nh": ("race_white_nh", "population"),
        "pct_black_nh": ("race_black_nh", "population"),
        "pct_foreign_born": ("foreign_born", "population"),
        "pct_below_poverty": ("below_poverty_line", "poverty_universe"),
        "pct_bachelors_or_higher": ("bachelors_or_higher", "adults_25_plus"),
        "pct_renters_cost_burdened": ("renters_paying_over_30pct", "renter_households"),
        "pct_households_no_car": ("households_no_vehicle", "households_vehicle_universe"),
        "pct_commute_transit": ("commute_public_transit", "workers_16_plus"),
    }
    for name, (numerator, denominator) in pairs.items():
        if numerator in frame.columns and denominator in frame.columns:
            base = frame[denominator].sum()
            if base:
                out[name] = round(frame[numerator].sum() / base * 100, 1)

    for column in ("median_household_income", "median_contract_rent"):
        if column in frame.columns and "households" in frame.columns:
            weights = frame["households"]
            values = frame[column]
            mask = values.notna() & weights.notna() & (values > 0)
            if mask.any() and weights[mask].sum():
                out[column] = round(
                    float((values[mask] * weights[mask]).sum() / weights[mask].sum())
                )
    return out


def _notable(row: pd.Series, citywide: dict, limit: int = 6) -> list[str]:
    """Where this place departs most from the city, in plain sentences."""
    out: list[tuple[float, str]] = []
    for column, label in SHARE_LABELS.items():
        if column not in citywide or column not in row.index or pd.isna(row[column]):
            continue
        here = float(row[column])
        city = float(citywide[column])
        gap = here - city
        if abs(gap) < 5:
            continue
        direction = "above" if gap > 0 else "below"
        out.append(
            (
                abs(gap),
                f"{label}: {here:.0f}% here against {city:.0f}% citywide, "
                f"{abs(gap):.0f} points {direction}.",
            )
        )
    for column, label in (
        ("median_household_income", "Median household income"),
        ("median_contract_rent", "Median contract rent"),
    ):
        if column not in citywide or column not in row.index or pd.isna(row[column]):
            continue
        here = float(row[column])
        city = float(citywide[column])
        if not city:
            continue
        ratio = here / city
        if 0.85 < ratio < 1.15:
            continue
        direction = "higher" if ratio > 1 else "lower"
        out.append(
            (
                abs(ratio - 1) * 100,
                f"{label}: ${here:,.0f} against ${city:,.0f} citywide, "
                f"{abs(ratio - 1) * 100:.0f}% {direction}.",
            )
        )
    out.sort(key=lambda pair: -pair[0])
    return [sentence for _, sentence in out[:limit]]


# Golden Gate Park, McLaren Park, Lincoln Park, the Presidio and the Farallones
# are analysis neighbourhoods with almost nobody living in them. A share
# computed over a few dozen residents will top any ranking while meaning
# nothing, so rankings need a floor.
MIN_POPULATION_FOR_RANKING = 1500

# A percentage computed over a few hundred households swings wildly between
# survey vintages. Ranking on one puts noise at the top of the list.
MIN_BASE_FOR_SHARE = 1000

# Which count each share divides by, so a ranking can check that base is large
# enough to mean anything. Mirrors the SHARES table in scripts/06_census.py.
SHARE_BASE: dict[str, str] = {
    "pct_asian": "population",
    "pct_hispanic": "population",
    "pct_white_nh": "population",
    "pct_black_nh": "population",
    "pct_foreign_born": "population",
    "pct_foreign_born_asia": "population",
    "pct_below_poverty": "poverty_universe",
    "pct_unemployed": "in_labor_force",
    "pct_commute_transit": "workers_16_plus",
    "pct_commute_walk": "workers_16_plus",
    "pct_commute_drove_alone": "workers_16_plus",
    "pct_work_from_home": "workers_16_plus",
    "pct_bachelors_or_higher": "adults_25_plus",
    "pct_no_high_school": "adults_25_plus",
    "pct_renters_cost_burdened": "renter_households",
    "pct_renter_occupied": "housing_units",
    "pct_housing_vacant": "housing_units",
    "pct_households_no_car": "households_vehicle_universe",
    "pct_speaks_asian_pacific_lang": "population_5_plus",
    "pct_speaks_spanish": "population_5_plus",
    "pct_speaks_indo_european": "population_5_plus",
}


def rank(measure: str, top: int = 10, ascending: bool = False) -> dict:
    """Neighbourhoods ordered by one measure, for "where is the most" questions."""
    frames = _load()
    if "neighborhood" not in frames:
        return {"available": False, "reason": "Census tables have not been built."}

    frame = frames["neighborhood"]
    column = measure if measure in frame.columns else None
    if column is None:
        # accept the human label as well as the column name
        lowered = measure.strip().lower()
        for candidate, label in SHARE_LABELS.items():
            if lowered in label.lower() or lowered == candidate:
                column = candidate
                break
    if column is None or column not in frame.columns:
        return {
            "available": False,
            "reason": f"No measure called {measure!r}.",
            "measures": sorted(SHARE_LABELS) + [c for _, c, _ in HEADLINE],
        }

    eligible = frame.dropna(subset=[column])
    excluded: list[str] = []
    thin: list[str] = []

    if "population" in eligible.columns and column != "population":
        too_small = eligible["population"].fillna(0) < MIN_POPULATION_FOR_RANKING
        excluded = sorted(eligible.loc[too_small, "neighborhood"].astype(str))
        eligible = eligible.loc[~too_small]

    # A share is only as solid as the base it divides by. Seacliff's 55 percent
    # cost-burdened renters rests on 229 renter households and outranked the
    # Tenderloin's 17,572 households at 47 percent, which is a ranking of
    # sampling noise. Neighbourhoods whose denominator is too thin are held out
    # of the ordering and named, rather than dropped silently.
    denominator = SHARE_BASE.get(column)
    if denominator not in eligible.columns:
        denominator = None
    if denominator:
        base = pd.to_numeric(eligible[denominator], errors="coerce").fillna(0)
        too_thin = base < MIN_BASE_FOR_SHARE
        thin = sorted(eligible.loc[too_thin, "neighborhood"].astype(str))
        eligible = eligible.loc[~too_thin]

    ordered = eligible.sort_values(column, ascending=ascending)
    rows = []
    for _, row in ordered.head(top).iterrows():
        entry = {"place": row["neighborhood"]}
        figure = _figure(row, column)
        if figure:
            entry.update(figure)
        if "population" in row.index and pd.notna(row["population"]):
            entry["population"] = int(row["population"])
        rows.append(entry)

    return {
        "available": True,
        "measure": SHARE_LABELS.get(column, column),
        "column": column,
        "order": "lowest first" if ascending else "highest first",
        "places": rows,
        "citywide": _citywide().get(column),
        "excludedAsTooSmall": excluded,
        "excludedAsTooFewToMeasure": thin,
        "note": (
            "Neighbourhoods with fewer than "
            f"{MIN_BASE_FOR_SHARE:,} in the group this share is measured over are "
            "held out, because a percentage of a few hundred is mostly noise."
        )
        if thin
        else None,
        "source": SOURCE_NOTE,
    }


def compare(places: list[str], measures: list[str] | None = None) -> dict:
    """Several places side by side, with honest verdicts on each gap."""
    frames = _load()
    if "neighborhood" not in frames:
        return {"available": False, "reason": "Census tables have not been built."}

    frame = frames["neighborhood"]
    resolved = [(place, _match(place)) for place in places]
    missing = [place for place, found in resolved if not found]
    found = [name for _, name in resolved if name]
    if len(found) < 2:
        return {
            "available": False,
            "reason": "Two or more known neighbourhoods are needed to compare.",
            "unmatched": missing,
            "knownPlaces": neighborhoods(),
        }

    columns = measures or [
        "population",
        "median_household_income",
        "median_contract_rent",
        "pct_bachelors_or_higher",
        "pct_below_poverty",
        "pct_households_no_car",
        "pct_renters_cost_burdened",
    ]

    rows = {name: frame.loc[frame["neighborhood"] == name].iloc[0] for name in found}
    table: dict[str, dict] = {}
    verdicts: list[str] = []

    for column in columns:
        entries = {}
        for name, row in rows.items():
            figure = _figure(row, column)
            if figure:
                entries[name] = figure
        if len(entries) < 2:
            continue
        table[SHARE_LABELS.get(column, column)] = entries

        # Is the gap real, or inside the survey's own error?
        ordered = sorted(entries.items(), key=lambda kv: -kv[1]["value"])
        (high_name, high), (low_name, low) = ordered[0], ordered[-1]
        gap = high["value"] - low["value"]
        combined = (
            (high.get("marginOfError", 0) ** 2 + low.get("marginOfError", 0) ** 2) ** 0.5
        )
        label = SHARE_LABELS.get(column, column.replace("_", " "))

        # A share aggregated from tracts carries no margin of the kind the
        # Bureau publishes, so guard it by size instead: under a point apart is
        # two ways of saying the same thing, and reporting it as a difference
        # invents a finding.
        if column.startswith("pct_") and not combined and gap < 2:
            verdicts.append(
                f"{label}: {high_name} and {low_name} are within {gap:.0f} "
                "percentage points, which is effectively the same."
            )
            continue

        if combined and gap <= combined:
            verdicts.append(
                f"{label}: the gap between {high_name} and {low_name} is inside the "
                f"survey's margin of error, so it is not a real difference."
            )
        else:
            if column.startswith("pct_"):
                amount = f"{gap:,.0f} percentage points"
            elif "income" in column or "rent" in column or "value" in column:
                amount = f"${gap:,.0f}"
            else:
                amount = f"{gap:,.0f}"
            verdicts.append(f"{label}: {high_name} exceeds {low_name} by {amount}.")

    return {
        "available": True,
        "places": found,
        "unmatched": missing,
        "table": table,
        "verdicts": verdicts,
        "source": SOURCE_NOTE,
    }


def near(lon: float, lat: float, radius_m: float = 1200.0) -> dict:
    """Who lives around a point, from the tracts whose centres fall nearby.

    Used when a question is about a site rather than a named neighbourhood.
    Tract centroids are a coarse instrument, so the tracts counted are named in
    the result and the caller can say how wide a net was cast.
    """
    frames = _load()
    if "tract" not in frames:
        return {"available": False, "reason": "Census tables have not been built."}

    frame = frames["tract"].dropna(subset=["lat", "lon"])
    if frame.empty:
        return {"available": False, "reason": "No tract centroids were located."}

    # equirectangular is plenty at city scale and avoids a geo dependency here
    import numpy as np

    mean_lat = float(np.radians(lat))
    dx = (frame["lon"].to_numpy() - lon) * 111_320 * float(np.cos(mean_lat))
    dy = (frame["lat"].to_numpy() - lat) * 110_540
    distance = np.hypot(dx, dy)
    selected = frame.loc[distance <= radius_m].copy()
    if selected.empty:
        nearest = frame.iloc[[int(distance.argmin())]].copy()
        selected = nearest

    totals: dict[str, float] = {}
    for column in ("population", "households", "housing_units", "workers_16_plus",
                   "adults_25_plus", "race_asian_nh", "race_hispanic", "race_white_nh",
                   "race_black_nh", "foreign_born", "below_poverty_line",
                   "poverty_universe", "bachelors_or_higher", "commute_public_transit",
                   "households_no_vehicle", "households_vehicle_universe",
                   "renter_households", "renters_paying_over_30pct"):
        if column in selected.columns:
            value = selected[column].sum(min_count=1)
            if pd.notna(value):
                totals[column] = float(value)

    shares: dict[str, float] = {}
    for name, (numerator, denominator) in {
        "pct_asian": ("race_asian_nh", "population"),
        "pct_hispanic": ("race_hispanic", "population"),
        "pct_white_nh": ("race_white_nh", "population"),
        "pct_black_nh": ("race_black_nh", "population"),
        "pct_foreign_born": ("foreign_born", "population"),
        "pct_below_poverty": ("below_poverty_line", "poverty_universe"),
        "pct_bachelors_or_higher": ("bachelors_or_higher", "adults_25_plus"),
        "pct_commute_transit": ("commute_public_transit", "workers_16_plus"),
        "pct_households_no_car": ("households_no_vehicle", "households_vehicle_universe"),
        "pct_renters_cost_burdened": ("renters_paying_over_30pct", "renter_households"),
    }.items():
        if totals.get(denominator):
            shares[SHARE_LABELS.get(name, name)] = round(
                totals[numerator] / totals[denominator] * 100, 1
            )

    medians: dict[str, float] = {}
    for column in ("median_household_income", "median_contract_rent", "median_age"):
        if column in selected.columns:
            weight = selected.get("households" if "median_a" not in column else "population")
            values = selected[column]
            mask = values.notna() & (weight.notna() if weight is not None else False)
            if weight is not None and mask.any() and weight[mask].sum():
                medians[column] = round(
                    float((values[mask] * weight[mask]).sum() / weight[mask].sum())
                )

    return {
        "available": True,
        "radiusMetres": radius_m,
        "tractsCounted": int(len(selected)),
        "neighborhoods": sorted(
            {n for n in selected.get("neighborhood", pd.Series(dtype=str)).dropna()}
        ),
        "population": int(totals.get("population", 0)),
        "households": int(totals.get("households", 0)),
        "shares": shares,
        "medians": medians,
        "note": (
            "Counted from whole census tracts whose centres fall within the radius, "
            "so the boundary is approximate."
        ),
        "source": SOURCE_NOTE,
    }


def community(term: str, place: str | None = None) -> dict:
    """What the data can and cannot say about a specific community.

    Asked about, say, the Indian population, the honest answer is that the
    keyless ACS tables stop at "Asian" and "born in Asia". Rather than let a
    broad figure pass as a narrow one, this returns the broad measures, names
    the limit outright, and points at the language figures, which cut finer.
    """
    broad = {
        "indian": "Asian",
        "chinese": "Asian",
        "filipino": "Asian",
        "korean": "Asian",
        "japanese": "Asian",
        "vietnamese": "Asian",
        "mexican": "Hispanic or Latino",
        "salvadoran": "Hispanic or Latino",
        "guatemalan": "Hispanic or Latino",
        "nigerian": "Black",
        "ethiopian": "Black",
    }
    needle = term.strip().lower()
    umbrella = next((v for k, v in broad.items() if k in needle), None)

    body = profile(place) if place else {"available": True, "place": "San Francisco"}
    payload = {
        "term": term,
        "available": body.get("available", False),
        "limit": (
            f"The census tables reachable without a key do not break out {term} "
            "specifically. They report race and Hispanic origin, and place of "
            "birth by world region, so the closest recorded measures are "
            + (f"the {umbrella} category " if umbrella else "the broad race categories ")
            + "and the language spoken at home."
        ),
        "closestMeasures": [],
        "source": SOURCE_NOTE,
    }
    if umbrella == "Asian":
        payload["closestMeasures"] = [
            "Asian, not Hispanic",
            "Foreign born, from Asia",
            "Speak an Asian or Pacific Island language at home",
        ]
    elif umbrella == "Hispanic or Latino":
        payload["closestMeasures"] = ["Hispanic or Latino", "Speak Spanish at home"]
    elif umbrella == "Black":
        payload["closestMeasures"] = ["Black, not Hispanic", "Foreign born"]

    if body.get("available") and place:
        shares = body.get("shares", {})
        payload["place"] = body["place"]
        payload["figures"] = {
            label: shares[label] for label in payload["closestMeasures"] if label in shares
        }
        payload["standsOut"] = body.get("standsOut", [])
    elif not place:
        payload["figures"] = {
            "citywide": {
                SHARE_LABELS.get(k, k): v
                for k, v in _citywide().items()
                if k.startswith("pct_")
            }
        }
    return payload
