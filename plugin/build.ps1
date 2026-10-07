<#
.SYNOPSIS
  Build the DriveDogs Radar SDK plugin (and/or its unit tests) with MSVC.
.DESCRIPTION
  -Test   build + run the SDK-independent core tests (no SCS SDK needed)
  default build ..\output\plugin\ddradar.dll; needs the SCS Telemetry SDK unpacked so that
          plugin\sdk\include\scssdk.h exists (not committed - SCS licence)
#>
param([switch]$Test)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here
$vcvars = Get-ChildItem 'C:\Program Files\Microsoft Visual Studio\*\*\VC\Auxiliary\Build\vcvars64.bat' |
    Select-Object -First 1
if (-not $vcvars) { throw 'vcvars64.bat not found (install VS with the C++ workload)' }

$obj = Join-Path $root 'build\plugin'
New-Item -ItemType Directory -Force $obj | Out-Null

function Invoke-Msvc([string]$cmd) {
    # a .bat sidesteps cmd.exe's quote stripping for paths with spaces
    $bat = Join-Path $obj 'msvc.bat'
    Set-Content -Encoding ascii $bat "@call `"$($vcvars.FullName)`" >nul`r`n@$cmd"
    & cmd.exe /c $bat
    if ($LASTEXITCODE -ne 0) { throw "build failed: $cmd" }
}

if ($Test) {
    $exe = Join-Path $obj 'test_core.exe'
    Invoke-Msvc "cl /nologo /std:c++17 /EHsc /W4 /O2 /Fo`"$obj/`" /Fe`"$exe`" `"$here\tests\test_core.cpp`""
    & $exe (Join-Path $root 'data\camera_db.csv')
    exit $LASTEXITCODE
}

$sdk = Join-Path $here 'sdk\include'
if (-not (Test-Path (Join-Path $sdk 'scssdk.h'))) {
    throw "SCS SDK headers not found in $sdk (see docs/POC-PLAN.md)"
}
$out = Join-Path $root 'output\plugin'
New-Item -ItemType Directory -Force (Join-Path $out 'ddradar') | Out-Null
Invoke-Msvc ("cl /nologo /std:c++17 /EHsc /W4 /O2 /LD /I`"$sdk`" /Fo`"$obj/`" " +
    "/Fe`"$out\ddradar.dll`" `"$here\src\plugin.cpp`" /link /DEF:`"$here\src\ddradar.def`"")
Copy-Item (Join-Path $root 'data\camera_db.csv') (Join-Path $out 'ddradar\camera_db.csv') -Force
Write-Host "built $out\ddradar.dll (+ ddradar\camera_db.csv)"
