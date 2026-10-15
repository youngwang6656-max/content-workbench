param([switch]$PrepareOnly,[switch]$FunctionsOnly)
$ErrorActionPreference='Stop'
# AI hosts may pass PowerShell 7 module paths to Windows PowerShell 5.1.
# Restore this process's native module search order, without changing system settings.
$env:PSModulePath=(Join-Path $PSHOME 'Modules')+';'+[Environment]::GetEnvironmentVariable('PSModulePath','Machine')+';'+[Environment]::GetEnvironmentVariable('PSModulePath','User')
$appRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
try { [Console]::OutputEncoding=New-Object Text.UTF8Encoding($false) } catch {}

function Get-UsablePython([string]$Command,[string[]]$Prefix=@()) {
    if (-not $Command -or $Command -match '\\WindowsApps\\') { return $null }
    try {
        $output=& $Command @Prefix -c 'import sys; print(sys.executable) if sys.version_info >= (3,12) else None; sys.exit(0 if sys.version_info >= (3,12) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $output) { return ([string]($output | Select-Object -Last 1)).Trim() }
    } catch {}
    return $null
}

function Assert-PythonArchive([string]$Path) {
    # SHA-512 from the official NuGet catalog, author Python Software Foundation.
    $expected='0ad3164e412912412d89ee9e8a9d8292893427812a67b9e43d8ef6766871faa7f10dc15899e3691c14e0336fd79da3d39eaa843eac1e3e056a9151ad336bac04'
    if ((Get-Item -LiteralPath $Path).Length -ne 14391248 -or (Get-FileHash -LiteralPath $Path -Algorithm SHA512).Hash.ToLowerInvariant() -ne $expected) {
        throw 'Python 运行包 SHA-512 校验失败，未解压或运行。请让 AI 检查网络或重新下载。'
    }
}

