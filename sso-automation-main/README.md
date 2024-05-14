# SSO Group and Automations

## Developing

``` bash
To develop, add a python virtualenv .venv and install the dependencies:

python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
pip3 install -r requirements-dev.txt
```


## Policies

### Permission Set Definition

``` json
          {
            "permissionset_name": "RDSFullAccess",
            "relay_state": null,
            "description": "RDSFullAccess",
            "session_duration": "PT12H",
            "aws_managed_policies": [
                {
                    "Name": "AmazonRDSFullAccess",
                    "Arn": "arn:aws:iam::aws:policy/AmazonRDSFullAccess"
                }
            ]
        }
```

permissionset_name:

```

Name
The name of the permission set.

Required: Yes

Type: String

Minimum: 1

Maximum: 32

Pattern: [\w+=,.@-]+

Update requires: Replacement
```

mapped_permission_name: Only used for Permission Renaming

```
Name
The name of the permission set.

Required: Yes

Type: String

Minimum: 1

Maximum: 32

Pattern: [\w+=,.@-]+

Update requires: Replacement
```

relay_state
```
Used to redirect users within the application during the federation authentication process.

Required: No

Type: String

Minimum: 1

Maximum: 240

Pattern: [a-zA-Z0-9&$@#\\\/%?=~\-_'"|!:,.;*+\[\]\ \(\)\{\}]+

Update requires: No interruption

```


description

```
Description
The description of the AWS::SSO::PermissionSet.

Required: No

Type: String

Minimum: 1

Maximum: 700

Pattern: [\u0009\u000A\u000D\u0020-\u007E\u00A1-\u00FF]*

Update requires: No interruption
```

session_duration: 

```

The length of time that the application user sessions are valid for in the ISO-8601 standard.

Required: No

Type: String

Minimum: 1

Maximum: 100

Pattern: ^(-?)P(?=\d|T\d)(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)([DW]))?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$

Update requires: No interruption
```

aws_managed_policies: json list of any attached managed policies

```

A structure that stores the details of the AWS managed policy.

Required: No

Type: List of String ARNs

Update requires: No interruption

```

inline_policy_document_file
```

Relative path to the json file stored within this repo

Required: No

Type: File Path

Update requires: No interruption

Example: "./legacy-policies/DS0102-1004-data-forge-analyst.json"

```

### Cloud Management

### Workload-Shared

Inline policies for these roles are in the `policies` directory. They make up core roles that are reused across the wmg org.  

### Workload-Legacy

The inline policies are contained in the `./legacy-policies/*`

These are policies that are typically account specific/usecase specfic policies that typically targeting on legacy accounts.  

## Generating Policy Cloudformation Templates

To add a new policy you'll need to add config to the permission set definitions to the `.\config\permission-sets\*` directory (workload or legacy).

## Creating a new group

- Requirements: Elevated Rights(ER) Account
- Leverage tooling [here](https://github.com/wmgtech/wmg-gt-iam-identity-automation/tree/master/powershell/okta-infra-group-builder)

## Adding users to new group

- Bulk assignment can be done [here](https://github.com/wmgtech/wmg-gt-iam-identity-automation/tree/master/powershell/okta-ad-user-match)  

## Mapping a new group to an existing permission set  

Group: [REQUIRED] The OKTA group you are assigning  

PermissionSet: [REQUIRED] The permission set for which you want to assign to that group

AccountNum: [REQUIRED] The account in which to assign the above group and permissions to

AccountName: [REQUIRED] Used for naming resources within the cfn, should be consistent with the account name/alias


### Example Mapping  

``` jsonb
  {
    "Group": "ENT_OKTA_AWS_nonprod_projectname-poweruser",
    "PermissionSet": "AllAccountsPowerUser",
    "AccountName": "projectname-nonprod",
    "AccountNum": "123546789012"
  }

```

