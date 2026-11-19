# C:\aimlmini\ml\build_stats.py
"""Precompute every statistics slice the web app serves, and prepare boundaries.

Nothing in the Flask app calculates from raw data during a request. This script
computes all slices once and writes small JSON files:

data/processed/zip_stats.json
  records: zone statistics for the four grouping levels
    (zone), (zone, severity), (zone, hour_band), (zone, hour_band, severity),
    so any combination of hour_band and severity filter maps to exactly one
    level with hour_band or severity set to "all".
  summary: overall median, p90, share over 10 and count for each of the 45
    hour_band and severity combinations.
  zone_hourly: median response per hour for each zone, for the zone panel chart.
data/processed/hourly_stats.json
  median and p90 per hour, overall and by borough.
data/processed/heatmap_stats.json
  H1 hour by weekday medians, H2 borough by hour medians,
  H3 severity by hour band share over 10 minutes.
data/processed/trend_stats.json
  monthly median, p90 and count, overall and by borough, and per zone monthly
  medians for the ranking sparklines.
data/processed/breakdown_stats.json
  median, p90, count by borough, by severity and by call type.
data/processed/distribution_stats.json
  2 minute histogram bins of response time, overall and by borough.
data/geo/zips.geojson, data/geo/boroughs.geojson
  simplified boundaries, each kept under 1 MB.

Zone means MODZCTA. The zone column in clean.csv was built from the zip to
MODZCTA crosswalk, so it matches the modzcta field in the boundary file.
"""
import json

import geopandas as gpd
import numpy as np
import pandas as pd

CLEAN = "data/processed/clean.csv"
HOUR_BANDS = ["overnight", "morning", "midday", "evening"]
BINS_2MIN = [(i, i + 2) for i in range(0, 60, 2)]

MODZCTA_RAW = "tmp/modzcta_raw.geojson"
BOROUGHS_RAW = "tmp/boroughs_raw.geojson"


def slice_stats(g: pd.DataFrame) -> dict:
    return {
        "count": int(len(g)),
        "median": round(float(g["response_min"].median()), 2),
        "p90": round(float(g["response_min"].quantile(0.9)), 2),
        "share_over_10": round(float((g["response_min"] > 10).mean()), 4),
    }


