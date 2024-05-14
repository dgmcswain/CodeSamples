from __future__ import print_function
import argparse
import os
import botocore
import boto3
import csv
###############################
###  Variables & Arguments  ###
###############################
# AWS variables
region = 'us-east-1'

# Report file
script_dir = os.path.dirname(os.path.realpath(__file__))
report_txt_file = script_dir + "/aws_ec2_listing_report.csv"

# Parser for command-line arguments
parser = argparse.ArgumentParser(description='Run RDS Listing report.')
args = parser.parse_args()

##################################
###  Initialize Boto3 Clients  ###
##################################

ec2_client = boto3.client('ec2', region_name=region)
ec2_resource = boto3.resource('ec2', region_name=region)
cw_client = boto3.client('cloudwatch', region_name=region)


##############################
###  Function Definitions  ###
##############################

# Function: print_header
#     Prints a header in the report file
def print_header(text):
    title_row = '#####  ' + str(text) + '  #####'
    buffer_row = '#' * len(title_row)

    print("", file=f)
    print(buffer_row, file=f)
    print(title_row, file=f)
    print(buffer_row, file=f)
    print("", file=f)

#---------------------------------------------------------------------------------------------

# Function: print_subheader
#     Prints a subheader in the report file
def print_subheader(text):
    print('===  ' + str(text) + '  ===', file=f)

#####################
###  Main Script  ###
#####################

# Create report file
with open(report_txt_file, 'w') as f:

    # Print the Cost Explorer start and end dates
    #print('\nRDS Explorer:', file=f)

