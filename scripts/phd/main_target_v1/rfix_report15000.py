"""Keep the first health-stop endpoint report separate from the authorized continuation."""
import rfix_continue_report as R
R.D=R.D/'endpoint15000';R.F=R.D/'figures';R.T=R.D/'tables'
R.main()
path=R.D/'보고서.md'
text=path.read_text().replace('(진행.md)','(../진행.md)').replace('(실행예외.md)','(../실행예외.md)').replace('(기록정의.md)','(../기록정의.md)')
text+='\n이 문서는 첫 15,000회 중단 시점의 기록이다. 후속 사용자 결정으로 수 검사만 해제한 이어 학습은 [전체 보고서](../보고서.md)에 별도로 기록한다.\n'
path.write_text(text)
