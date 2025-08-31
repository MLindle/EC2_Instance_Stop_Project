# EC2 Auto-Shutdown via Lambda + HTTP API + GitHub Actions

This project deploys a Python 3.12 AWS Lambda that **stops EC2 instances** based on tags, exposes a **secured HTTP API (AWS_IAM)** to trigger it on demand, and (optionally) **logs shutdowns to DynamoDB**. It also includes **beta** (PRs) and **prod** (main) GitHub Actions workflows that package and deploy the stack.

---

## Table of Contents
- [Architecture](#architecture)
- [Required Tags](#required-tags)
- [DynamoDB Table](#dynamodb-table)
- [Configure & Deploy the CloudFormation Stack](#configure--deploy-the-cloudformation-stack)
- [GitHub Actions Workflows (How to Trigger)](#github-actions-workflows-how-to-trigger)
- [Modify the Python Logic (Instance Filtering)](#modify-the-python-logic-instance-filtering)
- [Calling the API (with/without Query Params)](#calling-the-api-withwithout-query-params)
- [Security (AWS_IAM)](#security-aws_iam)
- [Verify EC2 Stops (Console, Logs, DynamoDB)](#verify-ec2-stops-console-logs-dynamodb)
- [Sample Logs & Items](#sample-logs--items)
- [Example Test Commands (curl & Postman)](#example-test-commands-curl--postman)
- [FAQ & Tips](#faq--tips)

---

## Architecture

- **Lambda** (`lambda_function.lambda_handler`)
  - Enumerates running instances → filters by tags → calls `StopInstances`.
  - Optionally writes a record to **DynamoDB** table `Stopped_Instance_Logging_Table`.
- **EventBridge** rule triggers Lambda on schedule: `cron(0 23 * * ? *)` (11 PM UTC).
- **HTTP API (API Gateway v2)** with `$default` route → **Lambda proxy** integration.
  - Route is secured with `AuthorizationType: AWS_IAM`.
- **Lambda resource policy** allows your HTTP API stage to invoke the function.

---

## Required Tags

Instances are targeted by tags:

- `AutoShutdown=True` *(required)*
- Either:
  - **No query params:** requires `Environment=Dev` *(default behavior in code)*  
  - **With query params:** `key=<TagKey>&value=<TagValue>` *(must match the instance’s tag)*

> ✅ Only instances with **`AutoShutdown=True`** **and** the matching tag condition will be stopped.

---

## DynamoDB Table

- **Name:** `Stopped_Instance_Logging_Table`
- **Key Schema:** Partition key `InstanceId` (`S`)
- **Attributes written by Lambda:**
  - `InstanceId` (`S`)
  - `TimeStamp` (`S`) – CloudTrail “StopInstances” time
  - `Tags` (`S`) – a `key=value` snapshot written at time of stop
  - `ExecutionId` (`S`) – Lambda invocation ID

> Set **`CreateDynamo=true`** in any environment where you want logging. If `false`, the table/policy aren’t created and writes will fail.

---

## Configure & Deploy the CloudFormation Stack

The template lives at:  
`infrastructure/cloudformation/lambda-ec2-shutdown.yml`

### Parameters
- `LambdaFunctionName` – e.g., `EC2ShutdownLambda-Beta` / `EC2ShutdownLambda-Prod`
- `LambdaCodeBucket` – S3 bucket holding the zip
- `LambdaCodeKey` – S3 key (e.g., `path/to/function.zip`)
- `ApiStageName` – `beta` or `prod`
- `CreateDynamo` – `true|false`
- `CreateCloudTrailRole` – `true|false` (optional for your use case)

### Deploy via GitHub Actions (recommended)

The included workflows:
- **Zip** `lambda_function.py` → upload to S3
- **Deploy** with `aws cloudformation deploy`

**PROD** (pushes to `main`):

```bash
aws cloudformation deploy   --stack-name ${{ secrets.CF_STACK_NAME_PROD }}   --template-file infrastructure/cloudformation/lambda-ec2-shutdown.yml   --capabilities CAPABILITY_NAMED_IAM   --parameter-overrides     LambdaFunctionName=${{ secrets.LAMBDA_NAME_PROD }}     LambdaCodeBucket=${{ secrets.S3_BUCKET_PROD }}     LambdaCodeKey=${{ secrets.S3_PATH_PROD }}/function.zip     CreateDynamo=true     CreateCloudTrailRole=false     ApiStageName=prod
```

**BETA** (runs on `pull_request` to `main`):

```bash
aws cloudformation deploy   --stack-name ${{ secrets.CF_STACK_NAME_BETA }}   --template-file infrastructure/cloudformation/lambda-ec2-shutdown.yml   --capabilities CAPABILITY_NAMED_IAM   --parameter-overrides     LambdaFunctionName=${{ secrets.LAMBDA_NAME_BETA }}     LambdaCodeBucket=${{ secrets.S3_BUCKET_BETA }}     LambdaCodeKey=${{ secrets.S3_PATH_BETA }}/function.zip     CreateDynamo=true     ApiStageName=beta
```

> Ensure repository secrets are set:  
> `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`,  
> `S3_BUCKET_BETA`, `S3_PATH_BETA`, `S3_BUCKET_PROD`, `S3_PATH_PROD`,  
> `CF_STACK_NAME_BETA`, `CF_STACK_NAME_PROD`, `LAMBDA_NAME_BETA`, `LAMBDA_NAME_PROD`.

---

## Modify the Python Logic (Instance Filtering)

**Current logic (simplified):**

- If **no** query params are provided:
  - Stop **running** instances with `AutoShutdown=True` **and** `Environment=Dev`.
- If `?key=K&value=V` are provided:
  - Stop **running** instances with `AutoShutdown=True` **and** `K=V`.

**Where to tweak:**

```python
# Marks candidate instances
if tag["Key"] == "AutoShutdown" and tag["Value"] == "True":
    autoshutdown = True

# Default behavior when no key/value provided:
if tag["Key"] == "Environment" and tag["Value"] == "Dev" and autoshutdown and key is None and value is None:
    # stop instance

# Custom behavior via query params:
elif key and value and tag["Key"] == key and tag["Value"] == value and autoshutdown:
    # stop instance
```

**Optional: pre-filter via EC2 API (faster, less scanning):**

```python
describe_instances = ec2.describe_instances(
    Filters=[
        {"Name": "instance-state-name", "Values": ["running"]},
        {"Name": "tag:AutoShutdown", "Values": ["True"]},
        # {"Name": "tag:Environment", "Values": ["Dev"]},  # default behavior
    ]
)
```

**If `CreateDynamo=false`:** wrap `put_item` in `try/except` to avoid errors.

---

## Calling the API (with/without Query Params)

> Your HTTP API route uses **AWS_IAM**. All requests **must be SigV4-signed** by a principal that has `execute-api:Invoke` for your stage/route.

- **No query params** (uses default rule `Environment=Dev`):
  ```
  https://<api-id>.execute-api.us-east-2.amazonaws.com/beta
  ```

- **With query params** (custom tag match):
  ```
  https://<api-id>.execute-api.us-east-2.amazonaws.com/beta?key=Environment&value=Dev
  https://<api-id>.execute-api.us-east-2.amazonaws.com/beta/shutdown?key=AutoShutdown&value=True
  ```

---

## Security (AWS_IAM)

- The route is `AuthorizationType: AWS_IAM`, so **unsigned** requests receive **403 Forbidden**.
- Example **caller** policy (grant only this stage’s `$default`):
  ```json
  {
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": "execute-api:Invoke",
      "Resource": "arn:aws:execute-api:us-east-2:<ACCOUNT_ID>:<API_ID>/beta/$default"
    }]
  }
  ```
- The Lambda resource policy is already scoped to your API’s `$default` route.

---

## Verify EC2 Stops (Console, Logs, DynamoDB)

### EC2 Console
1. Go to **EC2 → Instances**.
2. Filter: `tag:AutoShutdown=True` (and `Environment=Dev` if using the default path).
3. After invoking the API or waiting for the schedule, watch states transition **running → stopping → stopped**.

### CloudWatch Logs (Lambda)
- Log group: `/aws/lambda/<LambdaFunctionName>`
- Expect:
  - `Execution ID: <uuid>`
  - `i-... stopped`
  - `PutItem succeeded: {...}` (if DynamoDB enabled)

### DynamoDB
- Table: `Stopped_Instance_Logging_Table`
- Use **Explore table items** in the console to view latest entries, or:
  ```bash
  aws dynamodb scan --table-name Stopped_Instance_Logging_Table
  ```

> 🔔 **Reminder:** When `CreateDynamo=true`, every successful stop is logged to **DynamoDB**.

---

## Sample Logs & Items

### Sample CloudWatch (Lambda) log lines

```
START RequestId: 6a6... Version: $LATEST
Execution ID: 6a6286d8-0e1c-4d0e-95a0-2d2d5f2d52f8
ip-10-0-3-42 is running
i-0123456789abcdef0 stopped
PutItem succeeded: {'ResponseMetadata': {'HTTPStatusCode': 200}}
END RequestId: 6a6...
REPORT RequestId: 6a6... Duration: 305 ms  Billed Duration: 400 ms  Memory Size: 128 MB  Max Memory Used: 72 MB
```

### Sample DynamoDB item

```json
{
  "InstanceId":   {"S": "i-0123456789abcdef0"},
  "TimeStamp":    {"S": "2025-08-31 21:07:13.123000+00:00"},
  "Tags":         {"S": "Environment=Dev"},
  "ExecutionId":  {"S": "6a6286d8-0e1c-4d0e-95a0-2d2d5f2d52f8"}
}
```

---

## Example Test Commands (curl & Postman)

> Replace `<api-id>`, `<ACCOUNT_ID>`, `<API_ID>`, `<STAGE>` as appropriate. Region is `us-east-2` in these examples.

### curl (Linux/macOS)

```bash
API="https://<api-id>.execute-api.us-east-2.amazonaws.com/beta?key=Environment&value=Dev"

# Requires curl >= 7.75 for --aws-sigv4
curl --aws-sigv4 "aws:amz:us-east-2:execute-api"   --user "$AWS_ACCESS_KEY_ID:$AWS_SECRET_ACCESS_KEY"   -H "x-amz-security-token: $AWS_SESSION_TOKEN"   "$API"
```

### curl (PowerShell on Windows)

> Use **`curl.exe`** (not the PowerShell alias `curl` → Invoke-WebRequest).

```powershell
$api = "https://<api-id>.execute-api.us-east-2.amazonaws.com/beta?key=Environment&value=Dev"

curl.exe --aws-sigv4 "aws:amz:us-east-2:execute-api" `
  --user "$($env:AWS_ACCESS_KEY_ID):$($env:AWS_SECRET_ACCESS_KEY)" `
  -H "x-amz-security-token: $($env:AWS_SESSION_TOKEN)" `
  $api
```

### Postman

- **Authorization** tab → Type: **AWS Signature**
- **AccessKey / SecretKey / Session Token**: your creds
- **Service Name:** `execute-api`
- **Region:** `us-east-2`
- **Method/URL:** `GET https://<api-id>.execute-api.us-east-2.amazonaws.com/beta?key=Environment&value=Dev`

---

## FAQ & Tips

- **403 Forbidden on calls?**  
  Request isn’t signed, wrong region in signer, missing session token, or caller lacks `execute-api:Invoke` for `/<stage>/$default`.

- **Where’s my API URL?**  
  API Gateway → **HTTP APIs** → your API → **Invoke URL**; append stage (`/beta` or `/prod`).

- **Prod uses `CreateDynamo=false` but code writes to DynamoDB**  
  Either set `CreateDynamo=true` in prod or wrap the `put_item` call with `try/except` to skip writes when the table/policy don’t exist.

- **Audit trail**  
  CloudTrail → filter by `EventName=StopInstances` to confirm who/when; timestamps should align with DynamoDB `TimeStamp`.

---
