import aws_cdk as cdk
import aws_cdk.aws_sso as sso
from utilities.file_helper import file_sub
import utilities.resource_helpers as rh


class AwsSsoAutomationStack(cdk.Stack):
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
        importing_stack: bool,
        permission_sets: dict,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        for permission_set in permission_sets['permission_sets']:
            permission_set_name = permission_set['permission_set_name']
            if permission_set.get('aws_managed_policies'):
              managed_policy_arns= []
              managed_policy = permission_set.get('aws_managed_policies')
              for policy in managed_policy:
                managed_policy_arns.append(policy['Arn'])
            else:
              managed_policy_arns = None
            # Optionally attach an inline policy document to the SSO Permission Set
            if "inline_policy_document_file" in permission_set:
                inline_policy_document = file_sub(
                    f"{permission_set['inline_policy_document_file']}"
                )
            else:
                inline_policy_document = None

            cfn_tag = cdk.CfnTag(
                key="OriginalPermissionName",
                value=permission_set_name
            )
            
            pset_id_clean = rh.clean_resource_id(permission_set_name)
            mapped_permission_name = permission_set['mapped_permission_name']
            
            if not importing_stack:
              
              pset_id_clean = rh.clean_resource_id(permission_set['mapped_permission_name'])

              sso_permission_set = sso.CfnPermissionSet(
                  self,
                  f"{pset_id_clean}",
                  instance_arn=properties["sso_instance_arn"],
                  name=f"{mapped_permission_name}",
                  description=permission_set.get("description"),
                  inline_policy=inline_policy_document,
                  managed_policies=managed_policy_arns,
                  relay_state_type=permission_set.get("relay_state"),
                  session_duration=permission_set.get("session_duration"),
                  tags=[cfn_tag]
                  )
                
              cdk.CfnOutput(self, f"{pset_id_clean}output", value=sso_permission_set.attr_permission_set_arn, export_name=f"{pset_id_clean}output")       
              self.sso_permission_set = sso_permission_set.attr_permission_set_arn
              sso_permission_set.apply_removal_policy(policy=cdk.RemovalPolicy.DESTROY)

            else:
                import_tag = cdk.CfnTag(
                  key="CFNImport",
                  value="True"
                  )
                if permission_set.get("cfn_entity_name_override","") != "": 
                    pset_id_clean = rh.clean_resource_id(permission_set['cfn_entity_name_override'])
                else:
                  pset_id_clean = rh.clean_resource_id(permission_set_name)
                  permission_set_name = permission_set['permission_set_name']
                  
                sso_permission_set = sso.CfnPermissionSet(
                    self,
                    f"{pset_id_clean}",
                    instance_arn=properties["sso_instance_arn"],
                    name=f"{permission_set_name}",
                    description=permission_set.get("description"),
                    inline_policy=inline_policy_document,
                    managed_policies=managed_policy_arns,
                    relay_state_type=permission_set.get("relay_state"),
                    session_duration=permission_set.get("session_duration"),
                    tags=[import_tag]
                    )
                sso_permission_set.apply_removal_policy(policy=cdk.RemovalPolicy.RETAIN)
              
                cdk.CfnOutput(self, f"{pset_id_clean}output", value=sso_permission_set.attr_permission_set_arn, export_name=f"{pset_id_clean}output")       