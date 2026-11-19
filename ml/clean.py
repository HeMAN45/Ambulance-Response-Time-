# C:\aimlmini\ml\clean.py
"""Clean the raw EMS data and build the zone key.

Filter steps, each reported with the number of rows removed:
1. keep rows where valid_incident_rspns_time_indc is Y
2. drop rows with a null or unparseable response time (the target)
3. drop rows with response time above 60 minutes, after printing the
   distribution so the cut is visible rather than assumed
4. map zipcode to the MODZCTA zone used by the boundary file, using the
   zcta field in the MODZCTA GeoJSON as the crosswalk. Zoning by MODZCTA
   instead of raw zip keeps zone groups large enough to respect the 30
   incident minimum on the map.

The sampling to about 371,869 rows happened at download time, every 4th day
of the month across 2023. That is recorded in clean_report.json.
"""
import json
import os

import numpy as np
import pandas as pd

RAW = "data/raw/ems_2023.csv"
CROSSWALK = "tmp/modzcta_raw.geojson"
OUT_CSV = "data/processed/clean.csv"
OUT_REPORT = "data/processed/clean_report.json"

CUT_MINUTES = 60.0


def load_crosswalk(path: str) -> dict:
    """Return {zipcode: modzcta} from the zcta list field of each MODZCTA feature."""
    g = json.load(open(path))
    xw = {}
    for feat in g["features"]:
        modzcta = feat["properties"]["modzcta"]
        # Skip the 99999 placeholder zone, it has no incidents and is not a real zip.
        if modzcta == "99999":
            continue
        for z in str(feat["properties"]["zcta"]).split(","):
            z = z.strip()
            if z:
                xw.setdefault(z, modzcta)
        # a modzcta code maps to itself, so zones never fall through
        xw.setdefault(modzcta, modzcta)
    return xw


def main() -> None:
    df = pd.read_csv(RAW, dtype=str)
    n0 = len(df)
    report = {"source_rows": n0, "sampling": "every 4th day of month across 2023 (done at download time)"}

    # 1. validity flag
    df = df[df["valid_incident_rspns_time_indc"] == "Y"]
    n1 = len(df)
    report["after_valid_flag"] = n1
    report["removed_invalid_flag"] = n0 - n1

    # target, seconds to minutes
    df["response_sec"] = pd.to_numeric(df["incident_response_seconds_qy"], errors="coerce")
    df = df[df["response_sec"].notna()]
    n2 = len(df)
    report["after_target_not_null"] = n2
    report["removed_null_target"] = n1 - n2

    df["response_min"] = df["response_sec"] / 60.0

    # 3. distribution then cut
    q = df["response_min"].quantile([0.5, 0.75, 0.9, 0.95, 0.99]).round(2).to_dict()
    report["response_min_quantiles_before_cut"] = {k: float(v) for k, v in q.items()}
    df = df[df["response_min"] <= CUT_MINUTES]
    n3 = len(df)
    report["after_60min_cut"] = n3
    report["removed_over_60min"] = n2 - n3

    # 4. zone key
    xw = load_crosswalk(CROSSWALK)
    df["zipcode"] = df["zipcode"].fillna("").str.strip()
    df["zone"] = df["zipcode"].map(xw)
    n_no_zone = int(df["zone"].isna().sum())
    report["rows_without_zone"] = n_no_zone
    df["zone"] = df["zone"].fillna("Unknown")
    df["borough"] = df["borough"].fillna("Unknown").str.strip().str.title()
    df["initial_severity_level_code"] = df["initial_severity_level_code"].fillna("Unknown").str.strip()
    df["initial_call_type"] = df["initial_call_type"].fillna("Unknown").str.strip()
    df["incident_dispatch_area"] = df["incident_dispatch_area"].fillna("Unknown").str.strip()

    keep = [
        "incident_datetime", "initial_call_type", "initial_severity_level_code",
        "borough", "zipcode", "incident_dispatch_area", "zone", "response_min",
    ]
    out = df[keep].copy()
    out = out.sort_values("incident_datetime").reset_index(drop=True)
    out.to_csv(OUT_CSV, index=False)
    report["final_rows"] = len(out)
    report["severity_values"] = sorted(out["initial_severity_level_code"].unique().tolist())
    report["zones"] = int(out["zone"].nunique())

    os.makedirs("data/processed", exist_ok=True)
    json.dump(report, open(OUT_REPORT, "w"), indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
