# Deprecated: use install_task.bat (Run as administrator)
Write-Host 'Use install_task.bat instead (right-click -> Run as administrator).' -ForegroundColor Yellow
& (Join-Path $PSScriptRoot 'install_task.bat')
exit $LASTEXITCODE
