import boto3
import os
import uuid
import json
import time ### NEW V2 CODE ###
import datetime
import logging
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from botocore.config import Config ### NEW V2 CODE ###
from assume_role import assume_role

logger = logging.getLogger()
logger.setLevel(logging.INFO)

### BEGIN NEW V2 CODE ###
# Variables used for the retry logic:
sleep_timer = 10 # Number of seconds to wait between custom retries
max_retries = 20 # max_retries used for both custom and built-in retry logic
config = Config(
   retries = {
      'max_attempts': max_retries,
      'mode': 'standard'
   }
)
### END NEW V2 CODE ###

stsclient = boto3.client('sts')
shclient = boto3.client('securityhub')
dbclient = boto3.client('dynamodb', config=config) ### NEW V2 CODE ###
dbresource = boto3.resource('dynamodb')
lambdaclient = boto3.client('lambda')
# eksclient = boto3.client('eks')
ec2client = boto3.client('ec2')
ec2resource = boto3.resource('ec2')
emrclient = boto3.client('emr')

db_table = os.environ['DYNAMODB_TABLE']
db_index = os.environ['DYNAMODB_INDEX']
db_key = os.environ['DYNAMODB_KEY']
excluded_accounts = os.environ['EXCLUDED_ACCOUNTS']  # comma separated list of account IDs
x_account_role = os.environ['X_ACCOUNT_ROLE']
hub_account = stsclient.get_caller_identity()['Account']


def lambda_handler(event, context):
    source = event.get('source', False)
    print(json.dumps(event, indent=2, default=str))
    account_id = event.get('account_id',
                           None)  # ***********DYNAMIC-Live*************** (must use the Event Rule to trigger function)
    org_name = event.get('account_name', None) ### NEW V2 CODE ###
    ### If 'ALL' is passed in for 'EXCLUDED_ACCOUNTS', then execute a test run against only the org-SBX or ADO11 account
    ### Intended for testing or troubleshooting purposes without calling all accounts or having to explicitly exclude all accounts
    ### This IF statement can be removed later for cleaner code with no impact to the function
    if excluded_accounts == 'ALL':
        account_id = '123456789012'  # org-SBX
        source = 'TestRun'  # If source is 'aws.events' it will loop through all accounts - don't do that!

    ### BEGIN NEW V2 CODE - Removed account list table scan for every invocation ###
    accts = get_account_list()

    # If account_id is not present, it's the orchestration invocation, so process the list of accounts
    if not account_id and source == 'aws.events':
        accts = get_account_list() ### NEW V2 CODE ###
        excluded_account_list = excluded_accounts.replace(' ', '')
        excluded_account_list = excluded_account_list.split(',')
        logger.info(f'Begin invoking lambda functions on {len(accts)} accounts')
        logger.info(f'There are {len(excluded_account_list)} excluded accounts: {excluded_accounts}')
        for acct in accts:
            acct_id = acct['ID']['S']
            acct_name = acct['Name']['S']
            payload = {
                'account_id': acct_id,
                'account_name': acct_name
            }
            try:
                lambda_response = lambdaclient.invoke(FunctionName=context.function_name,
                                                      InvocationType='Event', Payload=json.dumps(payload, default=str))
                # logger.debug(lambda_response)
            except Exception:
                logger.exception(f'Error invoking the Lambda function for account: {acct_id}')
    elif not account_id and not source:
        raise Exception('Missing required parameter "account_id"')
    else:
        # '''Assume role on target account (accountId)'''
        if account_id in excluded_accounts:
            logger.info(f'Bypassing excluded account: {org_name}/{account_id}')
        else:
            # Process the roles in the account for the invoked lambda from the 'accts' FOR loop above
            result = main(account_id, org_name)
            logger.info(result)


