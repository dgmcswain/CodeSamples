import aws_cdk as cdk
import aws_cdk.aws_sso as sso
import boto3 
import utilities.resource_helpers as rh

class AwsSsoGroupMappings(cdk.Stack):
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
        map_imported: bool,
        translate_required: bool,
        mappings: dict,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
      

        for group in mappings:
            output=f"{group['permission_set']}output"              
            if map_imported: 
              if translate_required: 
                output = rh.clean_resource_id(output)
              perm_arn = cdk.Fn.import_value(output)
              
            group_name = group["Group"]
            trunc_grp_name = group_name.replace("ENT_OKTA_AWS_",'')
            #trunc_grp_name = trunc_grp_name.replace("ENT_Okta_AWS_",'')
            account_name = group.get("account_name","Shared")
            account_id = group.get("account_num", "")
            account_list = group.get("account_assignments",[])

            is_client = boto3.client(service_name="identitystore")
            
            group_response = is_client.list_groups(
            IdentityStoreId=properties.get('identity_store'),
              Filters=[{"AttributePath": "DisplayName", "AttributeValue": f"{group_name}"}],
                )
            
            if len(account_list)>0 and len(group_response['Groups'])>0:
              group_id = group_response['Groups'][0]['GroupId']

              for account in account_list:
                sso_assignment = sso.CfnAssignment(
                  self,
                  f"{trunc_grp_name}_{account}",
                  instance_arn=properties["sso_instance_arn"],
                  permission_set_arn=perm_arn,
                  principal_id=group_id,
                  principal_type="GROUP",
                  target_id=account,
                  target_type="AWS_ACCOUNT",
              )
            elif len(group_response['Groups'])>0:
              group_id = group_response['Groups'][0]['GroupId']

              # Each SSO assignment resource name needs to be unique
              sso_assignment = sso.CfnAssignment(
                  self,
                  f"{trunc_grp_name}_{account_name}",
                  instance_arn=properties["sso_instance_arn"],
                  permission_set_arn=perm_arn,
                  principal_id=group_id,
                  principal_type="GROUP",
                  target_id=account_id,
                  target_type="AWS_ACCOUNT",
              )
            else:
              print(f"Group does not exist for {group_name}")
