import boto3
import botocore
import json
import time
from datetime import datetime
from botocore.exceptions import ClientError

def lambda_handler(event, context):
    route53 = boto3.client('route53')
    sqs = boto3.client('sqs')
    queue_url = 'https://sqs.us-east-1.amazonaws.com/663386616047/Route53-Delete-HIDS-SQS.fifo'

    # Define Check For Existing DNS Record
    def check_for_existing_dns(zone_id,record_name,rectype):
        dns_chk = route53.test_dns_answer(
            HostedZoneId=zone_id,
            RecordName=record_name,
            RecordType=rectype
        )
        result = dns_chk['ResponseCode']
        return result

    # Define Function: Change Resource Record 
    def change_resource_record(zone_id,action,record_name,rectype,value):
        try:
            rec_change = route53.change_resource_record_sets(HostedZoneId=zone_id,ChangeBatch={
                "Changes": [{
                    "Action": action,
                    "ResourceRecordSet": {
                        "Name": record_name,
                        "Type": rectype,
                        "TTL": 300,
                        "ResourceRecords": [{"Value": value}]
            }}]})
            print(rec_change)
        except botocore.exceptions.ClientError as e:
            print("Error: " + str(e.response['Error']))

    #### Main Logic ####
    # Create Forward Lookup DNS Records from SQS messages
    get_attrib = sqs.get_queue_attributes(QueueUrl=queue_url,AttributeNames=['ApproximateNumberOfMessages'])
    msg_count = get_attrib['Attributes']['ApproximateNumberOfMessages']
    msg_count = int(msg_count)
    if msg_count > 0:
        while msg_count > 0:
            # Retreive DNS information from SQS
            msg_count = msg_count - 1
            get_msg = sqs.receive_message(QueueUrl=queue_url,MaxNumberOfMessages=1)
            rcpt_handle = get_msg['Messages'][0]['ReceiptHandle']
            msg_body = get_msg['Messages'][0]['Body']
            msg_body = msg_body.replace("\'","\"")
            msg_body = json.loads(msg_body)
            HCQISName = msg_body['HCQISName']
            HCQISNameMgt = msg_body['HCQISNameMgt']
            action = msg_body['action']
            func_ip = msg_body['func_ip']
            mgmt_ip = msg_body['mgmt_ip']
            OpSys = msg_body['OpSys']
            hosted_zone_name = "ado11.r53test.org."
            hosted_zone_id = "Z0362588342LPQBCO20TC"
            print(HCQISName,action,func_ip,mgmt_ip)
            if OpSys == "CentOS" or OpSys == "RHEL":
                # Build DNS Record Sets
                if func_ip == mgmt_ip:
                    rectype = ['A','CNAME']
                    zone_id = hosted_zone_id
                    value = [func_ip,HCQISName + '.' + hosted_zone_name]
                    record_name = [HCQISName + '.' + hosted_zone_name, HCQISNameMgt + '.' + hosted_zone_name]
                else:
                    rectype = ['A','A']
                    zone_id = hosted_zone_id
                    value = [func_ip,mgmt_ip]
                    record_name = [HCQISName + '.' + hosted_zone_name, HCQISNameMgt + '.'+ hosted_zone_name]
                for i in [0,1]:
                    if check_for_existing_dns(zone_id,record_name[i],rectype[i]) == 'NOERROR':
                        print("Deleting DNS records for " + HCQISName + ", " + HCQISNameMgt )
                        change_resource_record(zone_id,action,record_name[i],rectype[i],value[i])
                        time.sleep(0.3)
                        recset = [zone_id,action,record_name[i],rectype[i],value[i]]
                        print(recset)
                        # Verify DNS record creation
                        print("Verifying DNS record")
                        while check_for_existing_dns(zone_id,record_name[i],rectype[i]) == 'NOERROR':
                            print(record_name[i] + " " + "'" + rectype[i] + "'" + " record pending.")
                            time.sleep(5)
                        else:
                            print(record_name[i] + " " + "'" + rectype[i] + "'" + " record deleted.")
            # Delete PTR Records
            rev_lookup_zone_id = 'Z03540141GKWIKLPTXOMS'
            rev_lookup_zone_name = '10.in-addr.arpa'
            rev_func_ip = msg_body['rev_func_ip']
            rev_mgmt_ip = msg_body['rev_mgmt_ip']
            rectype = 'PTR'
            zone_id = rev_lookup_zone_id
            value = [HCQISName + '.' + hosted_zone_name, HCQISNameMgt + '.'+ hosted_zone_name]
            record_name = [rev_func_ip + '.' + rev_lookup_zone_name, rev_mgmt_ip + '.' + rev_lookup_zone_name]
            for i in [0,1]:
                if check_for_existing_dns(zone_id,record_name[i],rectype) == 'NOERROR':
                    print("Deleting DNS records for " + HCQISName + ", " + HCQISNameMgt )
                    change_resource_record(zone_id,action,record_name[i],rectype,value[i])
                    recset = [zone_id,action,record_name[i],rectype,value[i]]
                    print(recset)
                    time.sleep(2)
                    print("Verifying DNS record deletion")
                    while check_for_existing_dns(zone_id,record_name[i],rectype) == 'NOERROR':
                        print(record_name[i] + " " + "'" + rectype + "'" + " record pending.")
                        time.sleep(5)
                    else:
                        print(record_name[i] + " " + "'" + rectype + "'" + " record deleted.")
            # Delete SQS Message
            try:
                sqs.delete_message(QueueUrl=queue_url,ReceiptHandle=rcpt_handle)
            except botocore.exceptions.ClientError as e:
                print("Error: " + str(e.response['Error']))
    else:
        print("Route 53 Management SQS queue has 0 Messages")
