import os
import json
import csv
import gzip
import time
from urllib.parse import unquote_plus
import boto3
from datetime import datetime

s3 = boto3.client("s3")
sns = boto3.client("sns")

SILVER_BUCKET = os.environ.get("SILVER_BUCKET", "dvf-silver")
GOLD_BUCKET   = os.environ.get("GOLD_BUCKET", "dvf-gold")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")

VF_COL_CANDIDATES = ["valeur_fonciere", "valeur fonciere"]
SURF_COL_CANDIDATES = [
    "surface_reelle_bati", "surface reelle bati",
    "surface_terrain", "surface terrain"
]

def extract_s3_records(event: dict):
    records = event.get("Records", [])
    if not records:
        return []
    if isinstance(records[0], dict) and "body" in records[0]:
        out = []
        for msg in records:
            try:
                payload = json.loads(msg.get("body", ""))
            except Exception:
                continue
            out.extend(payload.get("Records", []))
        return out
    return records

def find_col(fieldnames, candidates):
    lower = {c.lower(): c for c in fieldnames}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None

def to_float(x):
    if x is None:
        return None
    s = str(x).strip().replace(",", ".")
    if s == "" or s.lower() == "nan":
        return None
    try:
        return float(s)
    except Exception:
        return None

def handler(event, context):
    t0 = time.time()
    print("[GOLD_M2] raw event:", json.dumps(event)[:2000])

    s3recs = extract_s3_records(event)
    if not s3recs:
        print("[GOLD_M2] No records -> exit")
        return {"statusCode": 200, "message": "no records"}

    total_rows = 0
    used_rows = 0
    sum_price_m2 = 0.0
    processed_files = []

    for rec in s3recs:
        bucket = rec["s3"]["bucket"]["name"]
        key_raw = rec["s3"]["object"]["key"]
        key = unquote_plus(key_raw)  # ✅ IMPORTANT

        if not key.startswith("silver/") or not (key.endswith(".csv.gz") or key.endswith(".gz")):
            print("[GOLD_M2] skip key:", key)
            continue

        tmp_in = "/tmp/in.csv.gz"
        print(f"[GOLD_M2] downloading s3://{bucket}/{key}")
        s3.download_file(bucket, key, tmp_in)

        with gzip.open(tmp_in, "rt", encoding="utf-8", errors="ignore", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            if not reader.fieldnames:
                print("[GOLD_M2] empty header -> skip", key)
                continue

            vf_col = find_col(reader.fieldnames, VF_COL_CANDIDATES)
            surf_col = find_col(reader.fieldnames, SURF_COL_CANDIDATES)

            if not vf_col or not surf_col:
                print("[GOLD_M2] missing columns:",
                      {"vf_col": vf_col, "surf_col": surf_col})
                continue

            file_total = 0
            file_used = 0

            for row in reader:
                file_total += 1
                total_rows += 1

                vf = to_float(row.get(vf_col))
                surf = to_float(row.get(surf_col))

                if vf is None or surf is None or surf <= 0 or vf < 0:
                    continue

                sum_price_m2 += (vf / surf)
                used_rows += 1
                file_used += 1

            print(f"[GOLD_M2] rows read={file_total}, used={file_used} for {key}")
            processed_files.append(key)

    if not processed_files:
        print("[GOLD_M2] No processed files -> exit")
        return {"statusCode": 200, "message": "no silver files processed"}

    avg_price_m2 = (sum_price_m2 / used_rows) if used_rows > 0 else None

    years = set()
    for k in processed_files:
        if "year=" in k:
            try:
                years.add(k.split("year=")[1].split("/")[0])
            except Exception:
                pass
    year_tag = years.pop() if len(years) == 1 else "multi"

    out_key = f"gold/year={year_tag}/avg_price_m2_{year_tag}.json"
    out = {
        "year": year_tag,
        "source_files": processed_files,
        "rows_total": total_rows,
        "rows_used": used_rows,
        "avg_price_m2": avg_price_m2,
        "generated_at_utc": datetime.utcnow().isoformat() + "Z",
        "duration_sec": round(time.time() - t0, 3),
    }

    tmp_out = "/tmp/out.json"
    with open(tmp_out, "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=2)

    print(f"[GOLD_M2] uploading -> s3://{GOLD_BUCKET}/{out_key}")
    s3.upload_file(tmp_out, GOLD_BUCKET, out_key)

    if SNS_TOPIC_ARN:
        try:
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Message=json.dumps({
                    "stage": "gold_price_m2",
                    "year": year_tag,
                    "gold_key": out_key,
                    "rows_used": used_rows,
                    "avg_price_m2": avg_price_m2,
                    "duration_sec": out["duration_sec"]
                })
            )
        except Exception as e:
            print("[GOLD_M2][WARN] sns publish failed:", str(e))

    return {"statusCode": 200, "gold_key": out_key, "rows_used": used_rows, "avg_price_m2": avg_price_m2}
