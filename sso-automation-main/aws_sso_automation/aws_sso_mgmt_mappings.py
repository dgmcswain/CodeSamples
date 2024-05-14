import aws_cdk as cdk
import aws_cdk.aws_sso as sso
import boto3 
import utilities.resource_helpers as rh
class AwsSsoMgmtGroupMappings(cdk.Stack):
    """Generate AWS SSO Permission Sets and Account Assignments.

    Based on account structure with recursive account path mappings and group mappings as input
    the implementation generates a stack with SSO permission sets and SSO group & account assignments.

    Note that group names must be predictable as the identity store group lookup doesn't support wildcard searches.
    """
    def __init__(
        self,
        scope: cdk.App,
        construct_id: str,
        properties: dict,
        mappings: dict,
        translate_name: bool,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        for group in mappings:
          cfn_output = rh.clean_resource_id(f"{group['permission_set']}output")
          perm_arn = cdk.Fn.import_value(cfn_output)
          
          group_name = group["Group"]
          group_prefix = "ENT_OKTA_AWS_"
          
          if translate_name:
            trucated_grp_name = rh.translate_group_name(group_name)
          else:
            trucated_grp_name = group_name.replace(group_prefix,'')
          
          
          if group_name == "ENT_Okta_AWS_Administrators" or group_name == "ENT_Okta_AWS_CloudSecurity" or group_name == "ENT_Okta_AWS_NetworkingReadOnly":
            deletion_policy = cdk.RemovalPolicy.RETAIN
          else:
            deletion_policy = cdk.RemovalPolicy.DESTROY

          #Get all the groups in the config   
          ou_assignments = group.get("ou_assignments",[])
          account_assignments = group.get("account_assignments",[])
          excluded_assignments = group.get("account_exclusions",[])

          #recursively populate list of accounts for OUs provided
          ou_assigned_account_list = rh.list_accounts_in_ou(ou_assignments,[])
          
          #combine the two lists
          combined_assignment_list = account_assignments + ou_assigned_account_list
          
          #take the unique entries (no duplicates)
          combined_assignment_list = list(dict.fromkeys(combined_assignment_list))
          
          accounts_after_excluded = [acc for acc in combined_assignment_list if acc not in excluded_assignments]

          #TODO break this into a common function
          #Gets the group ID from the Name, its needed for the creation
          is_client = boto3.client(service_name="identitystore")
          group_response = is_client.list_groups(
          IdentityStoreId=properties.get('identity_store'),
            Filters=[{"AttributePath": "DisplayName", "AttributeValue": f"{group_name}"}],
              )
          try: 
            group_id = group_response['Groups'][0]['GroupId']
          except Exception as e:
            print(f"No group found for {group_name}")
            break
          for account in accounts_after_excluded:
            if len(account) == 12:
              sso_resource = sso.CfnAssignment(
                self,
                f"{trucated_grp_name}_{account}",
                instance_arn=properties["sso_instance_arn"],
                permission_set_arn=perm_arn,
                principal_id=group_id,
                principal_type="GROUP",
                target_id=account,
                target_type="AWS_ACCOUNT",
            )
              sso_resource.apply_removal_policy(deletion_policy)
            else:
              continue