#------------------------------------------------------------------------------------------------------------
#####  Relational Database Service (RDS)  #####
# Initialize variables
    ec2_instances_count_total = 0
    ec2_instance_running = 0
    #rds_allocated_storage = 0
    #rds_total_used_storage = 0
    ec2_list = []
    instance_id_list = []
    ec2_instances_count_total = 0
    ec2_instance_running = 0 
    # Print header
    print_header('Elastic Cloud Compute (EC2)')

    #--------------------------------------------------------------------------------------------------------
    #-----  RDS DB Instances  -----
    #------------------------------

    # Print subheader
    print_subheader('EC2 Instances')

    def get_instance_id_list():
        paginator = ec2_client.get_paginator('describe_instances')
        pages = paginator.paginate()
        global ec2_instances_count_total
        global instance_id_list
        global ec2_instance_running
        ec2_instances_count_total = 0
        ec2_instance_running = 0
        instance_id_list = []
        for page in pages:
            for reservation in page['Reservations']:
                for instance in reservation['Instances']:
                    ec2_instances_count_total +=1
                    if instance['State']['Name'] == 'running':
                        ec2_instance_running +=1
                    instance_id = instance['InstanceId']
                    instance_id_list.append(instance_id)
        return instance_id_list

    # Query AWS RDS Service
    instance_id_list = get_instance_id_list()
    for instance_id in instance_id_list:
        ec2instance = ec2_resource.Instance(instance_id)
        describe_ec2 = ec2_client.describe_instances(InstanceIds=[instance_id])
    
    # Declare default values
        iam_profile = 'Blank'
        Name = 'Blank'
        NameMgt = 'Blank'
        fqdn = 'Blank'
        ado = 'Blank'
        AMIOperatingSys = 'Blank'
        Application = 'Blank'
        ApplicationOwner = 'Blank'
        Builder = 'Blank'
        Description = 'Blank'
        build_date = 'Blank'
        Environment = 'Blank'
        Schedule = 'Blank'
        LineOfBusiness = 'Blank'
        PatchGroup = 'Blank'
        PrimaryTechPOC = 'Blank'
        SecondaryTechPOC = 'Blank'
        Tier = 'Blank'
        Vpc = 'Blank'
        cpm_backup = 'Blank'

        instance_state = describe_ec2['Reservations'][0]['Instances'][0]['State']['Name']
        if not instance_state == 'terminated':
            instance_type = describe_ec2['Reservations'][0]['Instances'][0]['InstanceType']
            launch_time = describe_ec2['Reservations'][0]['Instances'][0]['LaunchTime']
            vpc_id = describe_ec2['Reservations'][0]['Instances'][0]['VpcId']
            subnet_id = describe_ec2['Reservations'][0]['Instances'][0]['SubnetId']
            try:
                iam_profile = describe_ec2['Reservations'][0]['Instances'][0]['IamInstanceProfile']['Arn']
                iam_profile = iam_profile.split('/')[1]
            except:
                pass
            availability_zone = describe_ec2['Reservations'][0]['Instances'][0]['Placement']['AvailabilityZone']

            for tag in ec2instance.tags:
                if tag['Key'] == 'Name':
                    Name = tag['Value']
                elif tag['Key'] == 'Name':
                    Name = tag['Value']
                elif tag['Key'] == 'NameMgt':
                    NameMgt = tag['Value']
                    if NameMgt == '-mgt':
                        NameMgt = 'Blank'
                elif tag['Key'] == 'FQDN':
                    fqdn = tag['Value']
                elif tag['Key'] == 'ADO':
                    ado = tag['Value']
                elif tag['Key'] == 'AMIOperatingSys':
                    AMIOperatingSys = tag['Value']
                elif tag['Key'] == 'Application':
                    Application = tag['Value']
                elif tag['Key'] == 'ApplicationOwner':
                    ApplicationOwner = tag['Value']
                elif tag['Key'] == 'Builder':
                    Builder = tag['Value']
                elif tag['Key'] == 'Description':
                    Description = tag['Value']
                elif tag['Key'] == 'Build-Date':
                    build_date = tag['Value']
                elif tag['Key'] == 'ENVIRONMENT':
                    Environment = tag['Value']
                elif tag['Key'] == 'Schedule':
                    Schedule = tag['Key']
                elif tag['Key'] == 'LineOfBusiness':
                    LineOfBusiness = tag['Value']
                elif tag['Key'] == 'PatchGroup':
                    PatchGroup = tag['Value']
                elif tag['Key'] == 'PrimaryTechPOC':
                    PrimaryTechPOC = tag['Value']
                elif tag['Key'] == 'SecondaryTechPOC':
                    SecondaryTechPOC = tag['Value']
                elif tag['Key'] == 'VPC':
                    Vpc = tag['Value']
                elif tag['Key'] == 'TIER':
                    Tier = tag['Value']
                elif tag['Key'] == 'cpm backup':
                    cpm_backup = tag['Value']
            try:
                ec2_list.append({
                "Instance ID": instance_id,
                "Name": Name,
                #"Key Name": instance['KeyName'],
                "Instance Type": instance_type,
                "Launch Time": launch_time,
                "VPC ID": vpc_id,
                "Subnet ID": subnet_id,
                "IAM Profile": iam_profile,
                "AZ": availability_zone,
                "Name": Name,
                "NameMgt": str(NameMgt),
                " FQDN": fqdn,
                "ADO": ado,
                "AMIOperatingSys": AMIOperatingSys,
                "Application": Application,
                "ApplicationOwner": ApplicationOwner,
                "Builder": Builder,
                "Description":Description,
                "ENVIRONMENT": Environment,
                "BuildDate": build_date,
                "Schedule": Schedule,
                #"TerminateOnDate": 
                "LineOfBusiness": LineOfBusiness,
                "PatchGroup": PatchGroup,
                "PrimaryTechPOC": PrimaryTechPOC,
                "SecondaryTechPOC": SecondaryTechPOC,
                "TIER": Tier,
                "VPC": Vpc,
                "CPM Backup": cpm_backup
                })
                #name(instance_id)
            except botocore.exceptions.ClientError as error:
                print(error)
                pass

    print("Total EC2 Instances: " + str(ec2_instances_count_total), file=f)
    print("Total EC2 Running: " + str(ec2_instance_running), file=f)

    print("\n", file=f)
    header = ['Name','Instance ID','Instance Type','Launch Time','VPC ID','Subnet ID','IAM Profile','AZ','Name','NameMgt',' FQDN','ADO','AMIOperatingSys',
    'Application','ApplicationOwner','Builder','Description','ENVIRONMENT','BuildDate','Schedule','TerminateOnDate','LineOfBusiness','PatchGroup','PrimaryTechPOC','SecondaryTechPOC','TIER',
    'VPC','CPM Backup']
    writer = csv.DictWriter(f,fieldnames=header)
    writer.writeheader()
    writer.writerows(ec2_list)
