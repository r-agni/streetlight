#!/usr/bin/env python
"""Pull San Francisco population and demographic data.

Who lives where, from the American Community Survey, without needing a key.

The Census Bureau's own API began rejecting unauthenticated requests, which
left the demographics side of this project dead. Two keyless mirrors replace
it, and between them they cover more than the raw API did:

  * San Francisco's open data portal (4qbq-hvtt) publishes ACS counts already
    aggregated to the city's 42 analysis neighbourhoods, which is how the rest
    of this product addresses places. It also carries a reliability flag the
    city computed itself.
  * Esri's Living Atlas mirrors the full ACS tables at tract level, with the
    real table codes and a margin of error beside every estimate. That is where
    income, rent, education, commute mode, poverty and tenure come from, none
    of which the city's own table has.

Every estimate keeps its margin of error. A tract-level count of a small group
carries an error bar wide enough to reverse the comparison someone was about to
make, so an answer that quotes the estimate alone is worse than no answer.

Tracts are joined to neighbourhoods and supervisor districts through the city's
own crosswalk, so a tract-level ACS figure can be rolled up to the same place
names the assistant, the map and the site scores already use.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed"

PORTAL = "https://data.sf.gov/resource/4qbq-hvtt.json"
CROSSWALK = "https://data.sf.gov/resource/sevw-6tgi.json"
TIGERWEB = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "Tracts_Blocks/MapServer/0/query"
)
LIVING_ATLAS = "https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services"
PAGE = 50_000

# Which ACS variables to lift out of each Living Atlas layer, and what to call
# them. Chosen for the questions this product is actually asked: who lives
# here, what they earn, what they pay, how they get to work, and how much of
# that the data is willing to stand behind. Each estimate field has a matching
# margin-of-error field ending in M, pulled automatically.
LAYERS: dict[str, dict[str, str]] = {
    "ACS_Median_Income_by_Race_and_Age_Selp_Emp_Boundaries": {
        "B19049_001E": "median_household_income",
        "B19013D_001E": "median_income_asian_householder",
        "B19013H_001E": "median_income_white_nh_householder",
        "B19013I_001E": "median_income_hispanic_householder",
        "B19013B_001E": "median_income_black_householder",
        "B19053_001E": "households",
    },
    "ACS_Total_Population_Boundaries": {
        "B01001_001E": "population",
        "B01001_002E": "population_male",
        "B01001_026E": "population_female",
    },
    "ACS_Median_Age_Boundaries": {
        "B01002_001E": "median_age",
    },
    "ACS_Population_by_Race_and_Hispanic_Origin_Boundaries": {
        "B03002_003E": "race_white_nh",
        "B03002_004E": "race_black_nh",
        "B03002_006E": "race_asian_nh",
        "B03002_005E": "race_native_nh",
        "B03002_007E": "race_pacific_nh",
        "B03002_009E": "race_two_or_more_nh",
        "B03002_012E": "race_hispanic",
    },
    "ACS_Highlights_Population_Housing_Basics_Boundaries": {
        "B25058_001E": "median_contract_rent",
        "B25077_001E": "median_home_value",
        "B25002_001E": "housing_units",
        "B25002_003E": "vacant_housing_units",
        "B25003_002E": "owner_occupied_units",
        "B25003_003E": "renter_occupied_units",
    },
    "ACS_Housing_Costs_Boundaries": {
        "B25070_001E": "renter_households",
        "B25070_calc_numGE30pctE": "renters_paying_over_30pct",
        "B25091_001E": "owner_households",
        "B25091_calc_numMortGE30pctE": "owners_with_mortgage_over_30pct",
    },
    "ACS_Educational_Attainment_Boundaries": {
        "B15002_001E": "adults_25_plus",
        "B15002_calc_numGEBAE": "bachelors_or_higher",
        "B15002_calc_numLTHSE": "less_than_high_school",
    },
    "ACS_Poverty_by_Age_Boundaries": {
        "B17020_001E": "poverty_universe",
        "B17020_002E": "below_poverty_line",
    },
    "ACS_Employment_Status_Boundaries": {
        "B23025_002E": "in_labor_force",
        "B23025_005E": "unemployed",
    },
    "ACS_Means_of_Transportation_to_Work_Boundaries": {
        "B08301_001E": "workers_16_plus",
        "B08301_003E": "commute_drove_alone",
        "B08301_010E": "commute_public_transit",
        "B08301_019E": "commute_walked",
        "B08301_021E": "commute_worked_from_home",
    },
    "ACS_Place_of_Birth_Boundaries": {
        "B05002_013E": "foreign_born",
        "B05002_calc_numAsiaE": "foreign_born_asia",
    },
    "ACS_Language_by_Age_Boundaries": {
        "B16007_001E": "population_5_plus",
        "B16007_010E": "speaks_spanish_18_to_64",
        "B16007_011E": "speaks_indo_european_18_to_64",
        "B16007_012E": "speaks_asian_pacific_18_to_64",
    },
    "ACS_Vehicle_Availability_Boundaries": {
        "B08201_001E": "households_vehicle_universe",
        "B08201_002E": "households_no_vehicle",
    },
}


# Derived shares, as (numerator, denominator, name). Defined once and applied
# both to tracts and to anything rolled up from them. A share must always be
# recomputed from summed counts, never averaged or summed across tracts, or a
# neighbourhood ends up reported as 475 percent Asian.
SHARES: tuple[tuple[str, str, str], ...] = (
    ("race_asian_nh", "population", "pct_asian"),
    ("race_hispanic", "population", "pct_hispanic"),
    ("race_white_nh", "population", "pct_white_nh"),
    ("race_black_nh", "population", "pct_black_nh"),
    ("foreign_born", "population", "pct_foreign_born"),
    ("foreign_born_asia", "population", "pct_foreign_born_asia"),
    ("below_poverty_line", "poverty_universe", "pct_below_poverty"),
    ("unemployed", "in_labor_force", "pct_unemployed"),
    ("commute_public_transit", "workers_16_plus", "pct_commute_transit"),
    ("commute_walked", "workers_16_plus", "pct_commute_walk"),
    ("commute_drove_alone", "workers_16_plus", "pct_commute_drove_alone"),
    ("commute_worked_from_home", "workers_16_plus", "pct_work_from_home"),
    ("bachelors_or_higher", "adults_25_plus", "pct_bachelors_or_higher"),
    ("less_than_high_school", "adults_25_plus", "pct_no_high_school"),
    ("renters_paying_over_30pct", "renter_households", "pct_renters_cost_burdened"),
    ("vacant_housing_units", "housing_units", "pct_housing_vacant"),
    ("renter_occupied_units", "housing_units", "pct_renter_occupied"),
    ("households_no_vehicle", "households_vehicle_universe", "pct_households_no_car"),
    ("speaks_asian_pacific_18_to_64", "population_5_plus", "pct_speaks_asian_pacific_lang"),
    ("speaks_spanish_18_to_64", "population_5_plus", "pct_speaks_spanish"),
    ("speaks_indo_european_18_to_64", "population_5_plus", "pct_speaks_indo_european"),
)


def add_shares(df: pd.DataFrame) -> pd.DataFrame:
    """Attach every derived share, computed from counts present in df."""
    for numerator, denominator, name in SHARES:
        if numerator in df.columns and denominator in df.columns:
            base = pd.to_numeric(df[denominator], errors="coerce").replace(0, pd.NA)
            top = pd.to_numeric(df[numerator], errors="coerce")
            df[name] = (top / base * 100).astype("Float64").round(1)
    return df


# --------------------------------------------------------------------------
# the city's own table: counts already rolled up to neighbourhoods
# --------------------------------------------------------------------------

def fetch_portal_counts(client, geographies: tuple[str, ...]) -> pd.DataFrame:
    """Population counts by age and race, at tract and neighbourhood."""
    where = " OR ".join(f"geography='{g}'" for g in geographies)
    frames: list[pd.DataFrame] = []
    offset = 0
    while True:
        response = client.get(
            PORTAL,
            params={"$where": where, "$limit": PAGE, "$offset": offset, "$order": ":id"},
            timeout=180,
        )
        response.raise_for_status()
        rows = response.json()
        if not rows:
            break
        frames.append(pd.DataFrame(rows))
        print(f"    {offset + len(rows):,} rows", flush=True)
        if len(rows) < PAGE:
            break
        offset += PAGE
        time.sleep(0.2)
    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    keep = {
        "geography": "geography",
        "geography_id": "geography_id",
        "geography_name": "area",
        "demographic_category": "category",
        "demographic_category_label": "label",
        "estimate": "estimate",
        "moe": "margin_of_error",
        "reliable": "reliable",
        "unit": "unit",
        "end_year": "end_year",
        "source": "source",
        "min_age": "min_age",
        "max_age": "max_age",
    }
    present = {src: dst for src, dst in keep.items() if src in df.columns}
    out = df[list(present)].rename(columns=present)
    for column in ("estimate", "margin_of_error", "end_year", "min_age", "max_age"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    out["reliable"] = out.get("reliable", "true").astype(str).str.lower().isin(("true", "1"))

    # the table stacks several overlapping five-year windows; keep the newest
    out = out.sort_values("end_year")
    subset = [c for c in ("geography", "geography_id", "area", "category", "label") if c in out]
    return out.drop_duplicates(subset=subset, keep="last").reset_index(drop=True)


# --------------------------------------------------------------------------
# Living Atlas: the ACS tables the city's table does not carry
# --------------------------------------------------------------------------

def fetch_layer(client, service: str, fields: dict[str, str]) -> pd.DataFrame:
    """One Living Atlas layer, San Francisco tracts only, estimates and errors."""
    wanted = ["GEOID", "NAME"]
    for code in fields:
        wanted.append(code)
        wanted.append(code[:-1] + "M")  # matching margin of error

    # The service caps a page at 50 features regardless of what we ask for, so
    # this pages until it stops returning any. Without it only a fifth of the
    # city came back, which is worse than nothing: partial coverage silently
    # understates every citywide total.
    rows: list[dict] = []
    offset = 0
    while True:
        response = client.get(
            f"{LIVING_ATLAS}/{service}/FeatureServer/2/query",
            params={
                "where": "GEOID LIKE '06075%'",
                "outFields": ",".join(wanted),
                "returnGeometry": "false",
                "f": "json",
                "resultRecordCount": 1000,
                "resultOffset": offset,
            },
            timeout=180,
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            print(f"    {service}: {payload['error'].get('message')}")
            return pd.DataFrame()
        page = [f.get("attributes", {}) for f in payload.get("features", [])]
        if not page:
            break
        rows.extend(page)
        if not payload.get("exceededTransferLimit"):
            break
        offset += len(page)
        time.sleep(0.1)

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)

    rename: dict[str, str] = {"GEOID": "geography_id"}
    for code, name in fields.items():
        rename[code] = name
        rename[code[:-1] + "M"] = f"{name}_moe"
    df = df.rename(columns=rename)
    return df[[c for c in rename.values() if c in df.columns]]


def fetch_crosswalk(client) -> pd.DataFrame:
    """Tract to neighbourhood and supervisor district, from the city."""
    response = client.get(
        CROSSWALK,
        params={
            "$select": "geoid,neighborhoods_analysis_boundaries,sup_dist_2022",
            "$limit": 5000,
        },
        timeout=120,
    )
    response.raise_for_status()
    df = pd.DataFrame(response.json())
    if df.empty:
        return df
    return df.rename(
        columns={
            "geoid": "geography_id",
            "neighborhoods_analysis_boundaries": "neighborhood",
            "sup_dist_2022": "supervisor_district",
        }
    )


def fetch_tract_points(client) -> pd.DataFrame:
    """Tract centroids, so an estimate can be put on the map."""
    response = client.get(
        TIGERWEB,
        params={
            "where": "STATE='06' AND COUNTY='075'",
            "outFields": "GEOID,BASENAME,CENTLAT,CENTLON,AREALAND",
            "returnGeometry": "false",
            "f": "json",
            "resultRecordCount": 1000,
        },
        timeout=120,
    )
    response.raise_for_status()
    rows = [f.get("attributes", {}) for f in response.json().get("features", [])]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return pd.DataFrame(
        {
            "geography_id": df["GEOID"].astype(str),
            "tract_name": df.get("BASENAME", pd.Series(dtype=str)).astype(str),
            "lat": pd.to_numeric(df.get("CENTLAT"), errors="coerce"),
            "lon": pd.to_numeric(df.get("CENTLON"), errors="coerce"),
            "land_area_m2": pd.to_numeric(df.get("AREALAND"), errors="coerce"),
        }
    )


def roll_up(tracts: pd.DataFrame, by: str) -> pd.DataFrame:
    """Aggregate tract estimates to neighbourhoods or supervisor districts.

    Counts sum. Medians cannot be summed, so they are weighted by the
    population or household base they describe, which is an approximation and
    is labelled as one wherever it surfaces. Margins of error on summed counts
    combine in quadrature, which is what the Census Bureau prescribes.
    """
    if tracts.empty or by not in tracts.columns:
        return pd.DataFrame()

    derived = {name for _, _, name in SHARES}
    skip = {
        "geography_id", "neighborhood", "supervisor_district", "tract_name",
        "lat", "lon", "land_area_m2", "NAME",
    }
    counts = [
        c
        for c in tracts.columns
        if not c.endswith("_moe")
        and c not in skip
        and c not in derived
        and not c.startswith("median_")
    ]
    medians = [c for c in tracts.columns if c.startswith("median_")]

    rows = []
    for area, group in tracts.groupby(by):
        if not str(area).strip():
            continue
        record: dict[str, object] = {by: area, "tracts": len(group)}
        for column in counts:
            record[column] = pd.to_numeric(group[column], errors="coerce").sum(min_count=1)
            moe = f"{column}_moe"
            if moe in group.columns:
                errors = pd.to_numeric(group[moe], errors="coerce").fillna(0)
                record[moe] = float((errors ** 2).sum() ** 0.5)
        for column in medians:
            # A median of medians is not a median. Weighting each tract by the
            # base it describes is the usual approximation and is the best that
            # can be done without the underlying microdata; it is labelled as
            # approximate wherever it is surfaced.
            weight_col = "households" if "income" in column or "rent" in column else "population"
            weights = pd.to_numeric(group.get(weight_col), errors="coerce")
            values = pd.to_numeric(group[column], errors="coerce")
            mask = values.notna() & weights.notna() & (values > 0)
            if mask.any() and weights[mask].sum() > 0:
                record[column] = float((values[mask] * weights[mask]).sum() / weights[mask].sum())
            else:
                record[column] = values.median()
        rows.append(record)
    return add_shares(pd.DataFrame(rows))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geographies", default="tract,neighborhood,county")
    args = parser.parse_args()

    import httpx

    OUT.mkdir(parents=True, exist_ok=True)
    geographies = tuple(g.strip() for g in args.geographies.split(",") if g.strip())

    with httpx.Client(follow_redirects=True) as client:
        print("counts by age and race, from the city portal")
        counts = fetch_portal_counts(client, geographies)

        print("tract to neighbourhood crosswalk")
        crosswalk = fetch_crosswalk(client)
        print(f"    {len(crosswalk):,} tracts mapped to neighbourhoods")

        print("tract centroids")
        points = fetch_tract_points(client)
        print(f"    {len(points):,} located")

        print("American Community Survey tables, from the Living Atlas")
        tracts = pd.DataFrame()
        for service, fields in LAYERS.items():
            frame = fetch_layer(client, service, fields)
            label = service.replace("ACS_", "").replace("_Boundaries", "")[:44]
            if frame.empty:
                print(f"    {label:<46} unavailable")
                continue
            print(f"    {label:<46} {len(frame):>4} tracts, {len(fields)} measures")
            tracts = frame if tracts.empty else tracts.merge(frame, on="geography_id", how="outer")
            time.sleep(0.2)

    if tracts.empty:
        raise SystemExit("no ACS tables were reachable")

    # shares computed here and again after each roll-up, from that level's counts
    tracts = add_shares(tracts)

    if not crosswalk.empty:
        tracts = tracts.merge(crosswalk, on="geography_id", how="left")
    if not points.empty:
        tracts = tracts.merge(points, on="geography_id", how="left")

    neighborhoods = roll_up(tracts, "neighborhood")
    districts = roll_up(tracts, "supervisor_district")

    tracts.to_parquet(OUT / "census_tracts.parquet", index=False)
    if not neighborhoods.empty:
        neighborhoods.to_parquet(OUT / "census_neighborhoods.parquet", index=False)
    if not districts.empty:
        districts.to_parquet(OUT / "census_districts.parquet", index=False)
    if not counts.empty:
        counts.to_parquet(OUT / "census_demographics.parquet", index=False)

    print(f"\n  census_tracts         {len(tracts):>6,} tracts x {len(tracts.columns)} columns")
    print(f"  census_neighborhoods  {len(neighborhoods):>6,} neighbourhoods")
    print(f"  census_districts      {len(districts):>6,} supervisor districts")
    print(f"  census_demographics   {len(counts):>6,} age and race counts")

    if "population" in tracts.columns:
        print(f"\n  city population {int(tracts['population'].sum()):,} summed over tracts")
    if not neighborhoods.empty and "median_household_income" in neighborhoods.columns:
        ranked = neighborhoods.dropna(subset=["median_household_income"]).sort_values(
            "median_household_income", ascending=False
        )
        print("\n  median household income, highest and lowest")
        for _, row in pd.concat([ranked.head(3), ranked.tail(3)]).iterrows():
            print(f"    {row['neighborhood']:<34} ${int(row['median_household_income']):>7,}")


if __name__ == "__main__":
    main()
