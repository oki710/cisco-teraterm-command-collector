#requires -Version 5.1
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') {
    throw 'This launcher is Windows-only because the credential store uses Windows DPAPI.'
}

$storePath = Join-Path (Join-Path $env:LOCALAPPDATA 'TeraTermCiscoMacros') 'credentials.v1.json'
$macroPath = Join-Path $PSScriptRoot 'collector.ttl'

if (-not (Test-Path -LiteralPath $storePath)) {
    throw ("Credential store not found: {0}{1}Run setup-credentials.ps1 first." -f $storePath, [Environment]::NewLine)
}
if (-not (Test-Path -LiteralPath $macroPath)) {
    throw "Macro not found: $macroPath"
}

$data = Get-Content -LiteralPath $storePath -Raw | ConvertFrom-Json
if ($data.schema -ne 1) {
    throw "Unsupported credential store schema: $($data.schema)"
}

function Unprotect-String {
    param([AllowEmptyString()][string]$CipherText)
    if ([string]::IsNullOrEmpty($CipherText)) {
        return ''
    }

    $secure = ConvertTo-SecureString -String $CipherText
    $bstr = [IntPtr]::Zero
    try {
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        if ($bstr -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
        $secure.Dispose()
    }
}

$envNames = @(
    'TT_TACACS_USER',
    'TT_TACACS_PASS',
    'TT_COMMON_SSH_USER',
    'TT_COMMON_SSH_PASS',
    'TT_COMMON_SSH_ENABLE',
    'TT_COMMON_TELNET_USER',
    'TT_COMMON_TELNET_PASS',
    'TT_COMMON_TELNET_ENABLE'
)

foreach ($name in $envNames) {
    Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
}

try {
    if ($data.tacacsSsh.enabled) {
        $env:TT_TACACS_USER = Unprotect-String $data.tacacsSsh.username
        $env:TT_TACACS_PASS = Unprotect-String $data.tacacsSsh.password
    }
    if ($data.commonSsh.enabled) {
        $env:TT_COMMON_SSH_USER = Unprotect-String $data.commonSsh.username
        $env:TT_COMMON_SSH_PASS = Unprotect-String $data.commonSsh.password
        $env:TT_COMMON_SSH_ENABLE = Unprotect-String $data.commonSsh.enable
    }
    if ($data.commonTelnet.enabled) {
        $env:TT_COMMON_TELNET_USER = Unprotect-String $data.commonTelnet.username
        $env:TT_COMMON_TELNET_PASS = Unprotect-String $data.commonTelnet.password
        $env:TT_COMMON_TELNET_ENABLE = Unprotect-String $data.commonTelnet.enable
    }

    $candidates = @()
    if ($env:TT_MACRO) { $candidates += $env:TT_MACRO }
    if ($env:TERATERM_MACRO_EXE) { $candidates += $env:TERATERM_MACRO_EXE }
    if ($env:ProgramFiles) {
        $candidates += (Join-Path $env:ProgramFiles 'teraterm5\ttpmacro.exe')
        $candidates += (Join-Path $env:ProgramFiles 'teraterm\ttpmacro.exe')
    }
    $programFilesX86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
    if ($programFilesX86) {
        $candidates += (Join-Path $programFilesX86 'teraterm5\ttpmacro.exe')
        $candidates += (Join-Path $programFilesX86 'teraterm\ttpmacro.exe')
    }

    $ttMacro = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if (-not $ttMacro) {
        throw 'ttpmacro.exe was not found. Set TT_MACRO or TERATERM_MACRO_EXE to its full path.'
    }

    & $ttMacro $macroPath
    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) { $exitCode = 0 }
}
finally {
    foreach ($name in $envNames) {
        Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
    }
    $data = $null
    [GC]::Collect()
}

exit $exitCode
