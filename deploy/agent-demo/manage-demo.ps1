param(
    [ValidateSet('setup','start','stop','backup','restore')][string]$Action='start',
    [ValidateSet('capabilities','demo')][string]$Profile='capabilities',
    [string]$PythonPath,
    [switch]$Rag,
    [string]$File,
    [switch]$NoPaidModel,
    [switch]$AllowPaidModel,
    [switch]$EnableRouter,
    [string]$KeyEnvFile
)
$ErrorActionPreference='Stop'
$demoRoot=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$stateName=if($Profile -eq 'capabilities'){'.agent-capabilities'}else{'.agent-demo'}
$demoPython=if($PythonPath){$PythonPath}else{Join-Path $demoRoot "$stateName\venv\Scripts\python.exe"}
if (-not (Test-Path -LiteralPath $demoPython)) { $demoPython='python' }
$demoArgs=@((Join-Path $PSScriptRoot 'manage_demo.py'),$Action,'--profile',$Profile)
if ($PythonPath) { $demoArgs+=@('--python',$PythonPath) }
if ($Rag) { $demoArgs+='--rag' }
if ($NoPaidModel) { $demoArgs+='--no-paid-model' }
if ($AllowPaidModel) { $demoArgs+='--allow-paid-model' }
if ($EnableRouter) { $demoArgs+='--enable-router' }
if ($File) { $demoArgs+=@('--file',$File) }
if ($KeyEnvFile) { $demoArgs+=@('--key-env-file',$KeyEnvFile) }
& $demoPython @demoArgs
if ($LASTEXITCODE -ne 0) { throw "Software demo command failed: $LASTEXITCODE" }
