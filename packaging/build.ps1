# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later
param(
    [string]$Output = "$PSScriptRoot\..\dist\release",
    [string]$MakeNSIS = "${env:ProgramFiles(x86)}\NSIS\makensis.exe"
)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path "$PSScriptRoot\..").Path
$python = Join-Path $project '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Create .venv and install requirements before building.' }
if (!(Test-Path -LiteralPath $MakeNSIS)) { throw 'Install NSIS or pass -MakeNSIS with its absolute path.' }
$destination = [IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Force $destination | Out-Null
Push-Location $project
try {
    $version = (& $python -c "from ember import VERSION; print(VERSION)").Trim()
    if ($LASTEXITCODE -or $version -notmatch '^(\d+\.\d+\.\d+)(?:-[A-Za-z0-9.-]+)?$') { throw 'Invalid Ember version' }
    $versionQuad = "$($Matches[1]).0"
    & $python packaging/source.py --notices
    if ($LASTEXITCODE) { throw 'License collection failed.' }
    & $python -m PyInstaller --noconfirm --clean --distpath "$destination\payload" --workpath "$project\build\ember" build_ember.spec
    if ($LASTEXITCODE) { throw 'PyInstaller failed.' }
    & $python packaging/source.py --export "$destination\Ember-Source"
    if ($LASTEXITCODE) { throw 'Source audit/export failed. Use a fresh output folder.' }
    $payload = "$destination\payload\Ember"
    Copy-Item -LiteralPath "$destination\Ember-Source.zip" -Destination "$payload\Ember-Source.zip"
    Copy-Item -LiteralPath "$project\README-EMBER.txt" -Destination "$payload\README.txt"
    Copy-Item -LiteralPath "$project\LICENSE" -Destination "$payload\LICENSE"
    & $MakeNSIS "/DEMBER_VERSION=$version" "/DEMBER_VERSION_QUAD=$versionQuad" "/DPAYLOAD=$payload" "/DOUTPUT=$destination\Ember-Setup.exe" "$project\packaging\installer.nsi"
    if ($LASTEXITCODE) { throw 'NSIS failed.' }
    Get-FileHash -LiteralPath "$destination\Ember-Setup.exe", "$destination\Ember-Source.zip" -Algorithm SHA256 |
        ForEach-Object { "$($_.Hash.ToLower())  $([IO.Path]::GetFileName($_.Path))" } |
        Set-Content "$destination\SHA256SUMS.txt" -Encoding ascii
} finally { Pop-Location }
