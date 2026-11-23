#Requires -Version 5.1
# MedInsure pipeline orchestrator (Windows PowerShell)
#
# Creates the database if missing, wipes project schemas/data, recreates schemas,
# then runs sql/00 through sql/07 in order with ON_ERROR_STOP.
#
# Usage (from sk2-capstone/):
#   .\scripts\run_pipeline.ps1                 # wipe schemas + full rebuild
#   .\scripts\run_pipeline.ps1 -Reset          # DROP + CREATE database, then rebuild
#   .\scripts\run_pipeline.ps1 -Reset -Yes     # same, skip confirmation
#
# Env overrides: PGHOST PGPORT PGUSER PGDATABASE (default medinsure) PGPASSWORD

[CmdletBinding()]
param(
    [switch]$Reset,

    [Alias('y')]
    [switch]$Yes,

    [Alias('h')]
    [switch]$Help
)

$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

$PgHost = if ($env:PGHOST) { $env:PGHOST } else { 'localhost' }
$PgPort = if ($env:PGPORT) { $env:PGPORT } else { '5432' }
$PgUser = if ($env:PGUSER) { $env:PGUSER } else { 'postgres' }
$DbName = if ($env:PGDATABASE) { $env:PGDATABASE } else { 'medinsure' }

function Show-Usage {
    Write-Host @"
Usage: $(Split-Path -Leaf $PSCommandPath) [-Reset] [-Yes] [-Help]

  (default)   Ensure DB exists; DROP schemas dw/staging/etl + reset public;
              then run sql/00-07 (full project rebuild).
  -Reset      DROP and CREATE database $DbName, then run sql/00-07.
  -Yes, -y    Skip confirmation prompts for destructive actions.
  -Help, -h   Show this help.

Environment: PGHOST PGPORT PGUSER PGDATABASE PGPASSWORD
"@
}

function Resolve-Psql {
    $cmd = Get-Command psql -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and (Test-Path -LiteralPath $cmd.Source)) {
        return $cmd.Source
    }

    $roots = @(
        'C:\Program Files\PostgreSQL',
        'C:\Program Files (x86)\PostgreSQL'
    )
    $found = foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        Get-ChildItem -Path $root -Filter psql.exe -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.Directory.Name -eq 'bin' -and $_.FullName -notmatch 'pgAdmin' }
    }
    $picked = $found | Sort-Object FullName -Descending | Select-Object -First 1
    if ($picked) { return $picked.FullName }

    Write-Host "ERROR: psql.exe was not found. Install PostgreSQL, or add its bin directory to PATH."
    exit 1
}

function Invoke-Psql {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Database,

        [string]$Command,

        [string]$File,

        [switch]$TuplesOnly,

        [switch]$IgnoreFailure
    )

    $psqlArgs = @(
        '-h', $script:PgHost,
        '-p', $script:PgPort,
        '-U', $script:PgUser,
        '-v', 'ON_ERROR_STOP=1',
        '-X',
        '-d', $Database
    )
    if ($TuplesOnly) { $psqlArgs += '-At' }
    if ($File) {
        $psqlArgs += @('-f', $File)
    }
    else {
        $psqlArgs += @('-c', $Command)
    }

    if ($TuplesOnly) {
        $output = & $script:PsqlExe @psqlArgs
        $code = $LASTEXITCODE
        if (-not $IgnoreFailure -and $code -ne 0) {
            throw "psql failed (exit $code)"
        }
        return $output
    }

    & $script:PsqlExe @psqlArgs
    $code = $LASTEXITCODE
    if (-not $IgnoreFailure -and $code -ne 0) {
        throw "psql failed (exit $code)"
    }
}

function Test-DatabaseExists {
    $quoted = $script:DbName.Replace("'", "''")
    $result = Invoke-Psql -Database 'postgres' -TuplesOnly -Command "SELECT 1 FROM pg_database WHERE datname = '$quoted'"
    return (($result | Out-String).Trim() -eq '1')
}

