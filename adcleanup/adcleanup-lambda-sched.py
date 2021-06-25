import boto3
import botocore
import socket

def lambda_handler(event, context):
    # Define AWS service objects for EC2, SSM, and SNS
    ec2 = boto3.client('ec2')
    ssm = boto3.client('ssm')
    sns = boto3.client('sns')

    # Define S3 bucket location information for SSM logging
    s3_output_bucket = 'Process Automation'
    s3_output_key_prefix = '/ADCleanupLogs/'

    # Query DNS for IP addresses associted with FQDN of AD domain
    domain_hosts = socket.gethostbyname_ex('ad.domain.org')[2]

    # Set filter for describe_instances() API call using IPs associated with FQDN of AD domain
    ec2_info = ec2.describe_instances(Filters=[{'Name': 'private-ip-address','Values': domain_hosts }])

    # Get EC2 instance IDs and store in list
    ec2_ids = []
    for i in range(len(ec2_info)):
        instance_id = ec2_info['Reservations'][i]['Instances'][0]['InstanceId']
        ec2_ids.append(instance_id)

    # Get EC2 instance status and assign target_ec2 as first running instance
    for i in range(len(ec2_ids)):
        ec2_status = ec2_info['Reservations'][i]['Instances'][0]['State']['Name']
        if ec2_status == 'running':
            target_ec2 = ec2_ids[i]
            break
        else:
            target_ec2 = None

    # Run ADCleanup SSM document against target_ec2
    # If there are no running EC2 instances associated with FQDN of the AD domain, send SNS alert
    if not target_ec2 == None:
        ssm.send_command(
            InstanceIds=[target_ec2],
            DocumentName='ADCleanup-SSM',
            OutputS3BucketName=s3_output_bucket,
            OutputS3KeyPrefix=s3_output_key_prefix
            )
        print("Running SSM document 'ADCleanup-SSM' on instance {}".format(target_ec2))
    else:
        print("No running target instances detected. Aborting.")
        sns.publish(
            TopicArn='ADCleanup-SNS',
            Message='No running target instances detected for AD Cleanup. Aborting.',
            Subject='AD Cleanup Log',
            )
