import boto3
import logging
import multiprocessing as mp
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Define boto3 clients
sts_client = boto3.client('sts')
ec2_client = boto3.client('ec2')
ddb_client = boto3.client('dynamodb')
org_client = boto3.client('organizations')
tag_client = boto3.client('resourcegroupstaggingapi')

# Assume role of spoke account for boto3 session
def assume_role(account_id,x_acct_role):
    logger.info(f"Assuming IAM role '{x_acct_role}' in account {account_id}")
    session = {}
    role_arn = f"arn:aws:iam::{account_id}:role/{x_acct_role}"

    try:
        assumed_role_object = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName=f"{x_acct_role}_acct_{account_id}"
        )
    except Exception:
        logger.exception(f'Error assuming role: {role_arn}')

    session['key']    = assumed_role_object['Credentials']['AccessKeyId']
    session['secret'] = assumed_role_object['Credentials']['SecretAccessKey']
    session['token']  = assumed_role_object['Credentials']['SessionToken']

    return session

def get_region_list():
    region_list = []
    desc_regions = ec2_client.describe_regions()
    for region in desc_regions['Regions']:
        region_name = region['RegionName']
        region_list.append(region_name)
    return region_list

def get_account_list():
    paginator = org_client.get_paginator('list_accounts')
    response_iterator = paginator.paginate()
    account_ids = []
    for accounts in response_iterator:
        for account in accounts['Accounts']:
            account_id = account['Id']
            account_ids.append(account_id)
    return account_ids

# Create a list of resources that have AutotagId tag  
def get_tagged_resources(session,prim_key):
    resource_arns=[]
    try:
        response = session.get_resources(
            TagFilters=[
                {
                    'Key': 'AutotagId',
                    'Values': [prim_key]
                }
            ]   
        )

        for resource in response['ResourceTagMappingList']:
            resource_arns.append(resource['ResourceARN'])
    except:
        pass
    return resource_arns

# Tag resources that have AutotagId tag
def tag_resources(session,tags,resource_arns,account_id,prim_key,region):
    if len(resource_arns) > 0:
        logger.info(f"Collected resources in region {region}, account {account_id} that match {prim_key} Project-specific tags")
        logger.info(f"Tagging resources in region {region}, account {account_id} with {prim_key} Project-specific tags")
        res_tags = {}
        for tag in tags:
            res_tags[tag['Key']]=tag['Value']  
        response = session.tag_resources(
            ResourceARNList=resource_arns,
            Tags=res_tags
        )
    else:
        return

# Scan DynamoDB for all items and build a JSON object with tagging info
def scan_dynamodb(dynamodb_table):
    logger.info(f"Scanning DynamoDB table {dynamodb_table} for Project-specific tagging information")
    scan = ddb_client.scan(
        TableName=dynamodb_table
    )
    dynamodb_scan = {}
    for item in scan['Items']:
        prim_key = item['AutotagId']['S']
        tags = [
            {'Key':'BillingCode','Value': item['BillingCode']['S']},
            {'Key':'BusinessUnit','Value': item['BusinessUnit']['S']},
            {'Key':'Environment','Value': item['Environment']['S']},
            {'Key':'Owner','Value': item['Owner']['S']},
            {'Key':'Project','Value': item['Project']['S']},
            {'Key':'ProjectManager','Value': item['ProjectManager']['S']},
            {'Key':'TechnicalContact','Value': item['TechnicalContact']['S']}
        ]
        dynamodb_scan[prim_key]={}
        dynamodb_scan[prim_key]['tags'] = tags
    return dynamodb_scan

# Split large list into an iterable object of smaller lists of length 'new_size'
def split_list(input_list, new_size):
    n = 0
    list_array = {}
    for i in range(0, len(input_list), new_size):
        split_list = yield input_list[i:i + new_size]
     
    for batch in split_list:
        list_array[n] = batch
        n = n + 1
    
    return list_array

def lambda_handler(event, context):
    # Set variables
    hub_account    = sts_client.get_caller_identity()['Account']
    x_acct_role    = 'autotag-assumed-role'
    dynamodb_table = 'autotag-dynamodb'
    dynamodb_scan  = scan_dynamodb(dynamodb_table)
    region_list    = get_region_list()
    account_ids    = get_account_list()
    excluded_accts = ("123546789012","456879120345")

    """"
    ### Suspended Organization Accounts ###
    123546789012 
    456879120345
    """

    def proccess_list(accounts): 
        for account_id in accounts:
            if not account_id in excluded_accts:
                # Test to make sure the mgmt account isn't trying to assume a remote session for the local account
                if account_id == hub_account:
                # Hub (Old Dev) account uses the local Lambda connection
                    tag_session = tag_client
                else:
                # Assume a role in the remote account
                    assumed_role = assume_role(account_id,x_acct_role)

                for prim_key in dynamodb_scan:
                    # account_ids = dynamodb_scan[prim_key]['AccountIds']
                    tags = dynamodb_scan[prim_key]['tags']        

                    for region in region_list:
                        if not region in ("ap-east-1"):
                            session = boto3.Session(
                                aws_session_token=assumed_role['token'],
                                aws_access_key_id=assumed_role['key'],
                                aws_secret_access_key=assumed_role['secret'],
                                region_name=region
                            )
                            tag_session = session.client('resourcegroupstaggingapi')
                            resource_arns = get_tagged_resources(tag_session,prim_key)
                            tag_resources(tag_session,tags,resource_arns,account_id,prim_key,region)

    # Main Logic
    # Build an array of lists
    list_array = split_list(account_ids, 10)

    # Create a seperate process for each list in list_array
    procs = []
    try:
        for accounts in list_array:
            p = mp.Process(target=proccess_list, args=(accounts,))
            procs.append(p)
            p.start()
            time.sleep(2)
    except:
        pass
    for proc in procs:
        proc.join()
