#
# retrieve and render AWS SSO PermissionSet information, would be nice to
# find a way to indent the policy rendering, i know this is a hack, please don't judge me... 🖖
#
import boto3
import json
import os
import yaml
from itertools import chain
import csv

# Function to convert a CSV to JSON
# Takes the file paths as arguments
def make_json(csvFilePath, jsonFilePath):
     
    # create a dictionary
    data = {}
     
    # Open a csv reader called DictReader
    with open(csvFilePath, encoding='utf-8') as csvf:
        csvReader = csv.DictReader(csvf)
        data = []
        # Convert each row into a dictionary
        # and add it to data
        for rows in csvReader:
             
            # Assuming a column named 'No' to
            # be the primary key
            data.append(rows)
 
    # Open a json writer, and use the json.dumps()
    # function to dump data
    with open(jsonFilePath, 'w', encoding='utf-8') as jsonf:
        jsonf.write(json.dumps(data, indent=4))

sso = boto3.client('sso-admin')

instances = sso.list_instances() # using [0] is daft, but not sure it is possible to have two instances in a region?
instance_arn = instances['Instances'][0]['InstanceArn']
identity_store = instances['Instances'][0]['IdentityStoreId']

store_policies = True
policy_directory = f"./new-policies"
permission_sets = []
output = []

stages = {"permission_sets": output}


paginator = sso.get_paginator('list_permission_sets')
for page in paginator.paginate(InstanceArn=instance_arn):
  for p in page['PermissionSets']:
    permission_sets.append(p)
deduped_permission_sets = list(set(permission_sets))

# Decide the two file paths according to your
# computer system

import_file = "test-mapping"

#csvFilePath = f"../config/{import_file}.csv"
jsonFilePath = f"./config/{import_file}.json"


# Call the make_json function
#make_json(csvFilePath, jsonFilePath)


with open(jsonFilePath) as f: 
  data = json.load(f)
  unique_policies = {}

  for map in data:
    if unique_policies.get(map['PermissionSet']) == None :
      ps_detail ={}
      ps_mapped_object = {map['PermissionSet']: ps_detail}
      ps_detail["PermName"] = map['PermissionSet']
      ps_detail["PermType"]= map['PermissionType']
      ps_detail["MappedPermissionSet"] = map["PermissionSetMapped"]

      unique_policies[map['PermissionSet']]=ps_detail

  for ps_arn in deduped_permission_sets:

    ps_object = {}
    detail = sso.describe_permission_set(InstanceArn=instance_arn, PermissionSetArn=ps_arn) # https://boto3.amazonaws.com/v1/documentation/api/1.18.10/reference/services/sso-admin.html#SSOAdmin.Client.describe_permission_set
    


    if unique_policies.get(detail['PermissionSet'].get('Name')) is not None:

      permission_set_name = detail['PermissionSet'].get('Name')
      print(f"Retrieving PermissionSets {permission_set_name} for AWS SSO Instance {ps_arn.split('/')[1]}, Identity Store {identity_store}...")

      ps_object["PermName"]= unique_policies.get(permission_set_name).get('PermName')
      ps_object["PermType"]= unique_policies.get(permission_set_name).get('PermType')
      ps_object["MappedPermissionSet"]= unique_policies.get(permission_set_name).get('MappedPermissionSet')
      ps_object["relay_state"] = detail['PermissionSet'].get('RelayState') 
      ps_object["permission_set_name"] = detail['PermissionSet'].get('Name')
      ps_object["ps_arn"] = detail['PermissionSet']['PermissionSetArn']
      ps_object["description"] = detail['PermissionSet'].get('Description', detail['PermissionSet'].get('Name'))
      ps_object["session_duration"] = detail['PermissionSet']['SessionDuration']
      ps_accounts = []
      
      params = {"InstanceArn": instance_arn, "PermissionSetArn": ps_arn, "MaxResults": 100}
      
      response = sso.list_managed_policies_in_permission_set(InstanceArn=instance_arn, PermissionSetArn=ps_arn)
      aws_managed_polices = []

      for policy in response['AttachedManagedPolicies']:
          aws_managed_polices.append(policy)
      
      ps_object["aws_managed_policies"]=aws_managed_polices
      ps_object["account_assignments"]=ps_accounts
          
            
      response = sso.get_inline_policy_for_permission_set(InstanceArn=instance_arn, PermissionSetArn=ps_arn)

      if not os.path.exists(policy_directory):
          os.makedirs(policy_directory)
      try: 
        if response['InlinePolicy']:
          file_path = f"{policy_directory}/{detail['PermissionSet']['Name']}.json"
          ps_object["inline_policy_document_file"]=file_path
          with open(file_path, 'w') as w:
              w.write(json.dumps(json.loads(response['InlinePolicy']), indent=4))
      except Exception as e:
        print(e)
        
      output.append(ps_object)

# Serializing to yaml config    
json_stuff = json.dumps(stages, indent=4)

with open(f"{import_file}-role-config.json", "w") as outfile:
    outfile.write(json_stuff)
