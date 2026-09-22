# SENTRA Hyperledger Fabric Windows PowerShell Wrapper
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$NetworkDir = Join-Path $ScriptDir "..\network"
$ChaincodeDir = Join-Path $ScriptDir "..\chaincode\sat-sa-integrity"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Starting SENTRA Hyperledger Fabric Local Permissioned Ledger" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

docker compose -f (Join-Path $NetworkDir "docker-compose-test-net.yaml") up -d
Push-Location $ChaincodeDir
& "C:\Program Files\Go\bin\go.exe" build -o SENTRA-integrity.exe .
Pop-Location

Write-Host "SENTRA Fabric Network started successfully." -ForegroundColor Green
