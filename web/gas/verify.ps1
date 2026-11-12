param([string]$PythonExecutable = 'python')
$ErrorActionPreference = 'Stop'
$candidateRoot = $PSScriptRoot
if (Test-Path -LiteralPath $PythonExecutable) {
    $PythonExecutable = (Resolve-Path -LiteralPath $PythonExecutable).Path
} else {
    $PythonExecutable = (Get-Command $PythonExecutable -ErrorAction Stop).Source
}
$nodeExecutable = (Get-Command node -ErrorAction Stop).Source
Push-Location -LiteralPath $candidateRoot
try {
    & $PythonExecutable -X utf8 --version
    if ($LASTEXITCODE -ne 0) { throw 'Python version check failed.' }
    & $nodeExecutable --version
    if ($LASTEXITCODE -ne 0) { throw 'Node version check failed.' }
    & $PythonExecutable -X utf8 tests/build-fixtures.py
    if ($LASTEXITCODE -ne 0) { throw 'Fixture generation failed.' }
    & $PythonExecutable -X utf8 -m pytest tests/test_api.py -q -p no:cacheprovider --junitxml=verification/api-junit.xml
    if ($LASTEXITCODE -ne 0) { throw 'API tests failed. Do not count this as a successful run.' }
    & $nodeExecutable tests/verify-gas.cjs
    if ($LASTEXITCODE -ne 0) { throw 'GAS mock tests failed.' }
    & $nodeExecutable tests/verify-browser.cjs
    if ($LASTEXITCODE -ne 0) { throw 'Local browser tests failed.' }
    Write-Output 'LOCAL verification finished. No database, cloud API, GAS deployment or GitHub write was performed.'
} finally {
    Pop-Location
}
