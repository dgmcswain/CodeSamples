import boto3
import botocore
import sys
import time
import json
import logging
from botocore.exceptions import ClientError
from datetime import datetime

### Global Variables
global instance_id
global netintlist
global netintdict
instance_id = sys.argv[1]
ami_id = None
ami_state = None
new_instance_id = None
new_ec2_status = None
new_ec2_tenancy = None
iam_profile = None

client = boto3.client('ec2')
# resource = boto3.resource('ec2')
elb = boto3.client('elb')
alb = boto3.client('elbv2')

##### FUNCTIONS ######
# Define Log function
def log(error):
    print('{}Z {}'.format(datetime.utcnow(), error))

def migration_action_skip():
    try:
        log("Tenancy Migration skipped for: {}".format(instance_id))
    except botocore.exceptions.ClientError as e:
        log("Error completing migration instance {}: {}".format(instance_id, e.response['Error']))
        log('{"Error": "1"}')
    exit()

##### Get EC2 System Information #####
# Get EC2 tenancy
def get_ec2_tenancy(instance_id):
    if instance_id:
        try:
            ec2 = client.describe_instances(InstanceIds=[instance_id])
            ec2_tenancy = ec2['Reservations'][0]['Instances'][0]['Placement']['Tenancy']
            log("EC2 Instance Tenancy: {}".format(ec2_tenancy))
        except botocore.exceptions.ClientError as e:
            log("Error parsing EC2 tenancy: {}".format(e.response['Error']))
        return ec2_tenancy

### Get EC2 Termination Protection 
def get_ec2_term_protection(instance_id):
        if instance_id:
            try:
                term = client.describe_instance_attribute(Attribute='disableApiTermination',InstanceId=instance_id)
                term_protection = term['DisableApiTermination']['Value']
            except botocore.exceptions.ClientError as e:
                log("Error parsing EC2 tenancy: {}".format(e.response['Error']))
            return term_protection

### Get EC2 Instance type
def get_ec2_type(instance_id):
    if instance_id:
        try:
            ec2 = client.describe_instances(InstanceIds=[instance_id])
            ec2_type = ec2['Reservations'][0]['Instances'][0]['InstanceType']
            log("EC2 Instance Type: {}".format(ec2_type))
        except botocore.exceptions.ClientError as e:
            log("Error parsing EC2 Instance Type: {}".format(e.response['Error']))
        return ec2_type

### Get EC2 Tags
def get_ec2_tags(instance_id):
    tag_info = None
    if instance_id:
        try:
            tags = client.describe_instances(InstanceIds=[instance_id])
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
            log("Getting EC2 tag information for: {}".format(instance_id))
        except botocore.exceptions.ClientError as e:
            log("Error parsing EC2 Tags: {}".format(e.response['Error']))
        return tag_info

### GET EC2 IAM profile
def get_iam_profile(instance_id):
    iam_profile = None
    if instance_id:
        try:
            iam = client.describe_instances(InstanceIds=[instance_id])
            iam_profile = iam['Reservations'][0]['Instances'][0]['IamInstanceProfile']['Arn']
            log("EC2 IAM profile: {}".format(iam_profile))
        except botocore.exceptions.ClientError as e:
            log("Error parsing IAM profile {}".format(e.response['Error']))
        except KeyError:
            pass
        return iam_profile

### Stop EC2 ###
def stop_ec2(instance_id):
    if instance_id:

        try:
            client.stop_instances(InstanceIds=[instance_id])
            log("Stopping EC2 instance: {}".format(instance_id))
        except botocore.exceptions.ClientError as e:
            log("Error stopping the instance {}: {}".format(instance_id,e.response['Error']))

### GET Source EC2 status
def get_ec2_status(instance_id):
    ec2_status = None
    if instance_id:
        try:
            ec2 = client.describe_instances(InstanceIds=[instance_id])
            ec2_status = ec2['Reservations'][0]['Instances'][0]['State']['Name']
            log("EC2 Status: {}".format(ec2_status))    
        except botocore.exceptions.ClientError as e:
            log("Error parsing EC2 state: {}".format(e.response['Error']))
        return ec2_status

### Create AMI
def create_ami(instance_id):
    global ami_id
    ami_id = None
    if instance_id:
        try:
            image = client.create_image(
                Description='Copy of ' + instance_id,
                DryRun=False,
                InstanceId=instance_id,
                Name='Copy of ' + instance_id,
                NoReboot=True,
            )
            time.sleep(5)
            ami_id = image['ImageId']
            log("Creating AMI ID: {}".format(ami_id))
        except botocore.exceptions.ClientError as e:
            log("Error creating AMI: {}".format(e.response['Error']))
        return ami_id

### Get AMI Status
def get_ami_create_status(ami_id):
    global ami_state
    ami_state = None
    if ami_id:  
        try:
            ami = client.describe_images(ImageIds=[ami_id])
            ami_status = ami['Images'][0]['State']
            log("AMI Status: {}".format(ami_status))
        except botocore.exceptions.ClientError as e:
            log("Error parsing AMI creation state {}: {}".format(ami_id,e.response['Error']))
        ami_state = ami_status
        time.sleep(10)
        return ami_state

