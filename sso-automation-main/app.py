#!/usr/bin/env python3

import json
import aws_cdk as cdk

from aws_sso_automation.aws_sso_automation_stack import AwsSsoAutomationStack
from aws_sso_automation.aws_sso_mappings import AwsSsoGroupMappings
from aws_sso_automation.aws_sso_mgmt_mappings import AwsSsoMgmtGroupMappings

app = cdk.App()

properties = {
  "env_name": "ENT_OKTA_AWS_",
  "sso_instance_arn": "arn:aws:sso:::instance/ssoins-7223dd0fdfc46891",
  "identity_store": "d-1111111111"
}

## Deploying workload permission sets
CONFIG_DIR = './config'


with open (f'{CONFIG_DIR}/permission-sets/workload-config.json') as data_file:
  data = json.load(data_file)
  
  imported_permissions = AwsSsoAutomationStack(
      app,
      f"ImportedPermissionSetsStack",
      properties=properties,
      permission_sets=data,
      importing_stack=True,
      stack_name=f"sso-permission-sets-imports",
  )
  
with open (f'{CONFIG_DIR}/permission-sets/legacy-config.json') as data_file:
  data = json.load(data_file)
  imported_legacy = AwsSsoAutomationStack(
      app,
      f"ImportedLegacyPermissionSetsStack",
      properties=properties,
      permission_sets=data,
      importing_stack=True,
      stack_name=f"sso-permission-sets-legacy-imports",
  )
  
  
with open (f'{CONFIG_DIR}/mapping-workload-groups.json') as data_file:
  data = json.load(data_file)
  
  imported_standard_group_mapping_stack = AwsSsoGroupMappings(
      app,
      f"ImportedPermissionSetsMappings",
      properties=properties,
      map_imported=True,
      translate_required=True,
      mappings=data,
      stack_name=f"sso-permission-sets-imported-mappings",
  )
  
#Deploy Account Specific Sets
with open (f'{CONFIG_DIR}/mapping-legacy-groups.json') as data_file:
  data = json.load(data_file)
  legacy_imported_mappings = AwsSsoGroupMappings(
      app,
      f"LegacyImportedPermissionSetsMappings",
      properties=properties,
      map_imported=True,
      translate_required=True,
      mappings=data,
      stack_name=f"sso-permission-sets-legacy-imported-mappings",
  )

#Deploy Management mappings for management accounts
with open (f'{CONFIG_DIR}/mapping-management-groups.json') as data_file:
  data = json.load(data_file)
  management_group_mappings = AwsSsoMgmtGroupMappings(
      app,
      f"ManagementPermissionSetsMappings",
      properties=properties,
      mappings=data,
      translate_name=False,
      stack_name=f"sso-permission-sets-management-mappings",
  )
  
#Deploy Management mappings for management accounts
with open (f'{CONFIG_DIR}/mapping-contractor-groups.json') as data_file:
  data = json.load(data_file)
  management_group_mappings = AwsSsoMgmtGroupMappings(
      app,
      f"ContractorPermissionSetsMappings",
      properties=properties,
      mappings=data,
      translate_name=False,
      stack_name=f"sso-permission-sets-contractor-mappings",
  )

app.synth()
