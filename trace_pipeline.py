from chopcast.config import Settings
from chopcast.processing.pipeline import build_deps, process
from chopcast.logging import configure
import sqlite3
import json

def trace_single_report():
    settings = Settings.load()
    configure(settings.logging)
    deps = build_deps(settings.processing, settings.labeling, path_root=str(settings.to_paths().root))

    # 1. Get one raw report from DB
    conn = sqlite3.connect(settings.to_paths().raw_db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM reports LIMIT 1").fetchone()
    conn.close()

    if not row:
        print("No reports found in DB.")
        return

    raw_dict = dict(row)
    print("=== STEP 1: RAW INPUT ===")
    print(f"Raw Text: {raw_dict['raw_text']}")
    print(f"Hash: {raw_dict['hash']}\n")

    # 2. Process through pipeline
    feature_row = process(raw_dict, deps)

    if not feature_row:
        print("Pipeline rejected this report.")
        return

    print("=== STEP 2: PROCESSED OUTPUT ===")
    print(f"Cleaned Text: {feature_row.clean_text}")
    print(f"Severity Label: {feature_row.severity_label}")
    print(f"Altitude Band: {feature_row.altitude_band}")
    print(f"Hour of Day: {feature_row.hour_of_day}\n")

    print("=== STEP 3: FEATURE VECTOR (JSON) ===")
    print(json.dumps(feature_row.to_dict(), indent=2))

if __name__ == "__main__":
    trace_single_report()
