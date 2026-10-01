# Deploy KidsGame Dimension Builder → IBM Code Engine app12 + Cloudflare app12.nextaura.fit
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$AppName = "app12-nextaura-fit"
$CeHost = "app12-nextaura-fit.284w7l87aq94.us-south.codeengine.appdomain.cloud"

Write-Host "==> Targeting IBM Code Engine nextaura-workflows"
ibmcloud target -g Default | Out-Null
ibmcloud target -r us-south | Out-Null
ibmcloud ce project select --name nextaura-workflows | Out-Null

$ErrorActionPreference = "Continue"
$null = ibmcloud ce application get --name $AppName 2>&1
$exists = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = "Stop"

if ($exists) {
  Write-Host "==> Updating CE app $AppName"
  & ibmcloud ce application update --name $AppName `
    --build-source . `
    --build-dockerfile Dockerfile `
    --build-strategy dockerfile `
    --port 8080 `
    --cpu 0.5 `
    --memory 1G `
    --min-scale 1 `
    --max-scale 1 `
    --wait
} else {
  Write-Host "==> Creating CE app $AppName"
  & ibmcloud ce application create --name $AppName `
    --build-source . `
    --build-dockerfile Dockerfile `
    --build-strategy dockerfile `
    --port 8080 `
    --cpu 0.5 `
    --memory 1G `
    --min-scale 1 `
    --max-scale 1 `
    --wait
}

if ($LASTEXITCODE -ne 0) { throw "Code Engine deploy failed" }

Write-Host "==> CE status"
ibmcloud ce application get --name $AppName

Write-Host "==> Deploying Cloudflare Worker nextaura-app12 → app12.nextaura.fit"
Set-Location (Join-Path $Root "cloudflare")
npx --yes wrangler deploy
if ($LASTEXITCODE -ne 0) { throw "Wrangler deploy failed" }

Write-Host "==> Smoke checks"
Start-Sleep -Seconds 4
try {
  $ce = Invoke-RestMethod -Uri "https://$CeHost/api/health" -TimeoutSec 45
  Write-Host "CE /api/health:" ($ce | ConvertTo-Json -Compress)
} catch {
  Write-Host "CE health pending:" $_.Exception.Message
}
try {
  $pub = Invoke-RestMethod -Uri "https://app12.nextaura.fit/health" -TimeoutSec 45
  Write-Host "Public /health:" ($pub | ConvertTo-Json -Compress)
} catch {
  Write-Host "Public health pending:" $_.Exception.Message
}
try {
  $api = Invoke-RestMethod -Uri "https://app12.nextaura.fit/api/health" -TimeoutSec 45
  Write-Host "Public /api/health:" ($api | ConvertTo-Json -Compress)
} catch {
  Write-Host "Public api health pending:" $_.Exception.Message
}

Write-Host ""
Write-Host "LIVE: https://app12.nextaura.fit" -ForegroundColor Green
