import boto3
import botocore
import sys
import time
import json
import logging
from botocore.exceptions import ClientError
from datetime import datetime

### Global Variables
instance_id = sys.argv[1]

ec2_client = boto3.client('ec2')
elb_client = boto3.client('elb')
alb_client = boto3.client('elbv2')

##### FUNCTIONS ######
# Define Log function
def log(error):
    print(f'{datetime.utcnow()}Z: {error}')

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
    tag_info = None
    try:
        tags = ec2_client.describe_instances(InstanceIds=[instance_id])
        tag_info = tags['Reservations'][0]['Instances'][0]['Tags']
        for i in range(len(tag_info)):
            if tag_info[i]['Key'] == "aws:cloudformation:logical-id":
                del tag_info[i]
                break
            for j in range(len(tag_info)):
                if tag_info[j]['Key'] == "aws:cloudformation:stack-id":
                    del tag_info[j]
                    break
                for k in range(len(tag_info)):
                    if tag_info[k]['Key'] == "aws:cloudformation:stack-name":
                        del tag_info[k]
                        break
        log(f"Getting EC2 tag information for: {instance_id}")
    except ClientError as e:
        log(f"Error parsing EC2 Tags: {e.response['Error']}")
    return tag_info

### GET EC2 IAM profile
def get_iam_profile(instance_id):
    iam_profile = None
    try:
        iam = ec2_client.describe_instances(InstanceIds=[instance_id])
        iam_profile = iam['Reservations'][0]['Instances'][0]['IamInstanceProfile']['Arn']
        log(f"EC2 IAM profile: {iam_profile}")
    except ClientError as e:
        log(f"Error parsing IAM profile {e.response['Error']}")
    except KeyError:
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
            Description='Copy of ' + instance_id,
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
    global ami_state
    ami_state = None
    if ami_id:  
        try:
            ami = ec2_client.describe_images(ImageIds=[ami_id])
            ami_status = ami['Images'][0]['State']
            log(f"AMI Status: {ami_status}")
        except ClientError as e:
            log(f"Error parsing AMI creation state {ami_id}: {e.response['Error']}")
        ami_state = ami_status
        time.sleep(10)
        return ami_state

### Process ENIs for migration
def process_enis_for_migraiton(instance_id):
    net_int_list = []
    net_int_dict = {}
    ec2desc = ec2_client.describe_instances(InstanceIds=[instance_id])
    for eni in ec2desc['Reservations'][0]['Instances'][0]['NetworkInterfaces']:
        eni_id = eni['NetworkInterfaceId']
        eni_desc = ec2_client.describe_network_interfaces(NetworkInterfaceIds=[eni_id])
        eni_ip = eni_desc['NetworkInterfaces'][0]['PrivateIpAddress']
        attach_id = eni_desc['NetworkInterfaces'][0]['Attachment']['AttachmentId']
        dev_index = eni_desc['NetworkInterfaces'][0]['Attachment']['DeviceIndex']
        # Build config for launch
        net_int_dict = {'DeleteOnTermination': False, 'DeviceIndex': dev_index, 'NetworkInterfaceId': eni_id}
        net_int_list.append(net_int_dict)
        # Mark ENIs for no deletion
        try:
            ec2_client.modify_network_interface_attribute(Attachment={'AttachmentId': attach_id, 'DeleteOnTermination': False},NetworkInterfaceId=eni_id)
            log(f"Setting DeleteOnTermination to False on ENI: {eni_id}, IP: {eni_ip}")
        except:
            pass
    return net_int_list
    
