import os, io, re, csv, gzip, json, time, zipfile
import boto3
from datetime import datetime
from urllib.parse import unquote_plus  # ✅ FIX

s3 = boto3.client("s3")
sns = boto3.client("sns")
cw  = boto3.client("cloudwatch")

BRONZE_BUCKET = os.environ.get("BRONZE_BUCKET", "dvf-bronze")
SILVER_BUCKET = os.environ.get("SILVER_BUCKET", "dvf-silver")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")

def put_metric(name, value, unit="Count"):
    cw.put_metric_data(
        Namespace="DVF_Pipeline",
        MetricData=[{"MetricName": name, "Value": float(value), "Unit": unit}],
    )

def snake(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s

def guess_delimiter(sample: str) -> str:
    # DVF souvent en "|" mais on sécurise
    for d in ["|", ";", "\t", ","]:
        if sample.count(d) > 5:
            return d
    return "|"

def safe_float(x):
    if x is None:
        return None
    x = str(x).strip().replace(",", ".")
    if x == "" or x.lower() == "nan":
        return None
    try:
        return float(x)
    except:
        return None

def extract_year_from_key(key: str) -> str:
    """
    Supporte:
      - bronze/year=2023/...
      - bronze/year%3D2023/...
    """
    m = re.search(r"year[=/](\d{4})", key)
    return m.group(1) if m else "unknown"

def handler(event, context):
    t0 = time.time()
    records_out = 0
    errors = 0

    print("[B2S] Event:", json.dumps(event))

    for rec in event.get("Records", []):
        bucket = rec["s3"]["bucket"]["name"]

        # ✅ FIX: key peut être URL-encoded (ex: year%3D2023)
        raw_key = rec["s3"]["object"]["key"]
        key = unquote_plus(raw_key)

        if not key.startswith("bronze/") or not key.endswith(".zip"):
            print("[B2S] Skip:", key)
            continue

        tmp_zip = "/tmp/in.zip"
        try:
            s3.download_file(bucket, key, tmp_zip)
        except Exception as e:
            errors += 1
            print("[B2S][ERROR] download_file failed:", key, str(e))
            continue

        year = extract_year_from_key(key)
        out_key = f"silver/year={year}/dvf_{year}.csv.gz"
        tmp_out = "/tmp/out.csv.gz"

        try:
            with zipfile.ZipFile(tmp_zip, "r") as zf:
                # DVF: 1 fichier .txt dedans
                txt_name = [n for n in zf.namelist() if n.endswith(".txt")]
                if not txt_name:
                    raise RuntimeError("No .txt found inside ZIP")
                txt_name = txt_name[0]

                with zf.open(txt_name, "r") as f_in, gzip.open(
                    tmp_out, "wt", newline="", encoding="utf-8"
                ) as gz_out:
                    # lire 1ère ligne pour delimiter
                    first = f_in.readline().decode("utf-8", errors="ignore")
                    delim = guess_delimiter(first)
                    header = first.strip("\n").split(delim)
                    header = [snake(h) for h in header]

                    writer = csv.writer(gz_out, delimiter=";")
                    writer.writerow(header)

                    # boucle lignes restantes
                    for raw in f_in:
                        line = raw.decode("utf-8", errors="ignore").rstrip("\n")
                        if not line:
                            continue
                        parts = line.split(delim)
                        if len(parts) != len(header):
                            errors += 1
                            continue

                        row = dict(zip(header, parts))

                        # cleaning minimal demandé: types + aberrations/missing
                        # codes postaux en string
                        if "code_postal" in row:
                            cp = row["code_postal"].strip()
                            row["code_postal"] = cp.zfill(5) if cp.isdigit() else cp

                        # valeur_fonciere numeric
                        if "valeur_fonciere" in row:
                            vf = safe_float(row["valeur_fonciere"])
                            row["valeur_fonciere"] = "" if vf is None or vf < 0 else str(vf)

                        # date_mutation (garder string)
                        if "date_mutation" in row:
                            row["date_mutation"] = row["date_mutation"].strip()

                        writer.writerow([row.get(h, "") for h in header])
                        records_out += 1

            s3.upload_file(tmp_out, SILVER_BUCKET, out_key)
            print(f"[B2S] Uploaded: s3://{SILVER_BUCKET}/{out_key}")

        except Exception as e:
            errors += 1
            print("[B2S][ERROR]", key, str(e))

    put_metric("B2SRuns", 1)
    put_metric("B2SRecordsOut", records_out)
    put_metric("B2SErrors", errors)
    put_metric("B2SDurationSec", time.time() - t0, unit="Seconds")

    if SNS_TOPIC_ARN:
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=json.dumps({
                "stage": "bronze_to_silver",
                "records_out": records_out,
                "errors": errors,
                "bucket": SILVER_BUCKET,
                "ts": datetime.utcnow().isoformat()
            })
        )

    return {"statusCode": 200, "records_out": records_out, "errors": errors}
