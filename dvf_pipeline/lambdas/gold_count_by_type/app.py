import os
import json
import csv
import gzip
import time
from collections import Counter
from urllib.parse import unquote_plus
import boto3
from datetime import datetime

s3 = boto3.client("s3")
sns = boto3.client("sns")

SILVER_BUCKET = os.environ.get("SILVER_BUCKET", "dvf-silver")
GOLD_BUCKET   = os.environ.get("GOLD_BUCKET", "dvf-gold")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")

# colonnes possibles DVF (selon millésime)
TYPE_COL_CANDIDATES = [
    "type_local", "type local",
    "nature_mutation", "nature mutation"
]

def extract_s3_records(event: dict):
    """
    Supporte:
    - Event S3 direct: event["Records"][i]["s3"]["object"]["key"]
    - Event SQS: event["Records"][i]["body"] contient JSON S3 event
    """
    records = event.get("Records", [])
    if not records:
        return []

    # SQS wrapper
    if isinstance(records[0], dict) and "body" in records[0]:
        out = []
        for msg in records:
            body = msg.get("body", "")
            try:
                payload = json.loads(body)
            except Exception:
                continue
            out.extend(payload.get("Records", []))
        return out

    # S3 direct
    return records

def find_type_column(fieldnames):
    lower = {c.lower(): c for c in fieldnames}
    for cand in TYPE_COL_CANDIDATES:
        if cand.lower() in lower:
            return lower[cand.lower()]
    # fallback: tenter "type_local" exact si existe
    return lower.get("type_local")

def handler(event, context):
    t0 = time.time()
    print("[GOLD_COUNT] raw event:", json.dumps(event)[:2000])

    s3recs = extract_s3_records(event)
    if not s3recs:
        print("[GOLD_COUNT] No records -> exit")
        return {"statusCode": 200, "message": "no records"}

    # On agrège sur tous les records reçus (souvent 1)
    grand_total = 0
    counts = Counter()
    processed_files = []

    for rec in s3recs:
        bucket = rec["s3"]["bucket"]["name"]
        key_raw = rec["s3"]["object"]["key"]
        key = unquote_plus(key_raw)  # ✅ IMPORTANT (year%3D2025 -> year=2025)

        # On ne traite que silver/
        if not key.startswith("silver/") or not (key.endswith(".csv.gz") or key.endswith(".gz")):
            print("[GOLD_COUNT] skip key:", key)
            continue

        tmp_in = "/tmp/in.csv.gz"
        print(f"[GOLD_COUNT] downloading s3://{bucket}/{key}")
        s3.download_file(bucket, key, tmp_in)

        # lecture streaming gzip csv
        with gzip.open(tmp_in, "rt", encoding="utf-8", errors="ignore", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            if not reader.fieldnames:
                print("[GOLD_COUNT] empty header -> skip", key)
                continue

            type_col = find_type_column(reader.fieldnames)
            if not type_col:
                # si pas trouvé, on log et on sort
                print("[GOLD_COUNT] type column not found in:", reader.fieldnames[:50])
                continue

            file_total = 0
            for row in reader:
                v = (row.get(type_col) or "").strip()
                if v == "":
                    v = "UNKNOWN"
                counts[v] += 1
                file_total += 1

            print(f"[GOLD_COUNT] rows read for {key}: {file_total}")
            grand_total += file_total
            processed_files.append(key)

    if not processed_files:
        print("[GOLD_COUNT] No processed files -> exit")
        return {"statusCode": 200, "message": "no silver files processed"}

    # Déterminer l'année depuis la key (silver/year=2025/...)
    # si multiple, on met "multi"
    years = set()
    for k in processed_files:
        if "year=" in k:
            try:
                years.add(k.split("year=")[1].split("/")[0])
            except Exception:
                pass
    year_tag = years.pop() if len(years) == 1 else "multi"

    out_key = f"gold/year={year_tag}/count_by_type_{year_tag}.json"
    payload_out = {
        "year": year_tag,
        "source_files": processed_files,
        "total_rows": grand_total,
        "counts": dict(counts),
        "generated_at_utc": datetime.utcnow().isoformat() + "Z",
        "duration_sec": round(time.time() - t0, 3),
    }

    tmp_out = "/tmp/out.json"
    with open(tmp_out, "w", encoding="utf-8") as fp:
        json.dump(payload_out, fp, ensure_ascii=False, indent=2)

    print(f"[GOLD_COUNT] uploading -> s3://{GOLD_BUCKET}/{out_key}")
    s3.upload_file(tmp_out, GOLD_BUCKET, out_key)

    if SNS_TOPIC_ARN:
        try:
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Message=json.dumps({
                    "stage": "gold_count_by_type",
                    "year": year_tag,
                    "gold_key": out_key,
                    "total_rows": grand_total,
                    "duration_sec": payload_out["duration_sec"]
                })
            )
        except Exception as e:
            print("[GOLD_COUNT][WARN] sns publish failed:", str(e))

    return {"statusCode": 200, "gold_key": out_key, "total_rows": grand_total}
