#!/usr/bin/env python
"""Pull San Francisco places from Overture Maps into a local parquet file.

Overture is the primary source of destinations. It merges Foursquare, Meta and
Microsoft place data under a permissive licence, carries a category taxonomy and
an operating status, and is a single reliable download - unlike Overpass, which
rate-limits a city-sized query into the ground.

Places are points, so the bounding-box columns hold the coordinate directly and
no geometry parsing is needed.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

RELEASE = "2026-08-19.0"
SOURCE = f"s3://overturemaps-us-west-2/release/{RELEASE}/theme=places/type=place/*"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", default=RELEASE)
    parser.add_argument("--min-confidence", type=float, default=0.15)
    args = parser.parse_args()

    import duckdb

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    west, south, east, north = cfg["bbox"]
    RAW.mkdir(parents=True, exist_ok=True)
    out = RAW / "overture_places_sf.parquet"

    source = SOURCE.replace(RELEASE, args.release)
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")

    query = f"""
    COPY (
      SELECT
        id,
        names.primary                     AS name,
        categories.primary                AS category_primary,
        basic_category                    AS basic_category,
        taxonomy.hierarchy                AS taxonomy,
        confidence,
        operating_status,
        brand.names.primary               AS brand,
        addresses[1].freeform             AS address,  -- addresses is a list
        bbox.xmin                         AS lon,
        bbox.ymin                         AS lat
      FROM read_parquet('{source}', hive_partitioning=1)
      WHERE bbox.xmin BETWEEN {west} AND {east}
        AND bbox.ymin BETWEEN {south} AND {north}
        AND confidence >= {args.min_confidence}
    ) TO '{out.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """

    print(f"reading Overture release {args.release} for bbox "
          f"({west}, {south}, {east}, {north})", flush=True)
    start = time.time()
    con.execute(query)
    print(f"wrote {out} in {time.time() - start:.0f}s")

    summary = con.execute(
        f"""
        SELECT category_primary, count(*) AS n
        FROM read_parquet('{out.as_posix()}')
        GROUP BY 1 ORDER BY n DESC LIMIT 30
        """
    ).fetchall()
    total = con.execute(f"SELECT count(*) FROM read_parquet('{out.as_posix()}')").fetchone()[0]
    closed = con.execute(
        f"SELECT count(*) FROM read_parquet('{out.as_posix()}') "
        f"WHERE operating_status IS NOT NULL AND operating_status <> 'open'"
    ).fetchone()[0]

    print(f"\n{total:,} places, {closed:,} flagged not open")
    print("most common categories:")
    for name, n in summary:
        print(f"  {n:>6,}  {name}")


if __name__ == "__main__":
    main()
