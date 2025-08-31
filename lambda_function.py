import boto3

ec2 = boto3.client('ec2')

describe_instances = ec2.describe_instances()

autoshutdown = False

for reservation in describe_instances["Reservations"]:
    for instance in reservation["Instances"]:
        if instance["State"].get('Name') == 'running':
                for tag in instance.get("Tags", []):
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
        elif instance["State"].get('Name') == 'stopped':
                for tag in instance.get("Tags", []):
                    if tag["Key"] == "Name":
                        print (tag["Value"], "is stopped")
        else:
             print ("Instance state unknown")

# Adding a comment to test PR and merge workflows
