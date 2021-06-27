import boto3
import botocore
import json
import time
import random
from botocore.exceptions import ClientError
from datetime import datetime

def lambda_handler(event, context):
    print("Parsing Event: " + str(event['detail-type']))
    print(event['detail'])
    instance_id = event['detail']['instance-id']
    ec2_client = boto3.client('ec2')
    ec2_resource = boto3.resource('ec2')
    ec2_instance = ec2_resource.Instance(instance_id)
    sqs = boto3.client('sqs')
    dynamodb_client = boto3.client('dynamodb')
    dynamodb_resource = boto3.resource('dynamodb')
    state = event['detail']['state']
    excluded_tags = [
        'tag1',
        'tag2',
        'tag3'       
        ]

    # Send data to SQS queue in multi-tenant
    def send_sqs_mt(func_ip,mgmt_ip,queue_url,DNSName,DNSNameMgt,OpSys,action):
        # Reverse Func IP
        rev_func_ip = func_ip.split('.')
        del rev_func_ip[0:2]
        rev_func_ip.reverse()
        rev_func_ip = '.'.join(rev_func_ip)
        # Reverse Mgmt IP
        rev_mgmt_ip = mgmt_ip.split('.')
        del rev_mgmt_ip[0:2]
        rev_mgmt_ip.reverse()
        rev_mgmt_ip = '.'.join(rev_mgmt_ip)
        # Send info to MT SQS queue
        print('Sending info to SQS queue: ' + queue_url)
        msg = {
            "DNSName": DNSName,
            "DNSNameMgt": DNSNameMgt,
            "func_ip": func_ip,
            "mgmt_ip": mgmt_ip,
            "rev_func_ip": rev_func_ip,
            "rev_mgmt_ip": rev_mgmt_ip,
            "OpSys": OpSys,
            "action": action
        }
        try:
            print(str(msg))
            print("MessageGroupId: " + MessageGroupId)
            sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=(str(msg)),
                MessageGroupId=MessageGroupId)
        except botocore.exceptions.ClientError as e:
            print('Error: ' + str(e.response['Error']))

    # JSON serializer for objects not serializable by default json code
    def json_serial(obj):
        if isinstance(obj, datetime):
            serial = obj.isoformat()
            return serial
        raise TypeError ("Type not serializable")

    # Create DynamoDB table 
    def create_table(table_name):
        dynamodb_client.create_table(
            TableName=table_name,
            AttributeDefinitions=[{
                'AttributeName': 'InstanceId',
                'AttributeType': 'S'
                }],
            KeySchema=[{
                'AttributeName': 'InstanceId',
                'KeyType': 'HASH'
                }],
            ProvisionedThroughput={
                'ReadCapacityUnits': 4,
                'WriteCapacityUnits': 4
            })
        table = dynamodb_resource.Table(table_name)
        table.wait_until_exists()

    # Retrive info from DynamoDB
    def get_config_info(instance_id):
        print("Retriving 'NetworkConfig' from table 'R53DNS'")
        net = table.get_item(Key={'InstanceId': instance_id},AttributesToGet=['NetworkConfig']) # Get NetworkConfig
        net = net['Item']['NetworkConfig']
        net = json.loads(net) # Convert string dict to dict
        print("Retriving 'DNSName' from table 'R53DNS'")
        name = table.get_item(Key={'InstanceId': instance_id},AttributesToGet=['DNSName']) # Get DNSName
        DNSName = name['Item']['DNSName']
        print("Retriving 'OpSys' from table 'R53DNS'")
        opsys = table.get_item(Key={'InstanceId': instance_id},AttributesToGet=['OpSys']) # Get OpSys
        OpSys = opsys['Item']['OpSys']
        return net, DNSName, OpSys

    #### Main Logic ####
    # Exclude all instances with any string match listed in 'excluded_tags'
    exclude = [string for string in excluded_tags if(string in str(ec2_instance.tags))]
    if bool(exclude) == True:
        print("One or more instance tags match exlcuded tags. Instance skipped.")
    else:
        # Look for DynamoDB table and create of it doesn't exist
        tables = dynamodb_client.list_tables()
        if not 'R53DNS' in tables['TableNames']:
            create_table('R53DNS')

        # Look for 'InstanceId': instance_id item in R53DNS table
        table = dynamodb_resource.Table('R53DNS')
        print("Retriving 'InstanceID' item from table 'R53DNS")
        tbl_chk = table.get_item(Key={'InstanceId': instance_id})
        if not instance_id in str(tbl_chk): # Populate DynamoDB with configuration info if it doesn't exist in 'R53DNS' table
            print("'InstanceId' item not found. Creating 'InstanceId' item in table 'R53DNS'")
            print("Waiting for 'AMIOperatingSys' tag")
            w = 0
            while not 'AMIOperatingSys' in str(ec2_instance.tags):
                time.sleep(random.randint(120,240+w))
                ec2_instance = ec2_resource.Instance(instance_id)
                w = random.randint(30,90)
            else:
                print("Parsing 'DNSName' and 'AMIOperatingSys' from EC2 Tags")
                for tag in ec2_instance.tags:
                    if tag['Key'] == 'DNSName':
                        DNSName = tag['Value']
                    elif tag['Key'] == 'AMIOperatingSys':
                        OpSys = tag['Value']
                instance = ec2_client.describe_instances(InstanceIds=[instance_id])
                instance.pop('ResponseMetadata') # Remove metadata from response
                network_config = instance['Reservations'][0]['Instances'][0]['NetworkInterfaces']
                network_dump = json.dumps(network_config,default=json_serial) # Serialize data before JSONifying
                network_config = str(network_dump) # Convert dict to string
                # Put config information into DynamoDB table
                print("Putting 'NetworkConfig' and 'DNSName' into table 'R53DNS")
                table.put_item(Item={'InstanceId': instance_id,'NetworkConfig': network_config,'DNSName': DNSName,'OpSys': OpSys})
                # Retrieve config information from DynamoDB table
                info = get_config_info(instance_id)
                net = info[0]
                DNSName = info[1]
                DNSNameMgt = DNSName + "-mgt"
                OpSys = info[2]
        else:
            # Retrieve config information from DynamoDB table
            info = get_config_info(instance_id)
            net = info[0]
            DNSName = info[1]
            DNSNameMgt = DNSName + "-mgt"
            OpSys = info[2]

        # Parse IP information from net
        print("Gathering IP information for func and mgmt")
        for i in range(len(net)):
            if len(net) > 1:
                if net[i]['Attachment']['DeviceIndex'] == 0:
                    func_ip = net[i]['PrivateIpAddress']
                elif net[i]['Attachment']['DeviceIndex'] == 1:
                    mgmt_ip = net[i]['PrivateIpAddress']
            elif len(net) == 1:
                func_ip = mgmt_ip = net[i]['PrivateIpAddress']

        # Determine Instance State and set variables as appropiate
        if state == "shutting-down":
            action = 'DELETE'
            queue_url = 'https://sqs.us-east-1.amazonaws.com/123456789012/Route53-Delete-SQS.fifo'
            MessageGroupId = 'r53AutomationDelete'
            print("Action: " + action)
        elif state == "pending": 
            action = 'CREATE'
            queue_url = 'https://sqs.us-east-1.amazonaws.com/123456789012/Route53-Create-SQS.fifo'
            MessageGroupId = 'r53AutomationCreate'
            print("Action: " + action)

        # Send info to MT SQS queue
        send_sqs_mt(func_ip,mgmt_ip,queue_url,DNSName,DNSNameMgt,OpSys,action)

        # Delete table items from DynamoDB
        if state == "shutting-down":
            print("EC2 State = 'shutting-down'")
            print("Removing 'InstanceId' item from 'R53DNS' Table")
            table.delete_item(Key={'InstanceId': instance_id})
