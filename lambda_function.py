import boto3

ec2 = boto3.client('ec2')

describe_instances = ec2.describe_instances()

for reservation in describe_instances["Reservations"]:
    for instance in reservation["Instances"]:
        if instance["State"].get('Name') == 'running':
            #print (instance.get("InstanceId"))
            for tag in instance.get("Tags", []):
                print (tag["Value"], "is running")
                stop_instances = ec2.stop_instances(
                InstanceIds=[
                    instance.get("InstanceId")
                ]
            )
        elif instance["State"].get('Name') == 'stopped':
                for tag in instance.get("Tags", []):
                    print (tag["Value"], "is stopped")
        else:
             print ("Instance state unknown")