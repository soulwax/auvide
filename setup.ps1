<#
  Compatibility wrapper. The maintained Windows provisioning script lives at
  desktop/setup.ps1.
#>
$desktopSetup = Join-Path $PSScriptRoot "desktop\setup.ps1"
& $desktopSetup @args
exit $LASTEXITCODE
