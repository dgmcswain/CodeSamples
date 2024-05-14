import boto3
import csv
import json
import string
import time
import unicodedata

from datetime import datetime

"""
list_accounts

Lists all AWS accounts assigned to the user.

Parameters:
-- None
Returns:
-- List[Dictionary]: account_list (a list of accounts each described by a dictionary with keys 'name' and 'id')
"""
def list_accounts():
    account_list = []
    org = boto3.client('organizations')
    paginator = org.get_paginator('list_accounts')
    page_iterator = paginator.paginate()

    for page in page_iterator:
        for acct in page['Accounts']:
            # only add active accounts
            if acct['Status'] == 'ACTIVE':
                account_list.append({'name': acct['Name'], 'id': acct['Id']})

    return account_list

"""
list_existing_sso_instances

Lists the SSO instances that the caller has access to.

Parameters:
-- None
Returns:
-- List[Dictionary]: sso_instance_list (a list of sso instances each described by a dictionary with keys 'instanceArn' and 'identityStore')
"""
def list_existing_sso_instances():
    client = boto3.client('sso-admin')

    sso_instance_list = []
    response = client.list_instances()
    for sso_instance in response['Instances']:
        # add only relevant keys to return
        sso_instance_list.append({'instanceArn': sso_instance["InstanceArn"], 'identityStore': sso_instance["IdentityStoreId"]})

    return sso_instance_list

"""
list_permission_sets

Lists the PermissionSet in an SSO instance.

Parameters:
-- String: ssoInstanceArn
Returns:
-- Dictionary: perm_set_dict (a dictionary with permission sets with key permission set name and value permission set arn)
"""
def list_permission_sets(ssoInstanceArn):
    client = boto3.client('sso-admin')

    perm_set_dict = {}

    response = client.list_permission_sets(InstanceArn=ssoInstanceArn)

    results = response["PermissionSets"]
    while "NextToken" in response:
        response = client.list_permission_sets(InstanceArn=ssoInstanceArn, NextToken=response["NextToken"])
        results.extend(response["PermissionSets"])

    for permission_set in results:
        # get the name of the permission set from the arn
        perm_description = client.describe_permission_set(InstanceArn=ssoInstanceArn,PermissionSetArn=permission_set)
        # key: permission set name, value: permission set arn
        perm_set_dict[perm_description["PermissionSet"]["Name"]] = permission_set


    return perm_set_dict


"""
list_account_assignments

Lists the assignee of the specified AWS account with the specified permission set.

Parameters:
-- String: ssoInstanceArn
-- String: accountId
-- String: permissionSetArn
Returns:
-- List[Dictionary]: account_assignments (a list of account assignments represented by dictionaries with the keys 'PrincipalType' and 'PrincipalId')
"""
def list_account_assignments(ssoInstanceArn, accountId, permissionSetArn):
    client = boto3.client('sso-admin')

    paginator = client.get_paginator("list_account_assignments")

    response_iterator = paginator.paginate(
        InstanceArn=ssoInstanceArn,
        AccountId=accountId,
        PermissionSetArn=permissionSetArn
    )

    account_assignments = []
    for response in response_iterator:
        for row in response['AccountAssignments']:
            # add only relevant keys to return
            account_assignments.append({'PrincipalType': row['PrincipalType'], 'PrincipalId': row['PrincipalId']})

    return account_assignments


def is_group_assignmented_to_account(ssoInstanceArn, accountId, permissionSetArn, group):
    client = boto3.client('sso-admin')

    paginator = client.get_paginator("list_account_assignments")

    response_iterator = paginator.paginate(
        InstanceArn=ssoInstanceArn,
        AccountId=accountId,
        PermissionSetArn=permissionSetArn
    )
    group_found = False
    for response in response_iterator:
        for id in response['AccountAssignments']:
            if id['PrincipalId'] == group.get('GroupId',""):
              group_found = True
              # print(response)
              # print(f"Validated Group {group['DisplayName']} is assigned to Account {accountId}")

    return group_found

"""
describe_user

Retrieves the user metadata and attributes from user id in an identity store to return a human friendly username.

Parameters:
-- String: userId
-- String: identityStoreId
Returns:
-- Dictionary: username and userid
"""
def describe_user(userId, identityStoreId):
    client = boto3.client('identitystore')

    response = client.describe_user(
        IdentityStoreId=identityStoreId,
        UserId=userId
    )
    userName = response['UserName']
    userId = response['UserId']

    userInfo = {
      "userName": userName,
      "userId": userId
    }
    
    return userInfo

