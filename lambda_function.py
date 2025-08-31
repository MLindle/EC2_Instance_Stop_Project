import boto3

from datetime import datetime, timedelta

import json

def lambda_handler(event, context):
    execution_id = context.aws_request_id
    print(f"Execution ID: {execution_id}")
    process_instances(context, execution_id)

    q = event.get("queryStringParameters") or {}
    key   = q.get("key")
    value = q.get("value")

    return {
        "statusCode": 200,
        "body": json.dumps({"execution_id": execution_id, "key": key, "value": value})
    }
    

def process_instances(context, execution_id, key, value):

    ec2 = boto3.client('ec2')

    cloudtrail = boto3.client("cloudtrail")

    dynamodb = boto3.client('dynamodb')

    describe_instances = ec2.describe_instances()

    autoshutdown = False

    shutdown_timestamp = ''

    print (key, value)

    for reservation in describe_instances["Reservations"]:
        for instance in reservation["Instances"]:
            if instance["State"].get('Name') == 'running':
                    for tag in instance.get("Tags", []):
                        #print (tag["Key"], tag["Value"])
                        if tag["Key"] == "Name":
                            print (tag["Value"], "is running")
                        if tag["Key"] == "AutoShutdown" and tag["Value"] == "True":
                            autoshutdown = True
                        if tag["Key"] == "Environment" and tag["Value"] == "Dev" and autoshutdown == True:
                            autoshutdown = False
                            stop_instances = ec2.stop_instances(
                            InstanceIds=[
                                instance.get("InstanceId")
                            ]
                        )
                            waiter = ec2.get_waiter("instance_stopped")
                            waiter.wait(InstanceIds=[instance["InstanceId"]])
                            print(instance["InstanceId"], "stopped")
                            end_time = datetime.utcnow()
                            start_time = end_time - timedelta(hours=24)
                            response = cloudtrail.lookup_events(
                                LookupAttributes=[
                                    {"AttributeKey": "ResourceName", "AttributeValue": instance["InstanceId"]}
                                ],
                                StartTime=start_time,
                                EndTime=end_time,
                                MaxResults=5
                            )
                            for event in response["Events"]:
                                if event["EventName"] == "StopInstances":
                                    shutdown_timestamp = event['EventTime']
                                    break

                            dynamodb_write = dynamodb.put_item(
                                TableName='Stopped_Instance_Logging_Table',
                                Item={
                                    'InstanceId': {'S': instance["InstanceId"]},
                                    'TimeStamp': {'S': str(shutdown_timestamp)},
                                    'Tags': {'S': tag["Key"] + '=' + tag["Value"]},
                                    'ExecutionId' : {'S' : execution_id}
                                }
                            )
                            print("PutItem succeeded:", dynamodb_write)

            elif instance["State"].get('Name') == 'stopped':
                    for tag in instance.get("Tags", []):
                        if tag["Key"] == "Name":
                            print (tag["Value"], "is stopped")
            else:
                print ("Instance state unknown")



# Adding a comment to test PR and merge workflows