def main(account_id, org_name):
    assumed_stsclient = ''
    assumed_shclient = ''
    assumed_emrclient = ''

    ### // TEMP IF STATEMENT USED FOR TESTING - remove this IF statement later and shift tabs accordingly
    # if account_id == '663386616047' or account_id == '925130777241': # TEMP for testing
    ###

    if account_id == hub_account:
        # Hub (multitenant) account uses the local Lambda connection
        assumed_stsclient = stsclient
        assumed_shclient = shclient
        assumed_emrclient = emrclient
    else:
        # Assume a role in the child account
        assumed_session = assume_role(account_id, x_account_role)
        assumed_stsclient = assumed_session.client('sts')
        assumed_shclient = assumed_session.client('securityhub')
        assumed_emrclient = assumed_session.client('emr')


    # Sanity check to make sure the client connection context is in the correct account
    assumed_account_id = assumed_stsclient.get_caller_identity()['Account']
    if assumed_account_id == account_id:
        db_items = query_db_items(account_id, db_table, db_index)
        clusters = get_clusters(assumed_emrclient)
        logger.info(f'Begin processing {len(clusters)} clusters in the {org_name}/{account_id} account')
        for cluster in clusters:
            cluster_id = cluster.get('Id', None)
            cluster_arn = cluster.get('ClusterArn', None)
            primary_tech_poc = None
            secondary_tech_poc = None
            matches = []
            compliance_status = ''
            bootstrap_scripts = get_cluster_bootstrap(cluster_id, assumed_emrclient)

            for match in bootstrap_scripts:
                if 's3://emr-boot-strap/' in match:
                    matches.append(match)
            if len(matches) > 0:
                compliance = 'COMPLIANT'
                compliance_status = 'PASSED'
                print(f'{cluster_id} is {compliance}')
            else:
                compliance = 'NON_COMPLIANT'
                compliance_status = 'FAILED'
                print(f'{cluster_id} is {compliance}')

            # Get Tags
            try:
                tags = assumed_emrclient.describe_cluster(ClusterId=cluster_id)['Cluster']['Tags']
                if len(tags) > 0:
                    for tag in tags:
                        try:
                            if tag['Key'] == 'PrimaryTechPOC':
                                primary_tech_poc = tag['Value']
                        except:
                            pass
                        try:
                            if tag['Key'] == 'SecondaryTechPOC':
                                secondary_tech_poc = tag['Value']
                        except:
                            pass
            except:
                tags = []
                print('No tags present')
                pass

            tag_map = map_tags(tags)

            sechub_action = ''
            finding_id = ''
            db_item = ''
            db_item_found = False
            # Set the DynamoDB record TTL to 90 days in seconds (7776000)
            int_ttl = int(datetime.datetime.utcnow().timestamp()) + 7776000

            (db_item, db_item_found) = get_db_item(db_items, cluster_id)

            if db_item_found:
                try:
                    finding_id = db_item['Finding ID']
                    db_compliance_status = db_item['Compliance Status']
                except Exception:
                    logger.exception('Error locating existing Security Hub finding ID for DynamoDB item:')
                    logger.error(db_item)

                # If we have a record of an existing role, check for a compliance change
                if compliance_status == db_compliance_status:
                    # No compliance change, so just update dynamo_db and sec hub udpated date using existing finding ID
                    # The possible actions are listed below
                    # 'new' (new record), 'update' (update existing finding), 'archive' (archive because of compliance change or deletion)
                    sechub_action = 'update'
                    import_sechub_finding(
                        assumed_shclient, cluster_arn, cluster_id, account_id, org_name, 
                        compliance_status, sechub_action, finding_id, tag_map
                    )
                else:
                    # There is a compliance change, so archive the old finding ID, then create a new finding ID and update dynamoDB
                    sechub_action = 'archive'
                    import_sechub_finding(
                        assumed_shclient, cluster_arn, cluster_id, account_id, org_name, 
                        compliance_status, sechub_action, finding_id, tag_map
                    )
                    finding_id = uuid.uuid1()
                    sechub_action = 'new'
                    import_sechub_finding(
                        assumed_shclient, cluster_arn, cluster_id, account_id, org_name, 
                        compliance_status, sechub_action, finding_id, tag_map
                    )
            else:
                # No existing role in dynamoDB, so create a new SecHub finding ID and new dynamoDB record
                finding_id = uuid.uuid1()
                sechub_action = 'new'
                import_sechub_finding(
                    assumed_shclient, cluster_arn, cluster_id, account_id, org_name, 
                    compliance_status, sechub_action, finding_id, tag_map
                )

            ### BEGIN NEW V2 CODE ###
            retry_count = 0
            retry = write_to_dynamodb(
                cluster_arn, cluster_id, account_id, org_name, primary_tech_poc,
                secondary_tech_poc, compliance_status, finding_id, int_ttl
            )
            while retry:
                retry_count += 1
                logger.info(f'Custom retry count: {retry_count} of {max_retries}')
                if retry_count > max_retries:
                    logger.error(f'Exceeded the number of custom retries writing to DynamoDB for resource {cluster_arn}. Try increasing the number of retries or the provisioned capacity for the table {db_table}')
                    break
                else:
                    logger.info(f'Waiting {sleep_timer} seconds before retrying')
                    time.sleep (sleep_timer)
                    logger.info(f'Retrying write to DynamoDB for resource {cluster_arn}')
                    retry = write_to_dynamodb(
                        cluster_arn, cluster_id, account_id, org_name, primary_tech_poc,
                        secondary_tech_poc, compliance_status, finding_id, int_ttl
                    )
            ### END NEW V2 CODE ###

    else:
        logger.error(f'The account ({account_id}) does not match the assumed account ({assumed_account_id})')

    ###
    ### // END TEMP IF STATEMENT USED FOR TESTING
    ###
    return (f'Function complete for {org_name}/{account_id}')