function New-ProjectDatabase {
    Write-Host ">>> Creating database $script:DbName"
    Invoke-Psql -Database 'postgres' -Command "CREATE DATABASE $script:DbName;"
}

function Remove-ProjectDatabase {
    $quoted = $script:DbName.Replace("'", "''")
    Write-Host ">>> Terminating connections to $script:DbName"
    Invoke-Psql -Database 'postgres' -IgnoreFailure -Command @"
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = '$quoted'
  AND pid <> pg_backend_pid();
"@ | Out-Null

    Write-Host ">>> DROP DATABASE $script:DbName"
    Invoke-Psql -Database 'postgres' -Command "DROP DATABASE IF EXISTS $script:DbName;"
}

function Clear-ProjectSchemas {
    Write-Host ">>> Dropping schemas dw, staging, etl and resetting public"
    Invoke-Psql -Database $script:DbName -Command @'
DROP SCHEMA IF EXISTS dw CASCADE;
DROP SCHEMA IF EXISTS staging CASCADE;
DROP SCHEMA IF EXISTS etl CASCADE;
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO public;
COMMENT ON SCHEMA public IS 'OLTP source tables for MedInsure claims';
'@
}

function Confirm-OrExit {
    param([Parameter(Mandatory = $true)][string]$Message)
    if ($script:Yes) { return }
    Write-Host "WARNING: $Message"
    $confirm = Read-Host "Type 'yes' to continue"
    if ($confirm -ne 'yes') {
        Write-Host 'Aborted.'
        exit 1
    }
}

function Invoke-SqlFile {
    param([Parameter(Mandatory = $true)][string]$RelativePath)
    Write-Host ''
    Write-Host '========================================'
    Write-Host ">>> $RelativePath"
    Write-Host '========================================'
    $full = Join-Path $script:Root ($RelativePath -replace '/', '\')
    Invoke-Psql -Database $script:DbName -File $full
}

if ($Help) {
    Show-Usage
    exit 0
}

if ($DbName -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
    Write-Host "ERROR: PGDATABASE must be a simple identifier (letters, numbers, underscore). Got: $DbName"
    exit 1
}

Set-Location $Root
$script:PsqlExe = Resolve-Psql
Write-Host ">>> Using $script:PsqlExe"

if ($Reset) {
    Confirm-OrExit "This will DROP database '$DbName' and delete all data."
    if (Test-DatabaseExists) {
        Remove-ProjectDatabase
    }
    New-ProjectDatabase
}
else {
    if (-not (Test-DatabaseExists)) {
        New-ProjectDatabase
    }
    else {
        Confirm-OrExit "This will wipe schemas/data in '$DbName' (dw, staging, etl, public) then rebuild."
    }
    Clear-ProjectSchemas
}

$steps = @(
    'sql/00_schemas.sql',
    'sql/01_oltp.sql',
    'sql/02_dw_ddl.sql',
    'sql/03_etl_dims.sql',
    'sql/04_etl_facts.sql',
    'sql/05_analytics.sql',
    'sql/06_tuning.sql',
    'sql/07_quality.sql'
)

$startedAt = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
Write-Host ''
Write-Host "Pipeline started at $startedAt"
Write-Host "Target: ${PgUser}@${PgHost}:${PgPort}/${DbName}"

foreach ($step in $steps) {
    $full = Join-Path $Root ($step -replace '/', '\')
    if (-not (Test-Path -LiteralPath $full)) {
        Write-Host "ERROR: missing file $full"
        exit 1
    }
    Invoke-SqlFile -RelativePath $step
}

$finishedAt = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
Write-Host ''
Write-Host '========================================'
Write-Host 'Pipeline finished successfully.'
Write-Host "Started:  $startedAt"
Write-Host "Finished: $finishedAt"
Write-Host '========================================'
