# Main variable definition
$queueurl = 'https://sqs.us-east-1.amazonaws.com/123456789012/ADCleanup-SQS'
$messages = Get-SQSQueueAttribute -QueueUrl $queueurl -AttributeName ApproximateNumberOfMessages -Region us-east-1
$messageCount = $messages.ApproximateNumberOfMessages
$global:username= (Get-SSMParameterValue -Name adcleanup_user).Parameters[0].Value
$global:password = (Get-SSMParameterValue -Name adcleanup_password -WithDecryption $True).Parameters[0].Value | ConvertTo-SecureString -asPlainText -Force
$global:cred = New-Object System.Management.Automation.PSCredential($username,$password)
$snstopic = 'arn:aws:sns:us-east-1:150370869210:ADCleanup-SNS'
$global:successarray = $Null
$global:errorarray = $Null

# Define Cleanup Functions
function Remove-HCQISNameFromAD($servername,$cred,$os,$instanceid,$accountid) {
    try {
        (Get-ADComputer -Identity $servername -Credential $cred | Remove-ADObject -Credential $cred -Confirm:$False -ErrorAction Stop | Out-String).trim()
        $successmsg = @((((date | Out-String).trim() + " EST - ") + "Info: Removing '$os' Server '$servername' from AD. Associated with '$instanceid' in account '$accountid'").trim())
        $global:successarray += $successmsg
    } catch {
        $out1 = Write-Output $_.Exception.Message
        $out2 = Write-Output "Info: Error removing '$os' Server '$servername' associated with '$instanceid' in account '$accountid'." 
        $errormsg = @("************** Error **************",
            ((date | Out-String).trim() + " EST - " + $out1).trim(),
            ((date | Out-String).trim() + " EST - " + $out2).trim())
        $global:errorarray += $errormsg
    }
}

function Remove-DNSRecord($servername,$servernamemgt) {
    $dnsrec = Get-DnsServerResourceRecord -ZoneName "aws.qualnet.org" -Name $servername
    $dnsrecmgt = Get-DnsServerResourceRecord -ZoneName "aws.qualnet.org" -Name $servernamemgt -ErrorAction Ignore
    if ($dnsrec) {
        Remove-DnsServerResourceRecord Get-ADComputer -Identity $servername -RRType $dnsrec.RecordType -Name $servername -Force -ErrorAction Stop
        $successmsg = @((((date | Out-String).trim() + " EST - ") + "Info: Removing DNS record '$servername' from Forward Lookup Zone 'aws.qualnet.org.'").trim())
        $global:successarray += $successmsg
    }
    if ($dnsrecmgt) {
        Remove-DnsServerResourceRecord -ZoneName "aws.qualnet.org" -RRType $dnsrecmgt.RecordType -Name $servernamemgt -Force -ErrorAction Stop
        $successmsg = @((((date | Out-String).trim() + " EST - ") + "Info: Removing DNS record '$servernamemgt' from Forward Lookup Zone 'aws.qualnet.org.'").trim())
        $global:successarray += $successmsg
    }
}

if ($messageCount -gt 0) {
    # Loop through messages and delete after processing
    (date | Out-String).trim() + " EST - " + "There are '$messageCount' servers queued for AD/DNS Cleanup."
    While ($messageCount -gt 0) {
        $messageTotal += 1
        $messageCount -= 1
        $message = Receive-SQSMessage -QueueUrl $queueurl -Region us-east-1
        $messagebody = $message.body | ConvertFrom-Json
        $servername = $messagebody.HCQISName
        $servernamemgt = $servername + "-mgt"
        $os = $messagebody.OS
        $instanceid = $messagebody.InstanceId
        $accountid = $messagebody.AccountId
        $exclude = $messagebody.Exclude
        # Exclusion Case Logic
        if ($exclude -ne 'Blank') {
            Switch ($exclude) {
                "AD" {
                    $out = Write-Output "Info: '$servername' excluded from AD Cleanup opeartion." 
                    ((date | Out-String).trim() + " EST - " + $out).trim()
                    if ($os -like '*Windows*') {Remove-DNSRecord($servername,$servernamemgt)}
                }
                "DNS" {
                    $out = Write-Output "Info: '$servername' excluded from DNS Cleanup opeartion." 
                    ((date | Out-String).trim() + " EST - " + $out).trim()
                    Remove-HCQISNameFromAD($servername,$cred,$os,$instanceid,$accountid)
                }
                "All" {
                    $out = Write-Output "Info: '$servername' excluded from AD & DNS Cleanup opeartions." 
                    ((date | Out-String).trim() + " EST - " + $out).trim()
                    Break
                }
                default {
                    $out = Write-Output "Info: 'HCQIS-ExcludeFromCleanup' tag of instance '$instanceid' contains an invlaid value of '$exclude'. Valid tag values are 'AD', 'DNS', or 'All'." 
                    ((date | Out-String).trim() + " EST - " + $out).trim()
                }
            }
        } else {
            Remove-HCQISNameFromAD($servername,$cred,$os,$instanceid,$accountid)
            Remove-DNSRecord($servername,$servernamemgt)
        }
        # Delete SQS Message
        try {
            Remove-SQSMessage -QueueUrl $queueurl -ReceiptHandle $message.ReceiptHandle -region us-east-1 -Force -ErrorAction Stop
        } catch {
            Write-Error $_.Exception.Message
        }
    }
    Write-Output $successarray
    Write-Output $errorarray
    $snsmessage = @("There were '$messageTotal' servers queued for AD Cleanup","`n",$successarray,$errorarray)
    $snsmessage = $snsmessage | Out-String
    Publish-SNSMessage -TopicArn $snstopic -subject "AD Cleanup Daily Log" -Message $snsmessage
    if ($errorarray -ne $Null) {
        $status = 1
    }
    exit $status
} else { 
    Write-Output (((date | Out-String).trim() + " EST - ") + "There are 0 servers queued for AD Cleanup.").trim()
    $snsmessage = (((date | Out-String).trim() + " EST - ") + "There are 0 servers queued for AD Cleanup.").trim()
    Publish-SNSMessage -TopicArn $snstopic -subject "AD Cleanup Daily Log" -Message $snsmessage
}