def get_account_list():
    # Scan Table for Active OU Accounts
    response = dbclient.scan(
        TableName='org-Organizations-OUAccountsTable-Table',
        ExpressionAttributeNames={"#St": "Status", "#Us": "Usage"},
        FilterExpression="#St = :x AND #Us = :y",
        ExpressionAttributeValues={":x": {"S": "ACTIVE"}, ":y": {"S": "Standard"}}
    )
    accts = response['Items']
    return accts


def get_org_name(account_id, accts):
    # Lookup the org name for the account ID
    for acct in accts:
        if account_id == acct['ID']['S']:
            return (acct['Name']['S'])


def query_db_items(account_id, db_table, db_index):
    # Query Table for existing findings
    table = dbresource.Table(db_table)
    query_response = table.query(
        TableName=db_table,
        IndexName=db_index,
        Select='ALL_ATTRIBUTES',
        KeyConditionExpression=Key('Account ID').eq(account_id)
    )
    count = query_response['Count']
    scanned_count = query_response['ScannedCount']
    if count == scanned_count:
        db_items = query_response['Items']
        return db_items
    else:
        raise Exception(
            f'Query count ({count}) and scanned count ({scanned_count}) do not match. Some DB items may be missing from the query result.')


def map_tags(tags):
    tag_map = {}
    for tag in tags:
        for k,v in tag.items():
            if k == 'Key':
                new_k = v
            elif k == 'Value':
                new_v = v
        tag_map[new_k] = new_v
    return tag_map


def get_clusters(emr_client):
    response = emr_client.list_clusters()
    clusters = response['Clusters']
    return clusters


def get_cluster_bootstrap(cluster_id, emr_client):
    paginator = emr_client.get_paginator('list_bootstrap_actions')
    response_iterator = paginator.paginate(
        ClusterId=cluster_id
    )
    script_paths = []
    for bootstrap_actions in response_iterator:
        for actions in bootstrap_actions['BootstrapActions']:
            script_paths.append(actions["ScriptPath"])
    return script_paths


def get_db_item(db_items, id):
    db_item_found = False
    db_item = ''
    for db_item in db_items:
        db_id = db_item[db_key]
        if db_id == id:
            db_item_found = True
            return (db_item, db_item_found)
    db_item = ''
    return (db_item, db_item_found)


