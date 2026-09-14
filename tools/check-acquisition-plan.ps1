param([string]$PlanPath = (Join-Path $PSScriptRoot '../hardware/acquisition-plan-2026-09-11.json'))
$ErrorActionPreference = 'Stop'
$plan = Get-Content -LiteralPath $PlanPath -Raw -Encoding utf8 | ConvertFrom-Json
if ($plan.status -eq 'SUPERSEDED_DO_NOT_IMPLEMENT') {
    throw 'Historical plan superseded. Use 重构采集与接线基线_2026-09-11.md and check-demo-topology.ps1.'
}
$failures = [System.Collections.Generic.List[string]]::new()
foreach ($field in @('id','route','terminal')) {
    foreach ($group in ($plan.points | Group-Object -Property $field)) {
        if ($group.Count -ne 1) { $failures.Add("Duplicate $field : $($group.Name)") }
    }
}
foreach ($kind in @('MQ4','MQ7','ME2O2','MQ2','SHT30','FLAME')) {
    $points = @($plan.points | Where-Object kind -eq $kind)
    if ($points.Count -ne 5) { $failures.Add("Count mismatch: $kind") }
    if (@($points.zone | Select-Object -Unique).Count -ne 5) { $failures.Add("Not distributed: $kind") }
}
foreach ($zone in @('Z1','Z2','Z3','Z4','Z5')) {
    $water = @($plan.points | Where-Object { $_.zone -eq $zone -and $_.kind -eq 'FSIR02' })
    if ($water.Count -ne 1) { $failures.Add("Expected exactly one water point: $zone") }
    if (@($water | Where-Object inventory_status -ne 'planned_existing_quantity').Count -ne 0) {
        $failures.Add("Unapproved water sensor addition: $zone")
    }
}
if ($plan.fsir02_quantity_limit -ne 5 -or @($plan.points | Where-Object kind -eq 'FSIR02').Count -ne 5) {
    $failures.Add('FSIR02 inventory must remain exactly five')
}
foreach ($group in ($plan.expansion | Group-Object { "$($_.bus):$($_.address)" })) {
    if ($group.Count -ne 1) { $failures.Add("I2C root address conflict: $($group.Name)") }
}
$allowedDirect = @('CTRL-01:PC2/ADC1_IN12','CTRL-01:PC1/ADC1_IN11','CTRL-01:PB12','CTRL-01:PB14','CTRL-01:PC0')
foreach ($point in $plan.points) {
    if ($point.route.StartsWith('CTRL-') -and $point.route -notin $allowedDirect) { $failures.Add("Unexpected direct pin: $($point.route)") }
    if ($point.model_ready -or $point.implementation_status -ne 'DESIGN_ONLY') { $failures.Add("Unverified implementation claim: $($point.id)") }
    if ($point.route -match '^EADC-\d+:AIN([0-9]+)$' -and [int]$Matches[1] -gt 3) { $failures.Add("Invalid ADC channel: $($point.route)") }
    if ($point.route -match '^EDIO-\d+:P([0-9])([0-9])$' -and ([int]$Matches[1] -gt 1 -or [int]$Matches[2] -gt 7)) { $failures.Add("Invalid GPIO bank: $($point.route)") }
}
if ($failures.Count) { throw ($failures -join "`n") }
[pscustomobject]@{
    result = 'PASS_LOGICAL_ALLOCATION_ONLY'
    totalDesignPoints = $plan.points.Count
    existingPlanPoints = @($plan.points | Where-Object inventory_status -eq 'planned_existing_quantity').Count
    additionsAwaitingApproval = @($plan.points | Where-Object inventory_status -eq 'PROPOSED_ADD_NOT_APPROVED').Count
    modelChangeGates = $plan.model_change_gate
    disclaimer = 'No electrical, pressure, installation or firmware acceptance implied'
} | ConvertTo-Json -Depth 4