# def get_employee_remove_list():
#   emp_file = open("./scripts/employee_remove.txt", "r")
  
#   emp_data = emp_file.read()
  
#   emp_data = emp_data.split("\n")
#   # reading the file
#   emp_file.close()
  
#   return emp_data

# def is_a_blanket_remove(userName):
#     remove_list = get_employee_remove_list()
#     if userName in remove_list:
#       print(f"Found {userName} in remove list")
#       return True
#     elif userName in ["Jimmy.Zhu@wmg.com", "Tim.Yevdayev@wmg.com", "Taylor.Neill@wmg.com", "kkonig@navisite.com"]:
#       return True
#     elif "navisite.com" in userName:
#       return True
#     else:
#       return False

def get_group_members(identityStoreId, group_id):
    client = boto3.client('identitystore')
    member_list = []
    list_group_memberships_response = client.list_group_memberships(
        IdentityStoreId=identityStoreId,
        GroupId=group_id,
        MaxResults=100,
    )
    group_membership_response = list_group_memberships_response["GroupMemberships"]
    for group_membership in group_membership_response:
        member_id = format(group_membership["MemberId"]["UserId"])
        describe_user_response = client.describe_user(
            IdentityStoreId=identityStoreId,
            UserId=member_id
        )
        member_list.append(describe_user_response)
    return member_list


"""
remove_user_assignment

Retrieves the user metadata and attributes from user id in an identity store to return a human friendly username.

Parameters:
-- String: userId
-- String: identityStoreId
Returns:
-- Dictionary: username and userid
"""
# def remove_user_assignment(principalId, instance_arn, account, permission_set_arn, dry_run=False):
#     client = boto3.client('sso-admin')
#     if dry_run != True: 
#       print(f"Executing Delete of Assignment")
#       response = client.delete_account_assignment(
#           InstanceArn=instance_arn,
#           TargetId=account,
#           TargetType='AWS_ACCOUNT',
#           PermissionSetArn=permission_set_arn,
#           PrincipalType='USER',
#           PrincipalId=principalId
#       )
#     else: 
#       print(f"Skipping delete for dry run")

"""
is_member_in_group

Retrieves the group metadata and attributes from group id in an identity store to return a human friendly group name.

Parameters:
-- String: groupId
-- String: identityStoreId
Returns:
-- String: groupname (a human friendly groupname for the group id)
"""
def is_member_in_groups(memberID, groupId, identityStoreId):
    client = boto3.client('identitystore')
    try:
      response = client.is_member_in_groups(
          IdentityStoreId=identityStoreId,
          MemberId={
              'UserId': memberID
          },
          GroupIds=[
              groupId,
          ]
      )
      results = response['Results']
      return results[0]
    except Exception as e:
        print(e)


"""
find_permission_set_group_mapping

Retrieves the group metadata and attributes from group id in an identity store to return a human friendly group name.

Parameters:
-- String: groupId
-- String: identityStoreId
Returns:
-- String: groupname (a human friendly groupname for the group id)
"""
def find_permission_set_group_mapping(permission_set, accountId, identityStoreId):
  id_client = boto3.client('identitystore')
  with open('./config/mapping-legacy-groups.json') as f: 
    data = json.load(f)
    group = {}
    for item in data: 
      #print(f"{item}|{account}|{permission_set}")
      if accountId == item['AccountNum'] and permission_set == item['PermissionSet'] :
        group_response = id_client.list_groups(
        IdentityStoreId=identityStoreId,
          Filters=[{"AttributePath": "DisplayName", "AttributeValue": f"{item['Group']}"}],
            )
        
        group = group_response['Groups'][0]
  if len(group) != 1: #if we don't find the mapping in the legacy config, we check in the workload config
    with open('./config/mapping-workload-groups.json') as f: 
      data = json.load(f)
      for item in data: 
        #print(f"{item}|{account}|{permission_set}")
        if accountId == item['AccountNum'] and permission_set == item['PermissionSet']:
          group_response = id_client.list_groups(
          IdentityStoreId=identityStoreId,
            Filters=[{"AttributePath": "DisplayName", "AttributeValue": f"{item['Group']}"}],
              )
          group = group_response['Groups'][0]
  if len(group) != 1: #if we don't find the mapping in the legacy config, we check in the workload config
    with open('./config/mapping-management-groups.json') as f: 
      data = json.load(f)
      for item in data: 
        #print(f"{item}|{account}|{permission_set}")
        if accountId in item['account_assignments'] and permission_set == item['PermissionSet']:
          group_response = id_client.list_groups(
          IdentityStoreId=identityStoreId,
            Filters=[{"AttributePath": "DisplayName", "AttributeValue": f"{item['Group']}"}],
              )
          group = group_response['Groups'][0]
  return group

