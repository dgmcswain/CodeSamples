import boto3
import socket

def lambda_handler(event, context):
    # Define AWS service objects for EC2, SSM, and SNS
    ec2 = boto3.client('ec2')
    ssm = boto3.client('ssm')
    sns = boto3.client('sns')

    # Define S3 bucket location information for SSM logging
    s3_output_bucket = 'org-process-automation'
    s3_output_key_prefix = '/ADCleanupLogs/'

    # Get EC2 instance information with filters
    filters = [{'Name': 'private-ip-address', 'Values': socket.gethostbyname_ex('ad.domain.org')[2]}]
    ec2_info = ec2.describe_instances(Filters=filters)

    # Find the first running instance ID (or None)
    target_ec2 = next((instance['InstanceId'] for reservation in ec2_info['Reservations'] for instance in reservation['Instances'] if instance['State']['Name'] == 'running'), None)

    # Run ADCleanup SSM document against target_ec2
    # If there are no running EC2 instances associated with FQDN of the AD domain, send SNS alert
    if target_ec2:
        ssm.send_command(
            InstanceIds=[target_ec2],
            DocumentName='ADCleanup-SSM',
            OutputS3BucketName=s3_output_bucket,
            OutputS3KeyPrefix=s3_output_key_prefix
        )
        print(f"Running SSM document 'ADCleanup-SSM' on instance {target_ec2}")
    else:
        print("No running target instances detected. Aborting.")
        sns.publish(
            TopicArn='ADCleanup-SNS',
            Message='No running target instances detected for AD Cleanup. Aborting.',
            Subject='AD Cleanup Log',
        )
