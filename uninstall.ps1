$ErrorActionPreference = 'Continue'
$dest = Join-Path $env:LOCALAPPDATA 'Programs\PeripheralBattery'

Write-Host '正在卸载「电力王」...'
Get-Process -Name '电力王' -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500

$shell = New-Object -ComObject WScript.Shell
$shortcutDirs = @(
    [Environment]::GetFolderPath('Desktop'),
    (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs')
)
foreach ($dir in $shortcutDirs) {
    $link = Join-Path $dir '电力王.lnk'
    if (Test-Path $link) {
        Remove-Item $link -Force
        Write-Host ('  已删除 ' + $link)
    }
}

Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' `
    -Name 'PeripheralBattery' -ErrorAction SilentlyContinue

if (Test-Path $dest) {
    Remove-Item $dest -Recurse -Force
    Write-Host ('  已删除 ' + $dest)
}

Write-Host ''
Write-Host '卸载完成。' -ForegroundColor Green
Write-Host ('配置文件仍保留在 ' + (Join-Path $env:APPDATA 'PeripheralBattery') + '，需要的话可手动删除。')
