import boto3

dbclient = boto3.client('dynamodb')
db_table = 'autotag-dynamodb'
db_items = [
    {
        'BillingCode': {'S': 'C-012345'},
        'AutotagId': {'S': 'AT-123'},
        'BusinessUnit': {'S': 'Bus Unit 1'},
        'Environment': {'S': 'Non-Prod'},
        'Owner': {'S': 'owner.email@orgname.com'},
        'Project': {'S': 'Project Alpha'},
        'ProjectManager': {'S': 'proj.mgr@orgname.com'},
        'TechnicalContact': {'S': 'tech.contact@orgname.com'}
    },
    {
        'BillingCode': {'S': 'D-456789'},
        'AutotagId': {'S': 'AT-124'},
        'BusinessUnit': {'S': 'Bus Unit 1'},
        'Environment': {'S': 'Prod'},
        'Owner': {'S': 'owner.email@orgname.com'},
        'Project': {'S': 'Project Alpha'},
        'ProjectManager': {'S': 'proj.mgr@orgname.com'},
        'TechnicalContact': {'S': 'tech.contact@orgname.com'}
    }
]

for item in db_items:
    dbclient.put_item(Item=item,ReturnConsumedCapacity='TOTAL',TableName=db_table)
