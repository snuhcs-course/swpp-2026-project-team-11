param([ValidateSet('host','api','daily')][string]$Mode='host', [string]$Root)
$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if(!$Root){$Root=Join-Path $repo '.local/hosting'}
$uv=Join-Path $Root 'tools/uv.exe'
if(!(Test-Path $uv)){$uv='uv'}
$python=Join-Path $Root 'tools/python/cpython-3.12.16-windows-x86_64-none/python.exe'
if(!(Test-Path $python)){throw 'Install Python 3.12.16 before starting the service.'}
if($Mode -eq 'daily'){
    & $uv run --isolated --locked --project $repo --python $python python -X utf8 (Join-Path $PSScriptRoot 'daily_menus.py') --root $Root
}elseif($Mode -eq 'host'){
    & $uv run --isolated --locked --project $repo --python $python python -X utf8 (Join-Path $Root 'supervisor.py')
}else{
    & $uv run --isolated --locked --project $repo --python $python python -X utf8 (Join-Path $Root 'api.py')
}
exit $LASTEXITCODE
