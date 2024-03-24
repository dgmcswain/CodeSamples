import boto3
import sys
from botocore.exceptions import ClientError
from datetime import datetime

### Global Variables
global instance_id
instance_id = sys.argv[1]
client = boto3.client('ec2')

##### FUNCTIONS ######
### Define Log function ###
def log(msg):
    print(f'{datetime.UTC().isoformat()}Z: {msg}')

#### Get EC2 System Information ###
# Get EC2 tenancy
def get_ec2_tenancy(instance_id):
    if instance_id:
        try:
            ec2 = client.describe_instances(InstanceIds=[instance_id])
            ec2_tenancy = ec2['Reservations'][0]['Instances'][0]['Placement']['Tenancy']
        except ClientError as e:
            log("Error parsing EC2 tenancy: {}".format(e.response['Error']))
        return ec2_tenancy

# Get EC2 Termination Protection 
def get_ec2_term_protection(instance_id):
        if instance_id:
            try:
                term = client.describe_instance_attribute(Attribute='disableApiTermination',InstanceId=instance_id)
                term_protection = term['DisableApiTermination']['Value']
            except ClientError as e:
                log("Error parsing EC2 tenancy: {}".format(e.response['Error']))
            return term_protection

### Main Function
def main():
    ec2_tenancy = get_ec2_tenancy(instance_id)
    ec2_termination_protection = get_ec2_term_protection(instance_id)

    print('\n Validating EC2 Instance ' + instance_id)
    print(' ===============================================')
    if ec2_tenancy == 'dedicated':
        print(' Dedicated Tenancy: Passed!')
    else:
        print(' Dedicated tenancy: Failed. Instance not configured for dedicated tenancy.')

    if not ec2_termination_protection:
        print(' Termination Protection disabled: Passed!')
    else:
        print(' Termination Protection enabled: Failed. Please disable Termination Protection.')

    print(' ===============================================')
    print(' Validation of ' + instance_id + ' Complete.')
    print(' ===============================================')
    
    if ec2_tenancy == 'dedicated' and ec2_termination_protection == False:
        print(' EC2 Instance Migration Validation: Passed \n')
    else:
        print(' EC2 Instance Migration Validation: Failed \n')

if __name__ =='__main__':
    main()