"""
describe_group

Retrieves the group metadata and attributes from group id in an identity store to return a human friendly group name.

Parameters:
-- String: groupId
-- String: identityStoreId
Returns:
-- String: groupname (a human friendly groupname for the group id)
"""
def describe_group(groupId, identityStoreId):
    client = boto3.client('identitystore')
    try:
        response = client.describe_group(
            IdentityStoreId=identityStoreId,
            GroupId=groupId
        )
        groupname = response['DisplayName']
        return groupname
    except Exception as e:
        print("[WARN] Group was deleted while the report was running: " + str(groupId))
        groupname = "DELETED-GROUP"
        return groupname


"""
create_report

Creates a report of the assigned permissions on users for all accounts in an organization.

Parameters:
-- List[Dictionary]: account_list (a list of accounts each described by a dictionary with keys 'name' and 'id')
-- List[Dictionary]: sso_instance (a list of sso instances each described by a dictionary with keys 'instanceArn' and 'identityStore')
-- Dictionary: permission_sets_list (a dictionary with permission sets with key permission set name and value permission set arn)
Returns:
-- List[Dictionary]: result (a list of dictionaries with keys 'AccountID', 'AccountName', 'PermissionSet', 'ObjectName', 'ObjectType')
"""
def create_report(account_list, sso_instance, permission_sets_list, break_after=None, dry_run=True):
    result = []

    # variables for displaying the progress of processed accounts
    length = str(len(account_list))
    i = 1

    for account in account_list:
        print(f"Identifying permissions for {account['name']}")
        for permission_set in permission_sets_list.keys():
            print(f"Identifying permissions for {account['name']} and {permission_set}")
            # get all the users assigned to a permission set on the current account
            account_assignments = list_account_assignments(sso_instance['instanceArn'], account['id'], permission_sets_list[permission_set])

            # add the users and additional information to the sso report result
            for account_assignment in account_assignments:

                account_assignments_dic = {}

                # add information for all the headers
                account_assignments_dic['AccountID'] = account['id']
                account_assignments_dic['AccountName'] = account['name']
                account_assignments_dic['PermissionSet'] = permission_set
                account_assignments_dic['ObjectType'] = account_assignment['PrincipalType']
                sso_instance_arn = sso_instance['instanceArn']
                pset_arn = permission_sets_list[permission_set]
                print(f"Identifying permissions for {account['name']} and {permission_set} and {pset_arn}")
                # find human friendly name for user id if principal type is "USER"
                if account_assignments_dic['ObjectType'] == "USER":
                    userinfo = describe_user(account_assignment['PrincipalId'], sso_instance['identityStore'])
                    userName = userinfo['userName']
                    userId = userinfo ['userId']
                    account_assignments_dic['ObjectName'] = userName
                    group = find_permission_set_group_mapping(permission_set=permission_set, accountId=account['id'],identityStoreId=sso_instance['identityStore'])
                    is_assigned = is_group_assignmented_to_account(ssoInstanceArn=sso_instance_arn, permissionSetArn=pset_arn, accountId=account['id'], group=group)
                    
                    if len(group) > 0: #if we have a mapped group for their combination
                      results = is_member_in_groups(memberID=userId, groupId=group['GroupId'], identityStoreId=sso_instance['identityStore']) 
                      if results['MembershipExists'] == True and is_assigned:  #and they are in the group
                        
                        account_assignments_dic['GroupMapping'] = "FoundInGroup"
                        account_assignments_dic['GroupId'] = results['GroupId']
                        account_assignments_dic['GroupName'] = group['DisplayName']
                        print(f"Group Identified: Remove {userName} | {userId} | {account['id']} | | {permission_set} | {pset_arn}  | {group['DisplayName']}")
                        #remove_user_assignment(principalId=userId, instance_arn=sso_instance_arn, account=account['id'], permission_set_arn=pset_arn,  dry_run=dry_run)
                      else:
                        account_assignments_dic['GroupMapping'] = "NotInGroup"
                        account_assignments_dic['GroupId'] = results['GroupId']
                        account_assignments_dic['GroupName'] = group['DisplayName']

                    else:
                      print(f"No Group Mapping Found: {userId} | {account['id']} | {userName} | {permission_set}")
                      account_assignments_dic['GroupMapping'] = "NotInMapping"
                      account_assignments_dic['GroupId'] = "NotInMapping"
                      account_assignments_dic['GroupName'] = "NotInMapping"

                # find human friendly name for group id if principal type is "GROUP"
                    
                elif account_assignments_dic['ObjectType'] == "GROUP":
                    group = find_permission_set_group_mapping(permission_set=permission_set, accountId=account['id'],identityStoreId=sso_instance['identityStore'])
                    is_assigned = is_group_assignmented_to_account(ssoInstanceArn=sso_instance_arn, permissionSetArn=pset_arn, accountId=account['id'], group=group)
                    group_id = group.get('GroupId',False)
                    if group_id:
                      group_members = get_group_members(sso_instance['identityStore'],group['GroupId'])
                      if group_members is not None:
                        for member in group_members:
                          group_assignments_dic = {}
                          group_assignments_dic['ObjectName'] = member['UserName']
                          group_assignments_dic['GroupName'] = group['DisplayName']
                          group_assignments_dic['GroupMapping'] = is_assigned
                          group_assignments_dic['GroupId'] = group_id
                          group_assignments_dic['AccountID'] = account['id']
                          group_assignments_dic['AccountName'] = account['name']
                          group_assignments_dic['PermissionSet'] = permission_set
                          group_assignments_dic['ObjectType'] = account_assignment['PrincipalType']
                          result.append(group_assignments_dic)
                result.append(account_assignments_dic)
        # display the progress of processed accounts
        print(str(i) + "/" + length + " accounts done")
        i = i+1

        # debug code used for stopping after a certain amound of accounts for faster testing
        if break_after != None and i > break_after:
            break

    return result

