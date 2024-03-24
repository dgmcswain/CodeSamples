import boto3


def lambda_handler(event, context):
    ec2 = boto3.resource('ec2')
    sqs = boto3.client('sqs')
    queue_url = 'https://sqs.us-east-1.amazonaws.com/123456789012/ADCleanup-SQS'

    instance_id = event['detail']['instance-id']
    account_id = event['account']

    # Use dictionary comprehension to extract data from tags in one step
    tags_dict = {tag['Key']: tag['Value'] for tag in ec2.Instance(instance_id).tags}
    instance_name = tags_dict.get('ServerName', 'Blank')
    instance_os = tags_dict.get('AMIOperatingSys', 'Blank')
    ado_id = tags_dict.get('ADO', 'Blank')
    cleanup_exclude = tags_dict.get('ExcludeFromCleanup', 'Blank')

    if instance_name != 'Blank':
        message_body = {
            "ADO": ado_id,
            "AccountId": account_id,
            "InstanceId": instance_id,
            "InstanceName": instance_name,
            "OS": instance_os,
            "Exclude": cleanup_exclude
        }

        sqs.send_message(QueueUrl=queue_url, DelaySeconds=10, MessageBody=json.dumps(message_body))