### Process ENIs for migration
def process_eni_for_migraiton(instance_id):
    netintlist = []
    netintdict = {}
    ec2desc = client.describe_instances(InstanceIds=[instance_id])
    for eni in ec2desc['Reservations'][0]['Instances'][0]['NetworkInterfaces']:
        eniid = eni['NetworkInterfaceId']
        enidesc = client.describe_network_interfaces(NetworkInterfaceIds=[eniid])
        eniip = enidesc['NetworkInterfaces'][0]['PrivateIpAddress']
        attachid = enidesc['NetworkInterfaces'][0]['Attachment']['AttachmentId']
        devindex = enidesc['NetworkInterfaces'][0]['Attachment']['DeviceIndex']
        # Build config for launch
        netintdict = {'DeleteOnTermination': False, 'DeviceIndex': devindex, 'NetworkInterfaceId': eniid}
        netintlist.append(netintdict)
        # Mark ENIs for no deletion
        try:
            client.modify_network_interface_attribute(Attachment={'AttachmentId': attachid, 'DeleteOnTermination': False},NetworkInterfaceId=eniid)
            log("Setting DeleteOnTermination to False on ENI: " + eniid + ", IP: " + eniip)
            #log("Setting DeleteOnTermination to False on ENI: {}".format(eniid))
            #log("IP Address: {}".format(eniip))
        except:
            pass
    return netintlist
    