def main() -> None:
    df = pd.read_csv(CLEAN)
    dt = pd.to_datetime(df["incident_datetime"])
    df["hour"] = dt.dt.hour
    df["day_of_week"] = dt.dt.day_of_week
    df["hour_band"] = np.select(
        [df["hour"].between(lo, hi) for _, lo, hi in
         [("overnight", 0, 5), ("morning", 6, 11), ("midday", 12, 17), ("evening", 18, 23)]],
        ["overnight", "morning", "midday", "evening"],
        default="overnight",
    )

    # ---- zone slices ----
    records = []
    for rec_keys, grouped in {
        ("all", "all"): df.groupby("zone"),
        ("all", "sev"): df.groupby(["zone", "initial_severity_level_code"]),
        ("hb", "all"): df.groupby(["zone", "hour_band"]),
        ("hb", "sev"): df.groupby(["zone", "hour_band", "initial_severity_level_code"]),
    }.items():
        hb_mode, sev_mode = rec_keys
        for keys, g in grouped:
            keys = keys if isinstance(keys, tuple) else (keys,)
            zone = keys[0]
            hb = keys[1] if hb_mode == "hb" else "all"
            sev = keys[-1] if sev_mode == "sev" else "all"
            records.append({"zone": zone, "hour_band": hb, "severity": str(sev), **slice_stats(g)})
    print(f"zone records: {len(records)}")

    # ---- summary for every hour_band and severity combination ----
    summary = {}
    for hb in HOUR_BANDS + ["all"]:
        for sev in sorted(df["initial_severity_level_code"].unique()) + ["all"]:
            sub = df
            if hb != "all":
                sub = sub[sub["hour_band"] == hb]
            if sev != "all":
                sub = sub[sub["initial_severity_level_code"] == sev]
            if len(sub):
                summary[f"{hb}|{sev}"] = slice_stats(sub)
    summary["all|all"] = slice_stats(df)

    # ---- zone hourly medians for the zone panel ----
    zone_hourly = {}
    for (zone, hour), g in df.groupby(["zone", "hour"]):
        zone_hourly.setdefault(zone, []).append(
            {"hour": int(hour), "median": round(float(g["response_min"].median()), 2),
             "count": int(len(g))}
        )

    json.dump(
        {"records": records, "summary": summary, "zone_hourly": zone_hourly},
        open("data/processed/zip_stats.json", "w"),
    )

    # ---- hourly stats by borough ----
    hourly = []
    for (borough, hour), g in df.groupby(["borough", "hour"]):
        hourly.append({"borough": borough, "hour": int(hour), **slice_stats(g)})
    for hour, g in df.groupby("hour"):
        hourly.append({"borough": "all", "hour": int(hour), **slice_stats(g)})
    json.dump({"records": hourly}, open("data/processed/hourly_stats.json", "w"))

    # ---- heatmaps ----
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    h1 = [
        {"hour": int(h), "weekday": weekdays[int(d)], "median": round(float(g["response_min"].median()), 2),
         "count": int(len(g))}
        for (d, h), g in df.groupby([df["incident_datetime"].pipe(lambda s: pd.to_datetime(s)).dt.day_of_week, "hour"])
    ]
    h2 = [
        {"borough": b, "hour": int(h), "median": round(float(g["response_min"].median()), 2), "count": int(len(g))}
        for (b, h), g in df.groupby(["borough", "hour"])
    ]
    h3 = [
        {"severity": str(s), "hour_band": hb, **slice_stats(g)}
        for (s, hb), g in df.groupby(["initial_severity_level_code", "hour_band"])
    ]
    json.dump({"h1": h1, "h2": h2, "h3": h3}, open("data/processed/heatmap_stats.json", "w"))

    # ---- monthly trend ----
    month = pd.to_datetime(df["incident_datetime"]).dt.month
    trend = []
    for (b, m), g in df.groupby(["borough", month]):
        trend.append({"borough": b, "month": int(m), **slice_stats(g)})
    for m, g in df.groupby(month):
        trend.append({"borough": "all", "month": int(m), **slice_stats(g)})
    zone_trend = [
        {"zone": z, "month": int(m), "median": round(float(g["response_min"].median()), 2), "count": int(len(g))}
        for (z, m), g in df.groupby(["zone", month])
    ]
    json.dump({"records": trend, "zone_trend": zone_trend}, open("data/processed/trend_stats.json", "w"))

    # ---- breakdown by borough, severity, call type ----
    breakdown = {}
    for name, col in [("borough", "borough"), ("severity", "initial_severity_level_code"),
                      ("call_type", "initial_call_type")]:
        breakdown[name] = [
            {"value": str(v), **slice_stats(g)}
            for v, g in df.groupby(col)
        ]
    json.dump(breakdown, open("data/processed/breakdown_stats.json", "w"))

    # ---- distribution histogram ----
    dist = {}
    cuts = np.arange(0, 62, 2)
    for b, g in list(df.groupby("borough")) + [("all", df)]:
        hist, _ = np.histogram(g["response_min"], bins=cuts)
        dist[b] = {
            "bins": [{"lo": int(cuts[i]), "hi": int(cuts[i + 1]), "count": int(hist[i])} for i in range(len(hist))],
            **slice_stats(g),
        }
    json.dump(dist, open("data/processed/distribution_stats.json", "w"))

    # ---- boundaries ----
    zips = gpd.read_file(MODZCTA_RAW)
    boroughs = gpd.read_file(BOROUGHS_RAW)

    # attach the borough name to each zone with a spatial join on centroids
    pts = zips.copy()
    pts["geometry"] = pts.geometry.centroid
    joined = gpd.sjoin(pts, boroughs[["boroname", "geometry"]], how="left", predicate="within")
    zips["borough"] = joined["boroname"].values

    keep_cols = ["modzcta", "label", "borough", "geometry"]
    zips = gpd.GeoDataFrame(zips[keep_cols], geometry="geometry", crs=zips.crs)
    zips["geometry"] = zips.geometry.simplify(0.0005, preserve_topology=True)
    boroughs["geometry"] = boroughs.geometry.simplify(0.0005, preserve_topology=True)

    for name, gdf in [("zips.geojson", zips), ("boroughs.geojson", boroughs)]:
        gdf.to_file(f"data/geo/{name}", driver="GeoJSON")
        size = __import__("os").path.getsize(f"data/geo/{name}")
        print(f"{name}: {len(gdf)} features, {size / 1e6:.2f} MB")

    print("build_stats done")


if __name__ == "__main__":
    main()
