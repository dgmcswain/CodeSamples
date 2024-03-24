import boto3
import botocore
import sys
import time
from botocore.exceptions import ClientError
from datetime import datetime

### Global Variables
instance_id = sys.argv[1]

ec2_client = boto3.client('ec2')
elb_client = boto3.client('elb')
alb_client = boto3.client('elbv2')

##### FUNCTIONS ######
# Define Log function
def log(msg):
    print(f'{datetime.UTC()}Z: {msg}')

def migration_action_skip(instance_id):
    try:
        log(f"Tenancy Migration skipped for: {instance_id}")
    except ClientError as e:
        log(f"Error completing migration instance {instance_id}: {e.response['Error']}")
        log('{"Error": "1"}')
    exit()

##### Get EC2 System Information #####
# Get EC2 tenancy
def get_ec2_tenancy(instance_id):
    try:
        ec2 = ec2_client.describe_instances(InstanceIds=[instance_id])
        ec2_tenancy = ec2['Reservations'][0]['Instances'][0]['Placement']['Tenancy']
        log(f"EC2 Instance Tenancy: {ec2_tenancy}")
    except ClientError as e:
        log(f"Error parsing EC2 tenancy: {e.response['Error']}")
    return ec2_tenancy

### Get EC2 Termination Protection 
def get_ec2_term_protection(instance_id):
    try:
        term = ec2_client.describe_instance_attribute(Attribute='disableApiTermination',InstanceId=instance_id)
        term_protection = term['DisableApiTermination']['Value']
    except ClientError as e:
        log(f"Error parsing EC2 tenancy: {e.response['Error']}")
    return term_protection

### Get EC2 Instance type
def get_ec2_type(instance_id):
      try:
          ec2 = ec2_client.describe_instances(InstanceIds=[instance_id])
          ec2_type = ec2['Reservations'][0]['Instances'][0]['InstanceType']
          log(f"EC2 Instance Type: {ec2_type}")
      except ClientError as e:
          log(f"Error parsing EC2 Instance Type: {e.response['Error']}")
      return ec2_type

### Get EC2 Tags
def get_ec2_tags(instance_id):
    try:
        desc_instance = ec2_client.describe_instances(InstanceIds=[instance_id])
        tag_info = desc_instance['Reservations'][0]['Instances'][0]['Tags']
        keys_to_remove = ["aws:cloudformation:logical-id", "aws:cloudformation:stack-id", "aws:cloudformation:stack-name"]
        tags = [tag for tag in tag_info if tag['Key'] not in keys_to_remove]
        log(f"Getting EC2 tag information for: {instance_id}")
    except KeyError as e:
        tags = None
        log(f"Error parsing EC2 Tags: {e.response['Error']}")
    return tags

### GET EC2 IAM profile
def get_iam_profile(instance_id):
    try:
        iam = ec2_client.describe_instances(InstanceIds=[instance_id])
        iam_profile = iam['Reservations'][0]['Instances'][0]['IamInstanceProfile']['Arn']
        log(f"EC2 IAM profile: {iam_profile}")
    except ClientError as e:
        log(f"Error parsing IAM profile {e.response['Error']}")
    except KeyError:
        iam_profile = None
        pass
    return iam_profile

### Stop EC2 ###
def stop_ec2(instance_id):
    try:
        ec2_client.stop_instances(InstanceIds=[instance_id])
        log(f"Stopping EC2 instance: {instance_id}")
    except ClientError as e:
        log(f"Error stopping the instance {instance_id}: {e.response['Error']}")

### GET Source EC2 status
def get_ec2_status(instance_id):
    ec2_status = None
    try:
        ec2 = ec2_client.describe_instances(InstanceIds=[instance_id])
        ec2_status = ec2['Reservations'][0]['Instances'][0]['State']['Name']
        log(f"EC2 Status: {ec2_status}")    
    except ClientError as e:
        log(f"Error parsing EC2 state: {e.response['Error']}")
    return ec2_status

### Create AMI
def create_ami(instance_id):
    try:
        image = ec2_client.create_image(
            Description=f'Copy of {instance_id}',
            DryRun=False,
            InstanceId=instance_id,
            Name=f'Copy of {instance_id}',
            NoReboot=True,
        )
        time.sleep(5)
        ami_id = image['ImageId']
        log(f"Creating AMI ID: {ami_id}")
    except ClientError as e:
        log(f"Error creating AMI: {e.response['Error']}")
    return ami_id

### Get AMI Status
def get_ami_create_status(ami_id):
    try:
        ami = ec2_client.describe_images(ImageIds=[ami_id])
        ami_status = ami['Images'][0]['State']
        log(f"AMI Status: {ami_status}")
    except ClientError as e:
        log(f"Error parsing AMI creation state {ami_id}: {e.response['Error']}")
    return ami_status