### Test EC2 Launch permissions
def test_ec2_launch_dryrun(net_cfg_list,ami_id,ec2_type,iam_profile,ec2_tags):
    try:  
        if iam_profile == None:
            ec2_client.run_instances(
                NetworkInterfaces=net_cfg_list,
                ImageId=ami_id,
                MinCount=1,
                MaxCount=1,
                InstanceType=ec2_type,
                Placement={'Tenancy': 'default'},
                TagSpecifications=[{'ResourceType': 'instance','Tags': ec2_tags}],
                DryRun=True
            )
        else:
            ec2_client.run_instances(
                NetworkInterfaces=net_cfg_list,
                ImageId=ami_id,
                MinCount=1,
                MaxCount=1,
                InstanceType=ec2_type,
                Placement={'Tenancy': 'default'},
                TagSpecifications=[{'ResourceType': 'instance','Tags': ec2_tags}],
                IamInstanceProfile={'Arn': iam_profile},
                DryRun=True
            )                
    except ClientError as e:
        if e.response['Error']['Message'] == "Request would have succeeded, but DryRun flag is set.":
            log(f"Test EC2 launch Succeeded: {e.response['Error']['Message']}")
            return True
        else:
            log(f"Test EC2 launch failed: {e.response['Error']['Message']}")
            return False

### Terminate Source EC2
def terminate_ec2(instance_id):
    try:
        ec2_client.terminate_instances(InstanceIds=[instance_id])
    except ClientError as e:
        log(f"Error terminating EC2 instance {instance_id}: {e.response['Error']}")

### Launch New Instance
def launch_new_ec2(net_cfg_list,ami_id,ec2_type,ec2_tags,iam_profile):
    try:  
        if iam_profile == None:
            launch = ec2_client.run_instances(
                NetworkInterfaces=net_cfg_list,
                ImageId=ami_id,
                MinCount=1,
                MaxCount=1,
                InstanceType=ec2_type,
                Placement={'Tenancy': 'default'},
                TagSpecifications=[{'ResourceType': 'instance','Tags': ec2_tags}],
            )
        else:
            launch = ec2_client.run_instances(
                NetworkInterfaces=net_cfg_list,
                ImageId=ami_id,
                MinCount=1,
                MaxCount=1,
                InstanceType=ec2_type,
                Placement={'Tenancy': 'default'},
                TagSpecifications=[{'ResourceType': 'instance','Tags': ec2_tags}],
                IamInstanceProfile={'Arn': iam_profile},
            )
        new_instance_id = launch['Instances'][0]['InstanceId']
        log(f"Launching new EC2: {launch_id}")
    except ClientError as e:
        log(f"Error launching EC2: {e.response['Error']}")
    return new_instance_id

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
            new_get_ec2_status = new_ec2['Reservations'][0]['Instances'][0]['State']['Name']
            log(f"New EC2 Status: {new_get_ec2_status}")               
        except ClientError as e:
            log(f"Error parsing new EC2 state: {e.response['Error']}")
        new_ec2_status = new_get_ec2_status
        return new_ec2_status

### Get New EC2 tenancy
# def get_new_ec2_tenancy(new_instance_id):
#     try:
#         new_ec2 = ec2_client.describe_instances(InstanceIds=[new_instance_id])
#         new_ec2_tenancy = new_ec2['Reservations'][0]['Instances'][0]['Placement']['Tenancy']
#     except ClientError as e:
#         log(f"Error parsing new EC2 tenancy: {e.response['Error']}")
#     return new_ec2_tenancy

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
    elb_list = elb_client.describe_load_balancers()
    for elbs in elb_list['LoadBalancerDescriptions']:
        for ec2_id in elbs['Instances']:
            if ec2_id['InstanceId'] == instance_id:
                elb_name = elbs['LoadBalancerName']
                log(f"Instance: " + instance_id + " attached to ELB:" + elb_name)
                try:
                    elb_client.register_instances_with_load_balancer(LoadBalancerName=elb_name,Instances=[{'InstanceId': new_instance_id}])
                    elb_client.deregister_instances_from_load_balancer(LoadBalancerName=elb_name,Instances=[{'InstanceId': instance_id}])
                    log(f"Registering instance {new_instance_id} with ELB: {elb_name}")
                    log(f"De-Registering instance {instance_id} from ELB: {elb_name}")
                except ClientError as e:
                    log(f"Error registering {new_instance_id} with ELB: {e.response['Error']}")

