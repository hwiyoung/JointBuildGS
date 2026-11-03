# PHD-MAIN-RESCORE-v1 예외

- stage1 첫 실행은 읽기 전용 /repo 아래의 허용 스크립트 사본을 만들려다 차단됨. 계산 시작 전 실패. 호스트에서 허용 경로에 사본을 만들고 컨테이너에서는 읽기만 하도록 수정.
- stage0 Git diff 일반 검사는 생성 CSV의 CRLF를 공백으로 보고했다. 기존 CSV bytes는 유지하고 이후 검사에는 cr-at-eol을 적용한다.
