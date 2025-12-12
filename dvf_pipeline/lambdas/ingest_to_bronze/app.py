import os, re, time, json
import urllib.request
import boto3
from datetime import datetime

DVF_URLS = [
    {"year": "2025", "url": "https://static.data.gouv.fr/resources/demandes-de-valeurs-foncieres/20251018-234902/valeursfoncieres-2025-s1.txt.zip"},
    {"year": "2024", "url": "https://static.data.gouv.fr/resources/demandes-de-valeurs-foncieres/20251018-234857/valeursfoncieres-2024.txt.zip"},
    {"year": "2023", "url": "https://static.data.gouv.fr/resources/demandes-de-valeurs-foncieres/20251018-234851/valeursfoncieres-2023.txt.zip"}
]

s3 = boto3.client("s3")
sns = boto3.client("sns")
cw  = boto3.client("cloudwatch")

BRONZE_BUCKET = os.environ.get("BRONZE_BUCKET", "dvf-bronze")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")

def put_metric(name, value, unit="Count"):
    cw.put_metric_data(
        Namespace="DVF_Pipeline",
        MetricData=[{"MetricName": name, "Value": float(value), "Unit": unit}],
    )

def handler(event, context):
    t0 = time.time()
    ok, fail = 0, 0

    target_year = None
    if isinstance(event, dict):
        target_year = event.get("year")

    urls = DVF_URLS
    if target_year:
        urls = [u for u in DVF_URLS if u["year"] == str(target_year)]

    for item in urls:
        year = item["year"]
        url  = item["url"]
        local_path = f"/tmp/valeursfoncieres-{year}.zip"
        try:
            print(f"[INGEST] Download {url} -> {local_path}")
            urllib.request.urlretrieve(url, local_path)
            key = f"bronze/year={year}/valeursfoncieres-{year}.zip"
            print(f"[INGEST] Upload s3://{BRONZE_BUCKET}/{key}")
            s3.upload_file(local_path, BRONZE_BUCKET, key)
            ok += 1
        except Exception as e:
            fail += 1
            print("[INGEST][ERROR]", str(e))

    put_metric("IngestRuns", 1)
    put_metric("IngestFilesOK", ok)
    put_metric("IngestFilesFail", fail)
    put_metric("IngestDurationSec", time.time() - t0, unit="Seconds")

    if SNS_TOPIC_ARN:
        sns.publish(TopicArn=SNS_TOPIC_ARN, Message=json.dumps({"stage":"ingest_to_bronze","ok":ok,"fail":fail}))

    return {"statusCode": 200, "ok": ok, "fail": fail, "year": target_year}
