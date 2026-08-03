param(
    [string]$ExperimentHost = "innopam@192.168.10.203",
    [string]$Repository = "/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator"
)

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
& chcp.com 65001 | Out-Null

$remoteCommand = @"
cd '$Repository' || exit 2
echo '=== Experiment Host status ==='
printf 'HEAD: '
git rev-parse --short=12 HEAD
printf 'Latest record: '
git log -1 --pretty='%h %s'
printf 'Dirty file count: '
git status --porcelain | wc -l
echo 'Running JBGS containers:'
docker ps --format '{{.Names}} | {{.Status}}' | grep '^jbgs-' || echo 'NONE'
echo 'Running P2 workers:'
pgrep -af 'P2-|recovery_r|semantic_937|train.py|simple_trainer' | grep -v 'pgrep -af' || echo 'NONE'
"@

& ssh $ExperimentHost $remoteCommand
if ($LASTEXITCODE -ne 0) {
    throw "Experiment Host 상태 조회에 실패했습니다. SSH 연결과 호스트 주소를 확인하세요."
}