function Install-LocalPython {
    if (-not [Environment]::Is64BitOperatingSystem) { throw '自动准备仅支持 64 位 Windows。请把“给AI的启动说明.md”交给 AI 配置兼容环境。' }
    $runtimeBase=Join-Path $env:LOCALAPPDATA 'content-workbench-runtime'
    $runtimePath=Join-Path $runtimeBase 'python-3.13.15-portable'
    $existing=Get-UsablePython (Join-Path $runtimePath 'tools/python.exe')
    if ($existing) { return $existing }
    New-Item -ItemType Directory -Path $runtimeBase -Force | Out-Null
    $archive=Join-Path $runtimeBase 'python.3.13.15.nupkg'
    Write-Host '电脑上没有合适的 Python，正在下载免费的官方免安装环境（约 14 MB）…'
    [Net.ServicePointManager]::SecurityProtocol=[Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri 'https://api.nuget.org/v3-flatcontainer/python/3.13.15/python.3.13.15.nupkg' -OutFile $archive -UseBasicParsing
    Assert-PythonArchive $archive
    Write-Host '正在准备运行环境，请稍等…'
    # Extract into a fresh staging directory. No MSI, registry, admin or PATH change.
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $stage=Join-Path $runtimeBase ('prepare_'+[Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $stage | Out-Null
    $prefix=[IO.Path]::GetFullPath($stage)+[IO.Path]::DirectorySeparatorChar
    $zip=[IO.Compression.ZipFile]::OpenRead($archive)
    try {
        if ($zip.Entries.Count -gt 10000) { throw 'Python 运行包文件过多。' }
        $total=0L
        foreach($entry in $zip.Entries) {
            $total+=$entry.Length
            if ($total -gt 300MB) { throw 'Python 运行包解压大小异常。' }
            $name=$entry.FullName
            $target=[IO.Path]::GetFullPath((Join-Path $stage $name))
            if ($name.Contains(':') -or [IO.Path]::IsPathRooted($name) -or -not $target.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) { throw 'Python 运行包路径异常，未运行。' }
            if ($name.EndsWith('/')) { New-Item -ItemType Directory -Path $target -Force | Out-Null;continue }
            New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($target)) -Force | Out-Null
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry,$target,$false)
        }
    } finally { $zip.Dispose() }
    $executable=Join-Path $stage 'tools/python.exe'
    $signature=Get-AuthenticodeSignature -LiteralPath $executable
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') { throw 'Python 官方签名无法核实，未运行。' }
    if (Test-Path -LiteralPath $runtimePath) { throw '已有未完成的运行环境，请交给 AI 检查；文件已保留。' }
    Move-Item -LiteralPath $stage -Destination $runtimePath
    $python=Get-UsablePython (Join-Path $runtimePath 'tools/python.exe')
    if (-not $python) { throw 'Python 仍无法运行，已保留下载包与准备目录。' }
    return $python
}

function Start-Waypoint {
    Set-Location -LiteralPath $appRoot
    $logs=Join-Path $appRoot 'startup_logs';New-Item -ItemType Directory -Path $logs -Force | Out-Null
    $log=Join-Path $logs 'prepare.log'
    Write-Host '内容工作台（通用版） · 双击启动'
    Write-Host '首次准备需要联网；环境和依赖免费，API 不会自动开启。'
    if (-not $PrepareOnly) {
        try {
            $running=Invoke-RestMethod -Uri 'http://127.0.0.1:8766/api/session' -TimeoutSec 2
            if ($running.version) {
                $expected=(Get-Content -LiteralPath (Join-Path $appRoot 'waypoint/__init__.py') -Raw) -replace '(?s).*__version__\s*=\s*[''"]([^''"]+)[''"].*','$1'
                if ($running.version -ne $expected.Trim()) { throw ('已有旧工作台 '+$running.version+' 运行。请关闭旧启动窗口后再双击；不会自动停止其他程序。') }
                Write-Host ('本机已有 '+$running.version+' 工作台，正在打开。若要启用另一个目录中的源码修改，请先关闭旧服务。')
                Start-Process 'http://127.0.0.1:8766';return
            }
        } catch [System.Net.WebException] {} catch {
            # PowerShell 5.1 may not load System.Net.Http; never reference its type directly.
            if ($_.Exception.GetType().FullName -ne 'System.Net.Http.HttpRequestException') { throw }
        }
    }
    Write-Host '[1/3] 检查运行环境…'
    $venv=Join-Path $appRoot '.venv';$venvPython=Join-Path $venv 'Scripts/python.exe'
    $python=Get-UsablePython $venvPython
    if (-not $python) {
        $candidate=Get-Command py.exe -ErrorAction SilentlyContinue
        if ($candidate) { $python=Get-UsablePython $candidate.Source @('-3') }
        if (-not $python) {
            $candidate=Get-Command python.exe -ErrorAction SilentlyContinue
            if ($candidate) { $python=Get-UsablePython $candidate.Source }
        }
        if (-not $python) { $python=Install-LocalPython }
        if (Test-Path -LiteralPath $venv) {
            $resolved=[IO.Path]::GetFullPath($venv)
            if ([IO.Path]::GetDirectoryName($resolved) -ne $appRoot -or ((Get-Item -LiteralPath $venv).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw '运行环境路径需要核对，未移动任何文件。' }
            $saved=Join-Path $appRoot ('.venv_before_'+(Get-Date -Format 'yyyyMMddHHmmss'))
            Move-Item -LiteralPath $resolved -Destination $saved
        }
        & $python -m venv $venv *> $log
        if ($LASTEXITCODE -ne 0) { throw '准备独立运行环境失败。' }
    }
    Write-Host '[2/3] 准备程序依赖，首次可能需要几分钟…'
    $lock=Join-Path $appRoot 'requirements.lock';$hash=(Get-FileHash -LiteralPath $lock -Algorithm SHA256).Hash
    $stamp=Join-Path $venv 'waypoint_dependencies.sha256'
    $ready=(Test-Path -LiteralPath $stamp) -and ((Get-Content -LiteralPath $stamp -Raw).Trim() -eq $hash)
    if ($ready) {
        & $venvPython -c 'import fastapi,uvicorn,httpx,multipart,pypdf,docx,tzdata' *> $log
        $ready=$LASTEXITCODE -eq 0
    }
    if (-not $ready) {
        & $venvPython -m pip --isolated install --index-url https://pypi.org/simple -r $lock --disable-pip-version-check *> $log
        if ($LASTEXITCODE -ne 0) { throw '依赖准备失败，请检查网络；官方源错误已保留，没有关闭证书验证。' }
        [IO.File]::WriteAllText($stamp,$hash,[Text.Encoding]::ASCII)
    }
    if ($PrepareOnly) { Write-Host '环境已准备好，可双击“启动内容工作台.cmd”。';return }
    Write-Host '[3/3] 正在打开工作台…'
    Write-Host '请保持此窗口开启。首次进入设置自己的个人账号；模型账号由你自行登录。'
    & $venvPython -m waypoint.launcher
    if ($LASTEXITCODE -ne 0) { throw '程序未能启动，请保留上面的实际错误并交给 AI。' }
}

if ($FunctionsOnly) { return }
try { Start-Waypoint } catch {
    Write-Host ('启动未完成：'+$_.Exception.Message) -ForegroundColor Red
    Write-Host ('把整个程序文件夹和“给AI的启动说明.md”交给你的 AI，即可继续排错。日志：'+(Join-Path $appRoot 'startup_logs/prepare.log'))
    exit 1
}
