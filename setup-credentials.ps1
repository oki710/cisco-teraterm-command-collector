#requires -Version 5.1
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') {
    throw 'This credential store is Windows-only because it uses Windows DPAPI.'
}

$storeRoot = Join-Path $env:LOCALAPPDATA 'TeraTermCiscoMacros'
$storePath = Join-Path $storeRoot 'credentials.v1.json'

function Protect-PlainText {
    param([Parameter(Mandatory=$true)][string]$Value)
    $secure = ConvertTo-SecureString -String $Value -AsPlainText -Force
    try {
        ConvertFrom-SecureString -SecureString $secure
    }
    finally {
        $secure.Dispose()
    }
}

function Read-ProtectedSecret {
    param([Parameter(Mandatory=$true)][string]$Prompt)
    $secure = Read-Host $Prompt -AsSecureString
    try {
        if ($secure.Length -eq 0) {
            throw "$Prompt is required when this authentication method is enabled."
        }
        ConvertFrom-SecureString -SecureString $secure
    }
    finally {
        $secure.Dispose()
    }
}

function Read-AuthSet {
    param(
        [Parameter(Mandatory=$true)][string]$Label,
        [Parameter(Mandatory=$true)][bool]$RequireEnable
    )

    $user = Read-Host "$Label username (blank = disable this method)"
    if ([string]::IsNullOrWhiteSpace($user)) {
        return [ordered]@{
            enabled = $false
            username = ''
            password = ''
            enable   = ''
        }
    }

    $user = $user.Trim()
    $userEncrypted = Protect-PlainText -Value $user
    $user = $null
    $passwordEncrypted = Read-ProtectedSecret -Prompt "$Label password"

    $enableEncrypted = ''
    if ($RequireEnable) {
        $enableEncrypted = Read-ProtectedSecret -Prompt "$Label enable password"
    }

    [ordered]@{
        enabled = $true
        username = $userEncrypted
        password = $passwordEncrypted
        enable   = $enableEncrypted
    }
}

Write-Host ''
Write-Host 'Cisco Tera Term credential setup'
Write-Host 'The saved values are DPAPI-protected for the current Windows user on this computer.'
Write-Host "Store: $storePath"
Write-Host ''

if (Test-Path -LiteralPath $storePath) {
    $answer = Read-Host 'Credential store already exists. Replace it? [y/N]'
    if ($answer -notmatch '^(?i:y|yes)$') {
        Write-Host 'Cancelled. Existing credential store was not changed.'
        exit 1
    }
}

$tacacs = Read-AuthSet -Label 'TACACS SSH' -RequireEnable $false
$commonSsh = Read-AuthSet -Label 'Common SSH' -RequireEnable $true
$commonTelnet = Read-AuthSet -Label 'Common Telnet' -RequireEnable $true

if (-not $tacacs.enabled -and -not $commonSsh.enabled -and -not $commonTelnet.enabled) {
    throw 'At least one authentication method must be enabled.'
}

if ($commonTelnet.enabled) {
    Write-Warning 'Telnet does not encrypt credentials on the network. Keep it as the final fallback only and follow your network policy.'
}

$payload = [ordered]@{
    schema    = 1
    createdAt = (Get-Date).ToString('o')
    tacacsSsh = $tacacs
    commonSsh = $commonSsh
    commonTelnet = $commonTelnet
}

New-Item -ItemType Directory -Path $storeRoot -Force | Out-Null
$tmpPath = "$storePath.tmp"
$json = $payload | ConvertTo-Json -Depth 5
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($tmpPath, $json, $utf8NoBom)
Move-Item -LiteralPath $tmpPath -Destination $storePath -Force

try {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $sid = $identity.User
    $acl = New-Object System.Security.AccessControl.FileSecurity
    $acl.SetOwner($sid)
    $acl.SetAccessRuleProtection($true, $false)
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $sid,
        [System.Security.AccessControl.FileSystemRights]::FullControl,
        [System.Security.AccessControl.AccessControlType]::Allow
    )
    [void]$acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $storePath -AclObject $acl
}
catch {
    Write-Warning "Credential store was encrypted, but ACL hardening failed: $($_.Exception.Message)"
}

Write-Host ''
Write-Host 'Credential store updated.'
Write-Host 'Run the macro through start-collector.cmd or start-capture.cmd.'
Write-Host ''
Write-Host 'Important: if multiple people share the same Windows account, DPAPI cannot distinguish those people.'