"""
write_result_to_file

Writes a list of dictionaries to a csv file.

Parameters:
-- String: result
Returns:
-- None
Output:
-- CSV file: CSV with SSO report.
"""
def write_result_to_file(result):
    filename = 'sso_report_Account_Assignments_' + datetime.now().strftime("%Y-%m-%d_%H.%M.%S") + '.csv'
    filename = clean_filename(filename)
    with open(filename, 'w', newline='') as csv_file:
        fieldnames = ['AccountID', 'AccountName', 'ObjectType', 'ObjectName', 'PermissionSet', 'GroupMapping', 'GroupId', 'GroupName'] # The header/column names
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

        writer.writeheader()
        for row in result:
            writer.writerow(row)

def print_time_taken(start, end):
    elapsed_time = end - start
    elapsed_time_string = str(int(elapsed_time/60)) + " minutes and "  + str(int(elapsed_time%60)) + " seconds"
    print("The report took " + elapsed_time_string + " to generate.")

def clean_filename(filename, replace=' ', char_limit=255):
    #allowed chars
    valid_filename_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)

    # replace spaces
    for r in replace:
        filename = filename.replace(r,'_')

    # keep only valid ascii chars
    cleaned_filename = unicodedata.normalize('NFKD', filename).encode('ASCII', 'ignore').decode()

    # keep only whitelisted chars
    cleaned_filename = ''.join(c for c in cleaned_filename if c in valid_filename_chars)
    if len(cleaned_filename)>char_limit:
        print("Warning, filename truncated because it was over {}. Filenames may no longer be unique".format(char_limit))
    return cleaned_filename[:char_limit]

"""
main

Output:
-- CSV file: CSV with SSO report.
"""
def main():
  
    dry_run = True
    start = time.time()
    account_list = list_accounts()
    sso_instance = list_existing_sso_instances()[0]
    permission_sets_list = list_permission_sets(sso_instance['instanceArn'])
    result = create_report(account_list, sso_instance, permission_sets_list, dry_run=dry_run)
    write_result_to_file(result)

    # print the time it took to generate the report
    end = time.time()
    print_time_taken(start, end)

main()
