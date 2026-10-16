# office_check.ps1 — разовая проверка офисных пакетов на АРМ
# Повод: CVE-2026-63277 (LibreOffice), CVE-2026-59265 (Apache OpenOffice).
# Бегущая строка условия: исполнение Java-кода из вредоносной таблицы Calc, если включена Java.
#
# Запуск (без прав администратора):
#   powershell -ExecutionPolicy Bypass -File office_check.ps1
# Отчёт сохраняется рядом со скриптом: <COMPUTERNAME>-<ПОЛЬЗОВАТЕЛЬ>.txt

$ErrorActionPreference = 'SilentlyContinue'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$out = Join-Path $dir ("{0}-{1}.txt" -f $env:COMPUTERNAME, $env:USERNAME)

$uninstall = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
$office = Get-ItemProperty $uninstall |
    Where-Object { $_.DisplayName -match 'LibreOffice|OpenOffice' } |
    ForEach-Object { '{0} {1}' -f $_.DisplayName, $_.DisplayVersion }

$java = Get-ChildItem 'HKLM:\SOFTWARE\JavaSoft' |
    Select-Object -ExpandProperty PSChildName
$java64 = Get-ChildItem 'HKLM:\SOFTWARE\WOW6432Node\JavaSoft' |
    Select-Object -ExpandProperty PSChildName

$os = (Get-CimInstance Win32_OperatingSystem).Caption

$lines = @(
    'computer=' + $env:COMPUTERNAME,
    'user=' + $env:USERNAME,
    'date=' + (Get-Date -Format 'yyyy-MM-dd HH:mm'),
    'os=' + $os,
    'office=' + (($office | Select-Object -Unique) -join '; '),
    'java_jre=' + (($java + $java64 | Where-Object { $_ } | Select-Object -Unique) -join ', ')
)
$lines | Set-Content -Encoding UTF8 -Path $out
Write-Host ('Отчёт сохранён: ' + $out)
