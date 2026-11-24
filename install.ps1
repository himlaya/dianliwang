$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$src = Join-Path $root "dist\电力王"
$dest = Join-Path $env:LOCALAPPDATA "Programs\电力王"
$target = Join-Path $dest "电力王.exe"

Write-Host "正在安装「电力王」..."

if (-not (Test-Path (Join-Path $src "电力王.exe"))) {
    Write-Host "[错误] 没有找到 dist\电力王\电力王.exe" -ForegroundColor Red
    Write-Host "       请先运行 build.cmd 打包。"
    exit 1
}

Get-Process -Name "电力王" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 400
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
New-Item -ItemType Directory -Path $dest -Force | Out-Null
Copy-Item (Join-Path $src "*") $dest -Recurse -Force

if (-not (Test-Path $target)) {
    Write-Host "[错误] 复制失败，请检查权限。" -ForegroundColor Red
    exit 1
}
Write-Host ("  已复制到 " + $dest)

$shell = New-Object -ComObject WScript.Shell
$shortcutDirs = @(
    [Environment]::GetFolderPath("Desktop"),
    (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs")
)
foreach ($dir in $shortcutDirs) {
    if (-not (Test-Path $dir)) { continue }
    $link = Join-Path $dir "电力王.lnk"
    $sc = $shell.CreateShortcut($link)
    $sc.TargetPath = $target
    $sc.WorkingDirectory = $dest
    $sc.IconLocation = $target + ",0"
    $sc.Description = "无线外设电量监视器"
    $sc.Save()
    Write-Host ("  已创建快捷方式 " + $link)
}

Write-Host ""
Write-Host "安装完成。桌面和开始菜单里都有「电力王」了。" -ForegroundColor Green
Write-Host "设置里可以打开「开机自动启动」。卸载请运行 卸载.cmd。"