### Process ENIs for migration
def get_net_config(instance_id):
    eni_list = []
    eni_dict = {}
    ec2 = ec2_client.describe_instances(InstanceIds=[instance_id])
    for eni in ec2['Reservations'][0]['Instances'][0]['NetworkInterfaces']:
        eni_id = eni['NetworkInterfaceId']
        eni_desc = ec2_client.describe_network_interfaces(NetworkInterfaceIds=[eni_id])
        dev_index = eni_desc['NetworkInterfaces'][0]['Attachment']['DeviceIndex']
        # Build config for launch
        eni_dict = {'DeleteOnTermination': False, 'DeviceIndex': dev_index, 'NetworkInterfaceId': eni_id}
        eni_list.append(eni_dict)
    return eni_list
    
### Test EC2 Launch permissions
def test_ec2_launch_dryrun(net_config,ami_id,ec2_type,iam_profile,ec2_tags):
    try:  
        launch_params = {
            'NetworkInterfaces': net_config,
            'ImageId': ami_id,
            'MinCount': 1,
            'MaxCount': 1,
            'InstanceType': ec2_type,
            'Placement': {'Tenancy': 'default'},
            'TagSpecifications': [{'ResourceType': 'instance', 'Tags': ec2_tags}],
            'DryRun': True
        }
        if iam_profile:
            launch_params['IamInstanceProfile'] = {'Arn': iam_profile}        
        ec2_client.run_instances(**launch_params)             
    except ClientError as e:
        if e.response['Error']['Message'] == "Request would have succeeded, but DryRun flag is set.":
            log(f"Test EC2 launch Succeeded: {e.response['Error']['Message']}")
            return True
        else:
            log(f"Test EC2 launch failed: {e.response['Error']['Message']}")
            return False

### Launch New Instance
def launch_new_ec2(net_config,ami_id,ec2_type,ec2_tags,iam_profile):
    try:  
        launch_params = {
            'NetworkInterfaces': net_config,
            'ImageId': ami_id,
            'MinCount': 1,
            'MaxCount': 1,
            'InstanceType': ec2_type,
            'Placement': {'Tenancy': 'default'},
            'TagSpecifications': [{'ResourceType': 'instance', 'Tags': ec2_tags}],
        }
        if iam_profile:
            launch_params['IamInstanceProfile'] = {'Arn': iam_profile}        
        launch = ec2_client.run_instances(**launch_params)
        new_instance_id = launch['Instances'][0]['InstanceId']
        log(f"Launching new EC2: {new_instance_id}")
    except ClientError as e:
        log(f"Error launching EC2: {e.response['Error']}")
    return new_instance_id

### Detach ENIs from EC2
def detach_enis(instance_id):
    try:
        ec2 = ec2_client.describe_instances(InstanceIds=[instance_id])
        for eni in ec2['Reservations'][0]['Instances'][0]['NetworkInterfaces']:
            eni_id = eni['NetworkInterfaceId']
            eni_desc = ec2_client.describe_network_interfaces(NetworkInterfaceIds=[eni_id])
            eni_ip = eni_desc['NetworkInterfaces'][0]['PrivateIpAddress']
            attach_id = eni_desc['NetworkInterfaces'][0]['Attachment']['AttachmentId']
            ec2_client.detach_network_interface(AttachmentId=attach_id)
            log(f"Detaching {eni_id} with IP {eni_ip} from {instance_id}")
    except ClientError as e:
        log(f"Error detaching ENI: {e.response['Error']}")

#### Terminate Source EC2
# def terminate_ec2(instance_id):
#     try:
#         ec2_client.terminate_instances(InstanceIds=[instance_id])
#     except ClientError as e:
#         log(f"Error terminating EC2 instance {instance_id}: {e.response['Error']}")

### Enable Termination protection
def enable_termination_protection(new_instance_id):
    if new_instance_id:
        try:
            ec2_client.modify_instance_attribute(InstanceId=new_instance_id,DisableApiTermination={'Value': True})
        except ClientError as e:
            log(f"Error enabling termination protection: {e.response['Error']}")                

### Get New EC2 status
def new_get_ec2_status(new_instance_id):
    global new_ec2_status
    new_ec2_status = None
    if new_instance_id:
        try:
            new_ec2 = ec2_client.describe_instances(InstanceIds=[new_instance_id])
            new_ec2_status = new_ec2['Reservations'][0]['Instances'][0]['State']['Name']
            log(f"New EC2 Status: {new_ec2_status}")
        except ClientError as e:
            log(f"Error parsing new EC2 state: {e.response['Error']}")
        return new_ec2_status

### Reboot new instance
def new_ec2_reboot(new_instance_id):
    if new_instance_id:
        try:
            ec2_client.reboot_instances(InstanceIds=[new_instance_id])
            log(f"Rebooting New EC2: {new_instance_id}")
        except ClientError as e:
            log(f"Error rebooting new EC2 instance: {e.response['Error']}")

