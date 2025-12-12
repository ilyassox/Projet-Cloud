def handler(event, context):
    for record in event["Records"]:
        msg = record["Sns"]["Message"]
        print(f"[SNS] Message reçu : {msg}")
    return {"statusCode": 200}