def import_sechub_finding(
        assumed_shclient, cluster_arn, cluster_id, account_id, org_name, 
        compliance_status, sechub_action, finding_id, tag_map
):
    #########################################################
    # Possible values for the 'sechub_action' parameter
    # 'new' (new record OR compliance status change) = import as a new finding
    # 'update' (update existing finding) = import using existing finding ID
    # 'archive' (compliance status changed OR resource deleted) = import existing finding and set record_state to 'ARCHIVED'
    #########################################################

    lambda_name = os.environ['AWS_LAMBDA_FUNCTION_NAME']
    region = os.environ['AWS_REGION']
    rule_id = 'org-EMR-2'
    version = '1.0'
    company_name = 'org'
    d = datetime.datetime.utcnow()
    sh_date_created = d.replace(tzinfo=datetime.timezone.utc).isoformat()  # only used if SecHub imports a new record
    sh_date_updated = d.replace(tzinfo=datetime.timezone.utc).isoformat()
    description = 'Checks the EMR cluster to ensure it used the correct bootstrap hardening script'
    generator_id = f'{rule_id}/{lambda_name}'
    id = f'securityhub/{region}/{account_id}/custom/v/{version}/{rule_id}/finding/{finding_id}'
    product_arn = f'arn:aws:securityhub:{region}:{account_id}:product/{account_id}/default'  # default only one that works
    product_name = lambda_name
    recommendation_text = 'See AWS instructions for using bootstrap scripts in EMR clusters.'
    recommendation_url = 'https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-plan-bootstrap.html#bootstrapUses'
    record_state = 'ACTIVE'
    resource_type = 'Other'
    resource_id = cluster_arn
    resource_partition = 'aws'
    resource_region = region
    schema = '2018-10-08'
    title = 'org EMR Uses Bootstrap Script'
    types = 'Software and Configuration Checks/Vulnerabilities/CVE'
    wf_status = 'NEW'
    severity = ''

    if compliance_status == 'FAILED':
        severity = os.environ['SEVERITY']
    elif compliance_status == 'PASSED':
        wf_status = 'RESOLVED'  # Docs say this should get set automatically by the compliance_status - but it's not
        severity = 'INFORMATIONAL'
    elif compliance_status == 'NOT_AVAILABLE':
        severity = 'INFORMATIONAL'

    if sechub_action == 'new':
        logger.info(
            f'Creating {compliance_status} Security Hub finding for resource: {resource_id}')
    elif sechub_action == 'archive':
        record_state = 'ARCHIVED'
        logger.info(f'Archiving {compliance_status} Security Hub finding for resource: {resource_id}')
    elif sechub_action == 'update':
        logger.info(
            f'No status change for {compliance_status} Security Hub finding for resource: {resource_id}')

    findings = [{
        'SchemaVersion': schema,
        'Id': id,
        'ProductArn': product_arn,
        'GeneratorId': generator_id,
        'AwsAccountId': account_id,
        'Compliance': {
            'Status': compliance_status
        },
        'CreatedAt': sh_date_created,
        'UpdatedAt': sh_date_updated,
        'Severity': {
            'Label': severity,
            'Original': severity
        },
        'Types': [
            types
        ],
        'Title': title,
        'Description': description,
        'Remediation': {
            'Recommendation': {
                'Text': recommendation_text,
                'Url': recommendation_url
            }
        },
        'ProductFields': {
            'org/custom/account-name': org_name,
            'org/custom/rule-version': version,
            'org/custom/rule-id': rule_id,
            'org/custom/emr-bootstrap-compliance': compliance_status,
            'aws/securityhub/ProductName': product_name,
            'aws/securityhub/CompanyName': company_name,
            'aws/securityhub/FindingId': id
        },
        'Resources': [{
            'Type': resource_type,
            'Id': resource_id,
            'Partition': resource_partition,
            'Region': resource_region,
            'Tags': tag_map,
            'Details': {
                resource_type: {
                    'ClusterId': cluster_arn,
                    'ClusterName': cluster_id,
                }
            }

        }],
        'Workflow': {
            'Status': wf_status
        },
        'RecordState': record_state
    }]

    if not tag_map:
        del findings[0]['Resources'][0]['Tags']

    try:
        import_response = assumed_shclient.batch_import_findings(
            Findings=findings
        )
        # logger.debug('Response from import finding:')
        # logger.debug(import_response)
        if import_response['FailedCount'] != 0:
            failed_findings = import_response['FailedFindings'][0]
            logger.error(f'Error importing finding: {id}')
            logger.error(failed_findings)
            logger.error(f'The error occurred for EMR Cluster: {cluster_arn}')
            logger.error(f'The finding data that failed to import is below:')
            logger.error(findings)

    except ClientError as e:
        # The RateLimit = 10/s and BurstLimit = 30/s
        # For now, let's log the issue and determine if we need to reprocess or wait until the next invocation.
        # If we add retry logic, we need to make sure we don't enter an infinite loop of retries
        # by counting and setting a max number of retries and/or by doing a bulk import of findings
        logger.exception(f'ClientError: {e}')
        logger.error(f'The error occurred for EMR Cluster: {cluster_arn}')
        logger.error(f'The finding data that failed to import is below:')
        logger.error(findings)
    except Exception as x:
        logger.exception(f'Exception: {x}')
        logger.error(f'The error occurred for EMR Cluster: {cluster_arn}')
        logger.error(f'The finding data that failed to import is below:')
        logger.error(findings)

    return {
        'statusCode': 200,
    }


