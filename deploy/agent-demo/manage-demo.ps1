param([ValidateSet('setup','start','stop','backup','restore')][string]$Action='start',[switch]$Rag,[string]$File,[switch]$NoPaidModel)
$ErrorActionPreference='Stop'
$demoRoot=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$demoPython=Join-Path $demoRoot '.agent-demo\venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $demoPython)) { $demoPython='python' }
$demoArgs=@((Join-Path $PSScriptRoot 'manage_demo.py'),$Action)
if ($Rag) { $demoArgs+='--rag' }
if ($NoPaidModel) { $demoArgs+='--no-paid-model' }
if ($File) { $demoArgs+=@('--file',$File) }
& $demoPython @demoArgs
if ($LASTEXITCODE -ne 0) { throw "Demo command failed: $LASTEXITCODE" }