### Process ELB Association
def process_elb_association(instance_id,new_instance_id):
    load_balancers = elb_client.describe_load_balancers()['LoadBalancerDescriptions']
    for elb in load_balancers:
        # Handle cases where there might be no instances
        instances = elb.get('Instances', [])
        for ec2_id in instances:
            if ec2_id['InstanceId'] == instance_id:
                elb_name = elb['LoadBalancerName']
                log(f"Instance: {instance_id} attached to ELB: {elb_name}")
                try:
                    elb_client.register_instances_with_load_balancer(LoadBalancerName=elb_name, Instances=[{'InstanceId': new_instance_id}])
                    elb_client.deregister_instances_from_load_balancer(LoadBalancerName=elb_name, Instances=[{'InstanceId': instance_id}])
                    log(f"Registering instance {new_instance_id} with ELB: {elb_name}")
                    log(f"De-Registering instance {instance_id} from ELB: {elb_name}")
                except ClientError as e:
                    log(f"Error registering {new_instance_id} with ELB: {e.response['Error']}")

### Process ALB Association
def process_alb_association(instance_id, new_instance_id):
    target_groups = alb_client.describe_target_groups()['TargetGroups']
    try:
        for target_group in target_groups:
            target_group_arn = target_group['TargetGroupArn']
            target_health = alb_client.describe_target_health(TargetGroupArn=target_group_arn)['TargetHealthDescriptions']
            for target in target_health:
                target_id = target['Target']['Id']
                if target_id == instance_id:
                    log(f"Instance: {instance_id} attached to Target Group: {target_group['TargetGroupName']}")
                    alb_client.register_targets(TargetGroupArn=target_group_arn, Targets=[{'Id': new_instance_id, 'Port': target['Target']['Port']}])
                    log(f"Registering instance {new_instance_id} with Target Group: {target_group['TargetGroupName']}")
    except botocore.exceptions.ClientError as e:
        log(f"Error registering {new_instance_id} with Target Group: {e.response['Error']}")

### Migration rollback
def migration_action_rollback(ami_id):
    try:
        ec2_client.deregister_image(ImageId=ami_id)
        log(f"De-Registering AMI id: {ami_id}")
    except ClientError as e:
        log(f"Error De-Registering AMI {ami_id}: {e.response['Error']}")

### Main Function
def main():
    start_time = datetime.now()
    ec2_tenancy = get_ec2_tenancy(instance_id)
    ec2_term_protection = get_ec2_term_protection(instance_id)
    iam_profile = get_iam_profile(instance_id)
    ami_state = None
    if ec2_tenancy == 'default':
        print('======================================================================')
        print(f'Instance {instance_id} already configured for default tenancy')
        print('Aborting ...')
        print('======================================================================')
        migration_action_skip()

    elif ec2_term_protection:
        print('========================================================================================================')
        print(f'Instance {instance_id} is configured with Termination Protection. Please disable and try again.')
        print('Aborting ...')
        print('========================================================================================================')
        migration_action_skip()  

    else:
        print('======================================================================')
        print(f'Proceeding with Tenancy Migration of EC2 instance: {instance_id}')
        print('======================================================================')
        ec2_type = get_ec2_type(instance_id)
        ec2_status = get_ec2_status(instance_id)
        ec2_tags = get_ec2_tags(instance_id)
        # Start the migration process
        stop_ec2(instance_id)
        while not ec2_status == 'stopped':
            time.sleep(10)
            ec2_status = get_ec2_status(instance_id)
        ami_id = create_ami(instance_id)
        time.sleep(10)     
        while not ami_state == 'available':
            time.sleep(10)
            ami_state = get_ami_create_status(ami_id)
        net_config = get_net_config(instance_id)
        # Execute Dryrun test EC2 launch prior to target EC2 termination
        test_ec2_launch_status = test_ec2_launch_dryrun(net_config,ami_id,ec2_type,iam_profile,ec2_tags)
        # Dryrun succeeds
        if test_ec2_launch_status:
            detach_enis(instance_id)
            # ec2_status = get_ec2_status(instance_id)
            # while not ec2_status == 'terminated':
            #     time.sleep(10)
            #     ec2_status = get_ec2_status(instance_id)
            new_instance_id = launch_new_ec2(net_config,ami_id,ec2_type,ec2_tags,iam_profile)
            # new_ec2_tenancy = get_new_ec2_tenancy(new_instance_id)
            while not new_ec2_status == 'running':
                time.sleep(10)
                new_get_ec2_status(new_instance_id)
            print(f'Enabling Termination Protection for {new_instance_id}')
            enable_termination_protection(new_instance_id)
            new_ec2_reboot(new_instance_id)
            # Update Load balancer Targets
            process_elb_association(instance_id,new_instance_id)
            process_alb_association(instance_id,new_instance_id)
            migration_duration = datetime.now() - start_time
            print('=================================================')
            print(f'Migration of {instance_id} Successful')
            print('=================================================')
            print(f'New Instance ID: {new_instance_id}')
            print(f'Migration Duration: {str(migration_duration)}')
        # Dryrun fails
        else:
            print('=================================================')
            print(f'-  Migration of {instance_id} Failed.           -')
            print('-  EC2 Test Launch unsuccessful. Please verify  -')
            print('-  IAM session has permissions in IAM policy    -')
            print('-  attached to IAM user or instance role.       -')
            print('-  Rolling EC2 back to pre-migration state.     -')
            print('=================================================')
            migration_action_rollback(ami_id)

if __name__ =='__main__':
    main()