### Process ALB Association
def process_alb_association(instance_id,new_instance_id):
    alb_list = alb_client.describe_target_groups()
    for targets in alb_list['TargetGroups']:
        tg_name = targets['TargetGroupName']
        target_arn = targets['TargetGroupArn']
        target_id = alb_client.describe_target_health(TargetGroupArn=target_arn)
        for target in target_id['TargetHealthDescriptions']:
            tg_id = target['Target']['Id']
            tg_port = target['Target']['Port']
            if tg_id == instance_id:
                log(f"Instance: {instance_id} attached to Target Group: {tg_name}")
                try:
                    alb_client.register_targets(TargetGroupArn=target_arn,Targets=[{'Id': new_instance_id,'Port': tg_port}])
                    log(f"Registering instance {new_instance_id} with Target Group: {tg_name}")       
                except ClientError as e:
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

    if ec2_tenancy == 'default':
        print('======================================================================')
        print('Instance ' + instance_id + ' already configured for default tenancy')
        print('Aborting ...')
        print('======================================================================')
        migration_action_skip()

    elif ec2_term_protection == True:
        print('========================================================================================================')
        print('Instance ' + instance_id + ' is configured with Termination Protection. Please disable and try again.')
        print('Aborting ...')
        print('========================================================================================================')
        migration_action_skip()  

    else:
        print('======================================================================')
        print('Proceeding with Tenancy Migration of EC2 instance: ' + instance_id)
        print('======================================================================')
        ec2_type = get_ec2_type(instance_id)
        ec2_status = get_ec2_status(instance_id)
        ec2_tags = get_ec2_tags(instance_id) 
        
        stop_ec2(instance_id)
        while ec2_status !== 'stopped':
            time.sleep(10)
            ec2_status = get_ec2_status(instance_id)
        ami_id = create_ami(instance_id)
        time.sleep(10)
        ami_state = None
        while ami_state !=='available':
            time.sleep(10)
            ami_state = get_ami_create_status(ami_id)
        # Execute Dryrun test EC2 launch prior to target EC2 termination
        net_cfg_list = process_enis_for_migraiton(instance_id)
        test_ec2_launch_status = test_ec2_launch_dryrun(net_cfg_list,ami_id,ec2_type,iam_profile,ec2_tags)
        # Dryrun succeeds
        if test_ec2_launch_status == True:
            terminate_ec2(instance_id)
            ec2_status = get_ec2_status(instance_id)
            while ec2_status !== 'terminated':
                time.sleep(5)
                ec2_status = get_ec2_status(instance_id)
            new_instance_id = launch_new_ec2(net_cfg_list,ami_id,ec2_type,ec2_tags,iam_profile)
            # new_ec2_tenancy = get_new_ec2_tenancy(new_instance_id)
            while new_ec2_status !== 'running':
                time.sleep(10)
                new_get_ec2_status(new_instance_id)
            print('Enabling Termination Protection for ' + new_instance_id)
            enable_termination_protection(new_instance_id)
            new_ec2_reboot(new_instance_id)
            
            # UpdateELB/ALB Target
            process_elb_association(instance_id,new_instance_id)
            process_alb_association(instance_id,new_instance_id)
            migration_duration = datetime.now() - start_time
            print('=================================================')
            print('-  Migration of ' + instance_id + ' Successful  -')
            print('=================================================')
            print('New Instance ID: ' + new_instance_id)
            print('Migration Duration: ' + str(migration_duration))
        # Dryrun fails
        else:
            print('=================================================')
            print('-  Migration of ' + instance_id + ' Failed.     -')
            print('-  EC2 Test Launch unsuccessful. Please verify  -')
            print('-  IAM session has AdministratorAccess policy   -')
            print('-  attached to IAM user or instance role.       -')
            print('-  Rolling EC2 back to pre-migration state.     -')
            print('=================================================')
            migration_action_rollback(ami_id)

if __name__ =='__main__':
    main()
