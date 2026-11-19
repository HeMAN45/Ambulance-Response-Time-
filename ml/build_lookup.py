# C:\aimlmini\ml\build_lookup.py
"""Build the zip to zone lookup the web app needs at prediction time.

The model expects a zone (MODZCTA) and a dispatch area, but the Predict form
takes a zip code. This script saves:
- zip_to_zone: the same crosswalk clean.py uses, so the app maps form input
  to the exact zone value the model was trained on
- zone_to_area: the most common dispatch area per zone in the training period,
  because dispatch area is a model feature the form does not ask for
- zone_to_borough: borough per zone for the form and the highlight map
"""
import json

import geopandas as gpd
import pandas as pd

TRAIN = "data/processed/train.csv"
MODZCTA_RAW = "tmp/modzcta_raw.geojson"
GEO = "data/geo/zips.geojson"
OUT = "data/processed/zip_crosswalk.json"


def main() -> None:
    train = pd.read_csv(TRAIN)
    area = (
        train.groupby(["zone", "incident_dispatch_area"]).size().reset_index(name="n")
        .sort_values("n", ascending=False).drop_duplicates("zone")
    )
    zone_to_area = dict(zip(area["zone"], area["incident_dispatch_area"]))

    g = json.load(open(MODZCTA_RAW))
    zip_to_zone = {}
    for feat in g["features"]:
        modzcta = feat["properties"]["modzcta"]
        # The boundary file includes a 99999 placeholder with zero population.
        # It never appears in the incident data, so it is not a valid input.
        if modzcta == "99999":
            continue
        for z in str(feat["properties"]["zcta"]).split(","):
            z = z.strip()
            if z:
                zip_to_zone.setdefault(z, modzcta)
        zip_to_zone.setdefault(modzcta, modzcta)

    zips = gpd.read_file(GEO)
    zone_to_borough = {
        r["modzcta"]: r["borough"]
        for _, r in zips.iterrows()
        if isinstance(r["borough"], str) and r["borough"]
    }

    json.dump({
        "zip_to_zone": zip_to_zone,
        "zone_to_area": zone_to_area,
        "zone_to_borough": zone_to_borough,
    }, open(OUT, "w"))
    print(f"zips: {len(zip_to_zone)}, zones with area: {len(zone_to_area)}, zones with borough: {len(zone_to_borough)}")


if __name__ == "__main__":
    main()
