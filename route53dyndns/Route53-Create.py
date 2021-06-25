import boto3
import botocore
import json
import time
from datetime import datetime
from botocore.exceptions import ClientError

def lambda_handler(event, context):
    route53 = boto3.client('route53')
    
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
    print(event)
    # Create Forward Lookup DNS Records from SQS messages
    # Retreive DNS information from SQS
    for r in range(len(event['Records'])):
        msg_body = event['Records'][r]['body']
        msg_body = msg_body.replace("\'","\"")
        msg_body = json.loads(msg_body)
        DNSName = msg_body['DNSName']
        DNSNameMgt = msg_body['DNSNameMgt']
        action = msg_body['action']
        func_ip = msg_body['func_ip']
        mgmt_ip = msg_body['mgmt_ip']
        hosted_zone_name = 'r53autotest.org.'
        hosted_zone_id = "Z09433722TPAXQVEZSHF7"
        OpSys = msg_body['OpSys']
        print(DNSName,action,func_ip,mgmt_ip)
        if OpSys == "CentOS" or OpSys == "RHEL":
            # Build DNS Record Sets
            if func_ip == mgmt_ip:
                rectype = ['A','CNAME']
                zone_id = hosted_zone_id
                value = [func_ip,DNSName + '.' + hosted_zone_name]
                record_name = [DNSName + '.' + hosted_zone_name, DNSNameMgt + '.' + hosted_zone_name]
            else:
                rectype = ['A','A']
                zone_id = hosted_zone_id
                value = [func_ip,mgmt_ip]
                record_name = [DNSName + '.' + hosted_zone_name, DNSNameMgt + '.'+ hosted_zone_name]
            for i in [0,1]:
                if not check_for_existing_dns(zone_id,record_name[i],rectype[i]) == 'NOERROR':
                    print("Creating DNS records for " + DNSName + ", " + DNSNameMgt )
                    change_resource_record(zone_id,action,record_name[i],rectype[i],value[i])
                    recset = [zone_id,action,record_name[i],rectype[i],value[i]]
                    print(recset)
                    time.sleep(2)
                    # Verify DNS record creation
                    print("Verifying DNS record")
                    while not check_for_existing_dns(zone_id,record_name[i],rectype[i]) == 'NOERROR':
                        print(record_name[i] + " " + "'" + rectype[i] + "'" + " record pending.")
                        time.sleep(5)
                    else:
                        print(record_name[i] + " " + "'" + rectype[i] + "'" + " record created.")

        # Create Reverse Lookup DNS Records
        rev_lookup_zone_id = 'Z02184172HLGMN6EJZKA2'
        rev_lookup_zone_name = '10.in-addr.arpa'
        rev_func_ip = msg_body['rev_func_ip']
        rev_mgmt_ip = msg_body['rev_mgmt_ip']
        rectype = 'PTR'
        zone_id = rev_lookup_zone_id
        value = [DNSName + '.' + hosted_zone_name, DNSNameMgt + '.'+ hosted_zone_name]
        record_name = [rev_func_ip + '.' + rev_lookup_zone_name, rev_mgmt_ip + '.' + rev_lookup_zone_name]

        for i in [0,1]:
            change_resource_record(zone_id,action,record_name[i],rectype,value[i])
            recset = [zone_id,action,record_name[i],rectype,value[i]]
            print(recset)
            time.sleep(5)
            # Verify DNS record creation
            print("Verifying DNS record")
            while not check_for_existing_dns(zone_id,record_name[i],rectype) == 'NOERROR':
                print(record_name[i] + " " + "'" + rectype + "'" + " record pending.")
                time.sleep(2)
            else:
                print(record_name[i] + " " + "'" + rectype + "'" + " record created.")
