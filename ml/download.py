# C:\aimlmini\ml\download.py
"""Pull the 2023 NYC EMS Incident Dispatch Data from NYC Open Data (Socrata).

The full year has 1,617,839 rows, more than a student laptop needs. Instead of
downloading everything and sampling later, this script samples at download time
with (day of month mod 4) = 0, verified against the live dataset: it returned
371,869 rows. That keeps every 4th calendar day across the whole year, so
seasonality, every hour of day and every borough stay represented, and the row
count lands in the 400,000 sample range the PRD asks for.

Column names were verified against the dataset metadata on 2026-11-19:
incident_datetime, initial_call_type, initial_severity_level_code, borough,
zipcode, incident_dispatch_area, incident_response_seconds_qy,
valid_incident_rspns_time_indc. All exist in the real schema.
"""
import requests
import pandas as pd

URL = "https://data.cityofnewyork.us/resource/76xm-jjuj.json"
BASE_WHERE = (
    "incident_datetime between '2023-01-01T00:00:00' and '2023-12-31T23:59:59'"
    " and (date_extract_d(incident_datetime) % 4) = 0"
)
params = {
    "$limit": 50000,
    "$where": BASE_WHERE,
    "$select": (
        "incident_datetime,initial_call_type,initial_severity_level_code,"
        "borough,zipcode,incident_dispatch_area,"
        "incident_response_seconds_qy,valid_incident_rspns_time_indc"
    ),
    "$order": "incident_datetime",
}


def main() -> None:
    frames, offset, expected = [], 0, 371869
    while True:
        params["$offset"] = offset
        batch = requests.get(URL, params=params, timeout=120).json()
        if isinstance(batch, dict):
            raise SystemExit(f"Socrata returned an error: {batch}")
        if not batch:
            break
        frames.append(pd.DataFrame(batch))
        offset += len(batch)
        print(f"fetched {offset} rows", flush=True)

    df = pd.concat(frames, ignore_index=True)
    df = df.sort_values("incident_datetime").reset_index(drop=True)
    df.to_csv("data/raw/ems_2023.csv", index=False)
    print(f"saved {df.shape[0]} rows (expected about {expected})")
    print("columns:", list(df.columns))
    print(df.head(3).to_string())


if __name__ == "__main__":
    main()