def write_to_dynamodb(
        cluster_arn, cluster_id, account_id, org_name, primary_tech_poc,
        secondary_tech_poc, compliance_status, finding_id, int_ttl
):
    db_item = {
        'Cluster Arn': {
            'S': cluster_arn,
        },
        db_key: {
            'S': cluster_id,
        },
        'Account ID': {
            'S': account_id,
        },
        'Account Name': {
            'S': org_name,
        },
        'Primary Tech POC': {
            'S': str(primary_tech_poc),
        },
        'Secondary Tech POC': {
            'S': str(secondary_tech_poc),
        },
        'Compliance Status': {
            'S': compliance_status,
        },
        'Finding ID': {
            'S': str(finding_id),
        },
        'TTL': {
            'N': str(int_ttl),
        },
    }

    try:
        dynamo_response = dbclient.put_item(
            Item=db_item,
            ReturnConsumedCapacity='TOTAL',
            TableName=db_table,
        )
        ### BEGIN NEW V2 CODE ###
        retry = False
        retry_attempts = dynamo_response['ResponseMetadata']['RetryAttempts']
        if (float(retry_attempts) / float(max_retries) * 100) >= 75:
            # If the retry attempt finishes within 75% of the max retries, throw a warning and consider
            # increasing the max_retries threshold or increase the provisioned capacity of the table
            logger.warning(f'Auto-retry attempts reached {retry_attempts} of {max_retries} max for {cluster_arn}')
        http_status_code = dynamo_response['ResponseMetadata']['HTTPStatusCode']
        if http_status_code == 200:
            return retry
        else:
            logger.error(f'Error (HTTP Status Code: {http_status_code}) writing to DynamoDB for resource: {cluster_arn}')
            logger.error(db_item)
            return retry
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ProvisionedThroughputExceededException':
            logger.warning(f'{error_code} writing to DynamoDB for resource {cluster_arn}. Entering custom retry pattern.')
            retry = True
            return retry
        else:
            logger.error(f'Unhandled client error writing the following record to DynamoDB for resource {cluster_arn}: {e}')
            logger.error(db_item)
            retry = False
            return retry
    except Exception as x:
        logger.exception(f'Unhandled exception writing the following record to DynamoDB for resource {cluster_arn}: {x}')
        logger.error(db_item)
        retry = False
        return retry
        ### END NEW V2 CODE ###
