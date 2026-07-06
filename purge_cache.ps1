# Purge Creo / ModelCHECK / batch caches.
# Reads creo_loadpoint from app_settings.json next to this script (same as the GUI).

$ErrorActionPreference = 'Stop'

function Write-Step([string]$Message) {
    Write-Host $Message
}

function Remove-IfExists([string]$Path, [scriptblock]$Remove) {
    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Host "  (skip - not found: $Path)"
        return
    }
    & $Remove
}

function Get-CreoLoadpoint {
    $settingsPath = Join-Path $PSScriptRoot 'app_settings.json'
    if (-not (Test-Path -LiteralPath $settingsPath)) {
        throw "app_settings.json not found: $settingsPath"
    }
    $settings = Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $loadpoint = ($settings.creo_loadpoint -as [string]).Trim().TrimEnd('\', '/')
    if (-not $loadpoint) {
        throw "creo_loadpoint is empty in $settingsPath"
    }
    if (-not (Test-Path -LiteralPath $loadpoint)) {
        throw "creo_loadpoint path does not exist: $loadpoint"
    }
    return $loadpoint
}

function Get-ParametricBinLogFiles([string]$BinDir) {
    if (-not (Test-Path -LiteralPath $BinDir)) {
        return @()
    }
    $seen = @{}
    $files = @()
    foreach ($item in Get-ChildItem -LiteralPath $BinDir -File -Force -ErrorAction SilentlyContinue) {
        if ($item.Name -notmatch '\.log(\.\d+)?$') {
            continue
        }
        $key = $item.FullName.ToLowerInvariant()
        if ($seen.ContainsKey($key)) {
            continue
        }
        $seen[$key] = $true
        $files += $item
    }
    return $files
}

Write-Step '=== Purge cache ==='

# 1. ProgramData dbatch* folders
Write-Step ''
Write-Step '[1] Removing C:\ProgramData\dbatch* folders...'
$programData = 'C:\ProgramData'
$dbatchDirs = @(Get-ChildItem -LiteralPath $programData -Directory -Filter 'dbatch*' -ErrorAction SilentlyContinue)
if ($dbatchDirs.Count -eq 0) {
    Write-Host '  (none found)'
} else {
    foreach ($dir in $dbatchDirs) {
        Write-Host "  removing $($dir.FullName)"
        Remove-Item -LiteralPath $dir.FullName -Recurse -Force
    }
}

# 2. ModelCHECK mdlchk folder contents (current Windows user)
Write-Step ''
Write-Step '[2] Clearing ModelCHECK mdlchk folder...'
$mdlchkDir = Join-Path $env:APPDATA 'PTC\ProENGINEER\mdlchk'
Remove-IfExists $mdlchkDir {
    $files = @(Get-ChildItem -LiteralPath $mdlchkDir -File -Force -ErrorAction SilentlyContinue)
    if ($files.Count -eq 0) {
        Write-Host '  (no files)'
    } else {
        foreach ($file in $files) {
            Write-Host "  removing $($file.FullName)"
            Remove-Item -LiteralPath $file.FullName -Force
        }
    }
}

# 3-4. Creo Parametric\bin logs and dsm_cache
$loadpoint = Get-CreoLoadpoint
$binDir = Join-Path $loadpoint 'Parametric\bin'
$dsmCache = Join-Path $binDir 'dsm_cache'

Write-Step ''
Write-Step "[3] Removing Parametric\bin log files ($binDir)..."
Remove-IfExists $binDir {
    $logs = @(Get-ParametricBinLogFiles $binDir)
    if ($logs.Count -eq 0) {
        Write-Host '  (no log files)'
    } else {
        foreach ($log in $logs) {
            Write-Host "  removing $($log.FullName)"
            Remove-Item -LiteralPath $log.FullName -Force
        }
    }
}

Write-Step ''
Write-Step "[4] Removing dsm_cache ($dsmCache)..."
Remove-IfExists $dsmCache {
    Write-Host "  removing $dsmCache"
    Remove-Item -LiteralPath $dsmCache -Recurse -Force
}

Write-Step ''
Write-Step 'Done.'
