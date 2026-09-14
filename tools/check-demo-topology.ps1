param([Parameter(Mandatory=$true)][string]$EvidenceDirectory)
$ErrorActionPreference = 'Stop'
$demoPlan = Get-Content -LiteralPath (Join-Path $EvidenceDirectory 'demo-topology.json') -Raw -Encoding utf8 | ConvertFrom-Json
$demoInventory = Get-Content -LiteralPath (Join-Path $EvidenceDirectory 'inventory.json') -Raw -Encoding utf8 | ConvertFrom-Json
if ($demoPlan.points.Count -ne 35) { throw 'Expected 35 collection points' }
if (($demoPlan.points | Group-Object id | Where-Object Count -ne 1)) { throw 'Duplicate point ID' }
if (($demoPlan.points | Group-Object route | Where-Object Count -ne 1)) { throw 'Duplicate candidate route' }
foreach ($demoKind in @('FSIR02','MQ4','MQ7','ME2O2','MQ2','FLAME','SHT30')) {
    $demoPoints = @($demoPlan.points | Where-Object kind -eq $demoKind)
    if ($demoPoints.Count -ne 5 -or @($demoPoints.zone | Select-Object -Unique).Count -ne 5) { throw "Distribution failure: $demoKind" }
}
if (@($demoPlan.points | Where-Object state -ne 'NOT_CONNECTED').Count) { throw 'Unverified connected state' }
if ($demoPlan.feed_air_gap_m -lt 0.03) { throw 'Feed air gap lost' }
if ($demoInventory.assets.Count -ne 79 -or $demoInventory.counts.FSIR02 -ne 5) { throw 'Hardware count changed' }
$demoWater = @($demoPlan.points | Where-Object kind -eq 'FSIR02')
if (@($demoWater.x_m | Select-Object -Unique).Count -ne 5) { throw 'Water points not separated' }
if (@($demoWater | Where-Object { $_.threshold_axis_above_local_invert_mm -notin @(8,24) }).Count) { throw 'Unexpected water threshold' }
if ($demoPlan.status -ne 'DESIGN_CANDIDATE_NOT_COMMISSIONED') { throw 'Unverified commissioning claim' }
[pscustomobject]@{result='PASS_DESIGN_LOGIC_ONLY';points=35;FSIR02=5;registeredHardware=79;commissioned=$false} | ConvertTo-Json
