---
name: bridge-guide
description: 교량 안전점검 지침서 조회 화면(웹 GUI)을 브라우저로 연다
argument-hint: [질문이나 표번호 - 생략 가능]
allowed-tools: Bash(python:*)
---

!`python "${CLAUDE_PLUGIN_ROOT}/열기.py" $ARGUMENTS`

위 명령이 교량 지침서 웹 GUI(`webapp/bridge_guide.html`)를 기본 브라우저로 열었다.

**한 문장으로 열었다고만 알리고 끝낸다.** 표 조회 · 등급 판정 · 본문 검색은
사용자가 그 화면에서 직접 누르고 입력하며 하는 것이지, 내가 텍스트로 대신
읽어주는 게 아니다. 화면 내용을 요약하거나 답을 추가로 만들지 않는다.

명령이 실패했으면(웹앱 파일이 없다는 등) 출력된 안내를 그대로 전한다.
브라우저를 열 수 없는 환경(헤드리스·순수 API)이면 스크립트가 주소만 찍고
물러나므로, 그때는 `skills/bridge-guide/SKILL.md`의 절차로 텍스트 답을 만든다.
