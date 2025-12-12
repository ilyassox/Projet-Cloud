import os, io, re, csv, gzip, json, time
import boto3
from datetime import datetime

s3 = boto3.client("s3")
sns = boto3.client("sns")
cw  = boto3.client("cloudwatch")

SILVER_BUCKET = os.environ.get("SILVER_BUCKET", "dvf-silver")
GOLD_BUCKET   = os.environ.get("GOLD_BUCKET", "dvf-gold")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")

def put_metric(name, value, unit="Count"):
    cw.put_metric_data(
        Namespace="DVF_Pipeline",
        MetricData=[{"MetricName": name, "Value": float(value), "Unit": unit}],
    )

def safe_int(x):
    try:
        return int(str(x).strip())
    except:
        return None

def normalize_cp(cp: str) -> str:
    cp = (cp or "").strip()
    return cp.zfill(5) if cp.isdigit() else cp

def extract_year_from_key(key: str) -> str:
    m = re.search(r"year=(\d{4})", key)
    return m.group(1) if m else "unknown"

def parse_s3_event_payload(payload: dict):
    """payload is an S3 event (Records[].s3.bucket.name + Records[].s3.object.key)"""
    out = []
    for r in payload.get("Records", []):
        s3info = r.get("s3", {})
        b = s3info.get("bucket", {}).get("name")
        k = s3info.get("object", {}).get("key")
        if b and k:
            out.append((b, k))
    return out

def parse_from_sqs_event(event: dict):
    """event is an SQS event: Records[].body contains S3 event JSON string"""
    out = []
    for r in event.get("Records", []):
        body = r.get("body", "")
        if not body or not body.strip():
            continue
        payload = json.loads(body)  # can raise -> handled by caller
        out.extend(parse_s3_event_payload(payload))
    return out

def get_s3_targets(event: dict):
    """
    Accepts:
    - SQS event (Records[].body is JSON S3 event)
    - S3 event directly (Records[].s3...)
    """
    # Heuristic: if Records[0] has 'body', treat as SQS
    recs = event.get("Records", [])
    if recs and isinstance(recs[0], dict) and "body" in recs[0]:
        return parse_from_sqs_event(event)
    return parse_s3_event_payload(event)

def handler(event, context):
    t0 = time.time()
    files = 0
    errors = 0
    rows_in = 0

    print("[GOLD_COUNT] Event keys:", list(event.keys()))
    try:
        targets = get_s3_targets(event)
    except Exception as e:
        errors += 1
        print("[GOLD_COUNT][ERROR] cannot parse event:", str(e))
        put_metric("GoldCountErrors", errors)
        raise

    if not targets:
        print("[GOLD_COUNT] No targets found in event. Nothing to do.")
        return {"statusCode": 200, "files": 0, "rows_in": 0, "errors": 0}

    for bucket, key in targets:
        # URL-encoded key sometimes: year%3D2025 -> year=2025
        key = key.replace("%3D", "=")

        if not key.startswith("silver/") or not key.endswith(".csv.gz"):
            print("[GOLD_COUNT] Skip non-silver gz:", bucket, key)
            continue

        year = extract_year_from_key(key)
        tmp_in = "/tmp/in.csv.gz"

        print(f"[GOLD_COUNT] Processing s3://{bucket}/{key}")
        try:
            s3.download_file(bucket, key, tmp_in)

            counts = {}  # (year, cp, type_local) -> count

            with gzip.open(tmp_in, "rt", encoding="utf-8", errors="ignore", newline="") as f:
                reader = csv.DictReader(f, delimiter=";")
                # handle possible column naming variations
                cols = [c.lower() for c in (reader.fieldnames or [])]
                # candidates in DVF normalized:
                # type_local, code_postal (or code_postal_commune), commune, etc.
                def pick_col(*cands):
                    for c in cands:
                        if c in cols:
                            return c
                    return None

                col_type = pick_col("type_local", "type_local_1", "type")
                col_cp   = pick_col("code_postal", "code_postal_commune", "codepostal")
                if not col_type or not col_cp:
                    raise RuntimeError(f"Missing columns. Found={reader.fieldnames}")

                for row in reader:
                    rows_in += 1
                    t = (row.get(col_type) or "").strip()
                    cp = normalize_cp(row.get(col_cp) or "")
                    if not t:
                        continue
                    k2 = (year, cp, t)
                    counts[k2] = counts.get(k2, 0) + 1

            # Write JSON output (small)
            out_key = f"gold/year={year}/count_by_type_{year}.json"
            payload = {
                "year": year,
                "generated_at": datetime.utcnow().isoformat(),
                "source_key": key,
                "counts": [
                    {"code_postal": cp, "type_local": t, "count": c}
                    for (y, cp, t), c in sorted(counts.items(), key=lambda x: (-x[1], x[0][1], x[0][2]))
                ],
            }
            s3.put_object(
                Bucket=GOLD_BUCKET,
                Key=out_key,
                Body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                ContentType="application/json",
            )
            print("[GOLD_COUNT] Wrote:", f"s3://{GOLD_BUCKET}/{out_key}")
            files += 1

            if SNS_TOPIC_ARN:
                sns.publish(
                    TopicArn=SNS_TOPIC_ARN,
                    Message=json.dumps({"stage": "gold_count_by_type", "year": year, "out": out_key, "rows_in": rows_in})
                )

        except Exception as e:
            errors += 1
            print("[GOLD_COUNT][ERROR]", bucket, key, str(e))

    put_metric("GoldCountRuns", 1)
    put_metric("GoldCountFiles", files)
    put_metric("GoldCountRowsIn", rows_in)
    put_metric("GoldCountErrors", errors)
    put_metric("GoldCountDurationSec", time.time() - t0, unit="Seconds")

    return {"statusCode": 200, "files": files, "rows_in": rows_in, "errors": errors}
