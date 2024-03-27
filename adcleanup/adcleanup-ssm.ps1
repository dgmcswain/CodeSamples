# Main variable definition (combined and improved)
$queueUrl = 'https://sqs.us-east-1.amazonaws.com/123456789012/ADCleanup-SQS'
$messageCount = (Get-SQSQueueAttribute -QueueUrl $queueUrl -AttributeName ApproximateNumberOfMessages -Region us-east-1).ApproximateNumberOfMessages
$credentials = New-Object System.Management.Automation.PSCredential((Get-SSMParameterValue -Name adcleanup_user).Parameters[0].Value, (Get-SSMParameterValue -Name adcleanup_password -WithDecryption $True).Parameters[0].Value | ConvertTo-SecureString -AsPlainText -Force)
$dnsZone = "aws.domain.org"
$successArray = @()
$errorArray = @()
$snstopic = 'arn:aws:sns:us-east-1:123456789012:ADCleanup-SNS'

# Define Cleanup Functions (combined and improved error handling)
function Remove-InstanceFromAD {
    param (
        [Parameter(Mandatory = $true)]
        [string] $serverName,
        [string] $os,
        [string] $instanceId,
        [string] $accountId,
        [switch] $RemoveAD = $true,
        [switch] $RemoveDNS = $true
    )

    try {
        if ($RemoveAD -and (Get-ADComputer -Identity $serverName -Credential $credentials)) {
            Remove-ADObject -Identity $serverName -Credential $credentials -Confirm:$False -ErrorAction Stop
            $successArray += "Info: Removing '$os' Server '$serverName' from AD. Associated with '$instanceId' in account '$accountId'"
        }
        if ($RemoveDNS) {
            $dnsRecord = Get-DnsServerResourceRecord -ZoneName $dnsZone -Name $serverName
            $dnsRecordMgmt = Get-DnsServerResourceRecord -ZoneName $dnsZone -Name ($serverName + "-mgt") -ErrorAction SilentlyContinue
            if ($dnsRecord) {
                Remove-DnsServerResourceRecord -ZoneName $dnsZone -RRType $dnsRecord.RecordType -Name $serverName -Force -ErrorAction Stop
                $successArray += "Info: Removing DNS record '$serverName' from Forward Lookup Zone '$dnsZone'"
            }
            if ($dnsRecordMgmt) {
                Remove-DnsServerResourceRecord -ZoneName $dnsZone -RRType $dnsRecordMgmt.RecordType -Name ($serverName + "-mgt") -Force -ErrorAction Stop
                $successArray += "Info: Removing DNS record '$serverName-mgt' from Forward Lookup Zone '$dnsZone'"
            }
        }
    } catch {
        $errorArray += @("************** Error **************",
            $_.Exception.Message,
            "Info: Error removing '$os' Server '$serverName' associated with '$instanceId' in account '$accountId'.")
    }
}

# Process SQS Queue
if ($messageCount -gt 0) {
    Write-Output (((date | Out-String).Trim() + " EST - ") + "There are '$messageCount' servers queued for AD/DNS Cleanup.")
    while ($messageCount -gt 0) {
        $message = Receive-SQSMessage -QueueUrl $queueUrl -Region us-east-1
        $messageBody = $message.Body | ConvertFrom-Json
        $serverName = $messageBody.InstanceName
        $os = $messageBody.OS
        $instanceId = $messageBody.InstanceId
        $accountId = $messageBody.AccountId
        $exclude = $messageBody.Exclude

        switch ($exclude) {
            "AD" {
                Write-Output "Info: '$serverName' excluded from AD Cleanup operation."
                if ($os -like '*Windows*') {
                    Remove-InstanceFromAD -ServerName $serverName -OS $os -InstanceId $instanceId -AccountId $accountId -RemoveDNS
                }
            }
            "DNS" {
                Write-Output "Info: '$serverName' excluded from DNS Cleanup operation."
                Remove-InstanceFromAD -ServerName $serverName -OS $os -InstanceId $instanceId -AccountId $accountId -RemoveAD
            }
            "All" {
                Write-Output "Info: '$serverName' excluded from AD & DNS Cleanup operations."
                Break
            }
            default {
                Write-Output "Info: 'ExcludeFromCleanup' tag of instance '$instanceId'