### Test EC2 Launch permissions
def test_ec2_launch_dryrun(net_cfg_list,ami_id,ec2_type,iam_profile,ec2_tags):
    if ami_id:
        try:  
            if iam_profile == None:
                client.run_instances(
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
                client.run_instances(
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
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Message'] == "Request would have succeeded, but DryRun flag is set.":
                log("Test EC2 launch Succeeded: {}".format(e.response['Error']['Message']))
                return True
            else:
                log("Test EC2 launch failed: {}".format(e.response['Error']['Message']))
                return False

### Terminate Source EC2
def terminate_ec2(instance_id):
    if instance_id:
        try:
            client.terminate_instances(InstanceIds=[instance_id])
        except botocore.exceptions.ClientError as e:
            log("Error terminating EC2 instance {}: {}".format(instance_id,e.response['Error']))

### Launch New Instance
def launch_ec2(net_cfg_list,ami_id,ec2_type,ec2_tags,iam_profile):
    global new_instance_id
    launch_id = None
    try:  
        if iam_profile == None:
            launch = client.run_instances(
                NetworkInterfaces=net_cfg_list,
                ImageId=ami_id,
                MinCount=1,
                MaxCount=1,
                InstanceType=ec2_type,
                Placement={'Tenancy': 'default'},
                TagSpecifications=[{'ResourceType': 'instance','Tags': ec2_tags}],
            )
        else:
            launch = client.run_instances(
                NetworkInterfaces=net_cfg_list,
                ImageId=ami_id,
                MinCount=1,
                MaxCount=1,
                InstanceType=ec2_type,
                Placement={'Tenancy': 'default'},
                TagSpecifications=[{'ResourceType': 'instance','Tags': ec2_tags}],
                IamInstanceProfile={'Arn': iam_profile},
            )
        launch_id = launch['Instances'][0]['InstanceId']
        log("Launching new EC2: {}".format(launch_id))
    except botocore.exceptions.ClientError as e:
        log("Error launching EC2: {}".format(e.response['Error']))
    new_instance_id = launch_id
    return new_instance_id

### Enable Termination protection
def enable_termination_protection(new_instance_id):
    if new_instance_id:
        try:
            client.modify_instance_attribute(InstanceId=new_instance_id,DisableApiTermination={'Value': True})
        except botocore.exceptions.ClientError as e:
            log("Error enabling termination protection: {}".format(e.response['Error']))                

### Get New EC2 status
def new_get_ec2_status(new_instance_id):
    global new_ec2_status
    new_ec2_status = None
    if new_instance_id:
        try:
            new_ec2 = client.describe_instances(InstanceIds=[new_instance_id])
            new_get_ec2_status = new_ec2['Reservations'][0]['Instances'][0]['State']['Name']
            log("New EC2 Status: {}".format(new_get_ec2_status))               
        except botocore.exceptions.ClientError as e:
            log("Error parsing new EC2 state: {}".format(e.response['Error']))
        new_ec2_status = new_get_ec2_status
        return new_ec2_status

### Get New EC2 tenancy
def get_new_ec2_tenancy(new_instance_id):
    global new_ec2_tenancy
    new_ec2_tenancy = None
    if new_instance_id:
        try:
            new_ec2 = client.describe_instances(InstanceIds=[new_instance_id])
            new_ec2_tenant = new_ec2['Reservations'][0]['Instances'][0]['Placement']['Tenancy']
        except botocore.exceptions.ClientError as e:
            log("Error parsing new EC2 tenancy: {}".format(e.response['Error']))
        new_ec2_tenancy = new_ec2_tenant
        return new_ec2_tenancy

### Reboot new instance
def new_ec2_reboot(new_instance_id):
    if new_instance_id:
        try:
            client.reboot_instances(InstanceIds=[new_instance_id])
            log("Rebooting New EC2: {}".format(new_instance_id))
        except botocore.exceptions.ClientError as e:
            log("Error rebooting new EC2 instance: {}".format(e.response['Error']))

### Process ELB Association
def process_elb_association(instance_id,new_instance_id):
    elblist = elb.describe_load_balancers()
    for elbs in elblist['LoadBalancerDescriptions']:
        for ec2id in elbs['Instances']:
            if ec2id['InstanceId'] == instance_id:
                elbname = elbs['LoadBalancerName']
                log("Instance: " + instance_id + " attached to ELB:" + elbname)
                try:
                    elb.register_instances_with_load_balancer(LoadBalancerName=elbname,Instances=[{'InstanceId': new_instance_id}])
                    elb.deregister_instances_from_load_balancer(LoadBalancerName=elbname,Instances=[{'InstanceId': instance_id}])
                    log("Registering instance " + new_instance_id + " with ELB: {}".format(elbname))
                    log("De-Registering instance " + instance_id + " from ELB: {}".format(elbname))
                except botocore.exceptions.ClientError as e:
                    log("Error registering " + new_instance_id + " with ELB: {}".format(e.response['Error']))

### Process ALB Association
def process_alb_association(instance_id,new_instance_id):
    alblist = alb.describe_target_groups()
    for targets in alblist['TargetGroups']:
        tgname = targets['TargetGroupName']
        targetarn = targets['TargetGroupArn']
        targetid = alb.describe_target_health(TargetGroupArn=targetarn)
        for target in targetid['TargetHealthDescriptions']:
            tgid = target['Target']['Id']
            tgport = target['Target']['Port']
            if tgid == instance_id:
                log ("Instance: " + instance_id + " attached to Target Group: {}".format(tgname))
                try:
                    alb.register_targets(TargetGroupArn=targetarn,Targets=[{'Id': new_instance_id,'Port': tgport}])
                    log("Registering instance " + new_instance_id + " with Target Group: {}".format(tgname))       
                except botocore.exceptions.ClientError as e:
                    log("Error registering " + new_instance_id + " with Target Group: {}".format(e.response['Error']))

### Migration rollback
def migration_action_rollback(ami_id):
    try:
        client.deregister_image(ImageId=ami_id)
        log("De-Registering AMI id: {}".format(ami_id))
    except botocore.exceptions.ClientError as amierr:
        log("Error De-Registering AMI {}: {}".format(ami_id,amierr.response['Error']))

### Main Function
def main():
    startTime = datetime.now()
    ec2_tenancy = get_ec2_tenancy(instance_id)
    ec2_termination_protection = get_ec2_term_protection(instance_id)
    iam_profile = get_iam_profile(instance_id)

    if ec2_tenancy == 'default':
        print('======================================================================')
        print('Instance ' + instance_id + ' already configured for default tenancy')
        print('Aborting ...')
        print('======================================================================')
        migration_action_skip()

    elif ec2_termination_protection == True:
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
        while not ec2_status == 'stopped':
            time.sleep(10)
            ec2_status = get_ec2_status(instance_id)
        create_ami(instance_id)
        time.sleep(10)
        ami_state = None
        while not ami_state =='available':
            time.sleep(10)
            ami_state = get_ami_create_status(ami_id)
        # Execute Dryrun test EC2 launch prior to target EC2 termination
        net_cfg_list = process_eni_for_migraiton(instance_id)
        test_ec2_launch_status = test_ec2_launch_dryrun(net_cfg_list,ami_id,ec2_type,iam_profile,ec2_tags)
        # Dryrun succeeds
        if test_ec2_launch_status == True:
            terminate_ec2(instance_id)
            ec2_status = get_ec2_status(instance_id)
            while not ec2_status == 'terminated':
                time.sleep(5)
                ec2_status = get_ec2_status(instance_id)
            launch_ec2(net_cfg_list,ami_id,ec2_type,ec2_tags,iam_profile)
            while not new_ec2_status == 'running':
                time.sleep(10)
                new_get_ec2_status(new_instance_id)
            print('Enabling Termination Protection for ' + new_instance_id)
            enable_termination_protection(new_instance_id)
            new_ec2_reboot(new_instance_id)
            #UpdateELB/ALB Target
            process_elb_association(instance_id,new_instance_id)
            process_alb_association(instance_id,new_instance_id)
            migrationDuration = datetime.now() - startTime
            print('=================================================')
            print('-  Migration of ' + instance_id + ' Successful  -')
            print('=================================================')
            print('New Instance ID: ' + new_instance_id)
            print('Migration Duration: ' + str(migrationDuration))
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
