import boto3

def lambda_handler(event, context):
    ec2 = boto3.resource('ec2')
    sqs = boto3.client('sqs')
    queue_url = 'https://sqs.us-east-1.amazonaws.com/123456789012/ADCleanup-SQS'
    instance_id = event['detail']['instance-id']
    account_id = event['account']
    ec2instance = ec2.Instance(instance_id)
    ado_id = 'Blank'
    instance_name = 'Blank'
    instance_os = 'Blank'
    cleanup_exclude = 'Blank'

    for tag in ec2instance.tags:
        if tag['Key'] == 'ServerName':
            instance_name = tag['Value']
        elif tag['Key'] == 'AMIOperatingSys':
            instance_os = tag['Value']
        elif tag['Key'] == 'ADO':
            ado_id = tag['Value']
        elif tag['Key'] == 'ExcludeFromCleanup':
            cleanup_exclude = tag['Value']

    if not instance_name == 'Blank':
        sqs.send_message(
            QueueUrl=queue_url,
            DelaySeconds=10,
            MessageBody=(str({
            "ADO": ado_id,
            "AccountId": account_id,
            "InstanceId": instance_id,
            "HCQISName": instance_name,
            "OS": instance_os,
            "Exclude": cleanup_exclude
            }))
        )