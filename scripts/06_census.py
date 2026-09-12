#!/usr/bin/env python
"""Pull American Community Survey tract data for San Francisco.

Who lives where, in the only form that is both free and authoritative. Tract
level rather than block group, because the detailed population tables this
needs are not published at block group.

Detailed-origin counts are included because a question like "where would an
Indian chai house work" is partly a question about whose neighbourhood it is.
That is a legitimate use of published census counts, and it is reported as a
count of residents, never as an assumption about what any individual wants.
Margins of error at tract level are wide for small groups, so counts are
reported alongside the total population rather than as a headline.

Tract centroids come from the TIGER cartographic boundary file, so each tract
can be matched to a point on the map without shipping polygons.
"""
from __future__ import annotations

import argparse
import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw" / "census"

YEAR = 2023
STATE = "06"
COUNTY = "075"

# variable -> output column. Kept short; every one of these is used somewhere.
VARIABLES = {
    "B01003_001E": "population",
    "B19013_001E": "median_household_income",
    "B01002_001E": "median_age",
    "B25064_001E": "median_gross_rent",
    "B15003_022E": "bachelors",
    "B15003_023E": "masters",
    "B15003_025E": "doctorate",
    "B08301_001E": "commuters",
    "B08301_010E": "commute_transit",
    "B08301_019E": "commute_walk",
    "B02015_021E": "asian_indian",
    "B02015_002E": "chinese",
    "B03001_003E": "hispanic_latino",
    "B02001_003E": "black",
    "B25003_003E": "renter_households",
    "B25003_001E": "households",
}

BOUNDARY_URL = (
    f"https://www2.census.gov/geo/tiger/GENZ{YEAR}/shp/"
    f"cb_{YEAR}_{STATE}_tract_500k.zip"
)


def fetch_acs(api_key: str | None) -> pd.DataFrame:
    import httpx

    names = list(VARIABLES)
    params = {
        "get": "NAME," + ",".join(names),
        "for": "tract:*",
        "in": f"state:{STATE} county:{COUNTY}",
    }
    if api_key:
        params["key"] = api_key

    response = httpx.get(
        f"https://api.census.gov/data/{YEAR}/acs/acs5",
        params=params,
        timeout=120,
        follow_redirects=True,
    )
    response.raise_for_status()
    rows = response.json()
    df = pd.DataFrame(rows[1:], columns=rows[0])

    for variable, column in VARIABLES.items():
        # the census uses large negative sentinels for suppressed values
        values = pd.to_numeric(df[variable], errors="coerce")
        df[column] = values.where(values > -1e6)
        df.drop(columns=[variable], inplace=True)

    df["tract"] = STATE + COUNTY + df["tract"]
    return df


def fetch_centroids() -> pd.DataFrame:
    """Tract centroids from the cartographic boundary file."""
    import httpx
    import shapefile  # provided by pyshp, a dependency of geopandas' stack

    RAW.mkdir(parents=True, exist_ok=True)
    cached = RAW / "tracts.zip"
    if not cached.exists():
        response = httpx.get(BOUNDARY_URL, timeout=180, follow_redirects=True)
        response.raise_for_status()
        cached.write_bytes(response.content)

    with zipfile.ZipFile(cached) as archive:
        base = next(n[:-4] for n in archive.namelist() if n.endswith(".shp"))
        reader = shapefile.Reader(
            shp=io.BytesIO(archive.read(base + ".shp")),
            dbf=io.BytesIO(archive.read(base + ".dbf")),
            shx=io.BytesIO(archive.read(base + ".shx")),
        )
        fields = [f[0] for f in reader.fields[1:]]
        rows = []
        for record, shape in zip(reader.records(), reader.shapes()):
            attributes = dict(zip(fields, record))
            geoid = attributes.get("GEOID")
            if not geoid or not geoid.startswith(STATE + COUNTY):
                continue
            points = np.array(shape.points)
            if not len(points):
                continue
            rows.append(
                {
                    "tract": geoid,
                    "lon": float(points[:, 0].mean()),
                    "lat": float(points[:, 1].mean()),
                    "land_area_m2": float(attributes.get("ALAND", 0) or 0),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", default=None, help="optional Census API key")
    args = parser.parse_args()

    key = args.key
    if not key:
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("CENSUS_API_KEY="):
                    key = line.split("=", 1)[1].strip() or None

    print(f"fetching ACS {YEAR} 5-year tract data for San Francisco")
    acs = fetch_acs(key)
    print(f"  {len(acs):,} tracts, {len(VARIABLES)} variables")

    print("fetching tract centroids")
    centroids = fetch_centroids()
    print(f"  {len(centroids):,} boundaries")

    df = acs.merge(centroids, on="tract", how="inner")

    # a few ratios that are read far more often than the raw counts
    df["degree_share"] = (
        (df["bachelors"] + df["masters"] + df["doctorate"]) / df["population"].replace(0, np.nan)
    ).round(3)
    df["transit_share"] = (
        df["commute_transit"] / df["commuters"].replace(0, np.nan)
    ).round(3)
    df["walk_share"] = (
        df["commute_walk"] / df["commuters"].replace(0, np.nan)
    ).round(3)
    df["renter_share"] = (
        df["renter_households"] / df["households"].replace(0, np.nan)
    ).round(3)
    df["density_per_km2"] = (
        df["population"] / (df["land_area_m2"] / 1e6).replace(0, np.nan)
    ).round(0)

    OUT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT / "census_tracts.parquet", index=False)

    print(f"\nwrote {len(df):,} tracts -> census_tracts.parquet")
    print(f"  population            {int(df['population'].sum()):,}")
    print(f"  median household income, citywide median  "
          f"${int(df['median_household_income'].median()):,}")
    print(f"  median gross rent, citywide median        "
          f"${int(df['median_gross_rent'].median()):,}")
    top = df.nlargest(5, "asian_indian")[["NAME", "asian_indian", "population"]]
    print("  tracts with the largest Asian Indian population:")
    for row in top.itertuples():
        name = row.NAME.split(";")[0]
        print(f"    {int(row.asian_indian):>5,} of {int(row.population):>6,}  {name}")


if __name__ == "__main__":
    main()
