param([string]$RecordPath = (Join-Path $PSScriptRoot '../hardware/bench/一区验收状态_2026-09-14.json'))
$ErrorActionPreference = 'Stop'
$zoneRecord = Get-Content -LiteralPath $RecordPath -Raw -Encoding utf8 | ConvertFrom-Json
$zoneExpected = @('Z1-01','Z1-02','Z1-03','Z1-04','Z1-05','Z1-06')
if ($zoneRecord.tests.Count -ne 6) { throw 'Expected six unique acceptance cases' }
if (@($zoneRecord.tests | Group-Object id | Where-Object Count -ne 1).Count) { throw 'Duplicate test ID' }
foreach ($zoneTest in $zoneRecord.tests) {
    if ($zoneTest.id -notin $zoneExpected -or $zoneTest.status -notin @('NOT_RUN','BLOCKED','FAIL','PASS')) { throw 'Invalid case or status' }
    if ($zoneTest.status -eq 'PASS') {
        if (-not $zoneTest.tester -or -not $zoneTest.tested_at -or -not $zoneTest.measurements -or @($zoneTest.evidence).Count -eq 0) {
            throw "PASS without test evidence: $($zoneTest.id)"
        }
        foreach ($zoneEvidence in $zoneTest.evidence) {
            if (-not [System.IO.Path]::IsPathRooted($zoneEvidence) -or -not (Test-Path -LiteralPath $zoneEvidence -PathType Leaf)) {
                throw "Evidence must be an existing absolute file path: $($zoneTest.id)"
            }
        }
    }
}
$zonePending = @($zoneRecord.tests | Where-Object status -ne 'PASS')
if ($zoneRecord.hardware_release -and ($zonePending.Count -or -not $zoneRecord.static_checks.physical_tests_executed)) {
    throw 'Hardware release contradicts outstanding tests'
}
# Automated checks only verify record consistency; even all PASS records require human review.
[pscustomobject]@{
    recordConsistency='PASS';acceptance= $(if ($zonePending.Count) {'BLOCKED'} else {'EVIDENCE_REQUIRES_REVIEW'})
    outstanding=$zonePending.id;hardwareRelease=$zoneRecord.hardware_release
} | ConvertTo-Json -Depth 4
