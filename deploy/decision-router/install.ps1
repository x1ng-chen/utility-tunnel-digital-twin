param(
    [string]$Python = 'D:\shixi\utility-tunnel-digital-twin\artifacts\publish-agent-qa-20261025\Scripts\python.exe',
    [string]$RuntimeRoot = 'D:\shixi\utility-tunnel-runtime\anyjev'
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$runtime = [IO.Path]::GetFullPath($RuntimeRoot)
if ($runtime.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar) -or $runtime -eq $projectRoot) {
    throw '模型与独立环境必须放在Git工作区以外。'
}
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
$venvPython = Join-Path $runtime 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $Python -m venv (Join-Path $runtime 'venv')
    if ($LASTEXITCODE -ne 0) { throw '创建独立Python环境失败。' }
}
$env:PIP_CACHE_DIR = Join-Path $runtime 'pip-cache'
& $venvPython -m pip install 'torch==2.14.1+cu126' --index-url https://download.pytorch.org/whl/cu126 --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { throw 'PyTorch CUDA安装失败；未修改Django环境。' }
& $venvPython -m pip install -r (Join-Path $projectRoot 'services\decision-router\requirements.txt') --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { throw '推理依赖安装失败。' }
& $venvPython (Join-Path $projectRoot 'tools\anyjev\prepare_model.py') --runtime-root $runtime
if ($LASTEXITCODE -ne 0) { throw '模型准备失败；保留可续传文件。' }
$lock = Get-Content -LiteralPath (Join-Path $projectRoot 'services\decision-router\model.lock.json') -Raw | ConvertFrom-Json
$archive = Join-Path $runtime ('sources\anyjev-' + $lock.anyjevCommit + '.zip')
& $venvPython -m pip install --no-deps $archive --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { throw '固定提交AnyJev安装失败。' }
& $venvPython -m pip freeze | Set-Content -LiteralPath (Join-Path $runtime 'requirements.resolved.txt') -Encoding utf8
$tokenFile = Join-Path $runtime 'service-token.txt'
if (-not (Test-Path -LiteralPath $tokenFile)) {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $rng.Dispose()
    [Convert]::ToBase64String($bytes) | Set-Content -LiteralPath $tokenFile -Encoding ascii
}
Write-Output '本地决策环境和固定模型已准备；尚未启动服务，未开启付费模型。'
Write-Output ('令牌仅保存在运行目录：' + $tokenFile)
