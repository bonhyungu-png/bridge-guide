---
name: bridge-guide
description: 교량 안전점검 지침서 조회 화면을 연다. 표 조회·등급 판정·본문 검색을 GUI에서 직접 한다.
---

교량 지침서 가이드 — 자체완결형 웹앱(`webapp/bridge_guide.html`)을 사용자의
기본 브라우저로 연다. 표 조회 · 등급 판정 · 본문 검색을 그 화면에서 직접
누르고 입력하며 쓰는 도구이지, 내가 텍스트로 대신 읽어주는 게 아니다.

## 절차

1. 이 플러그인이 설치된 경로를 찾는다. `${CLAUDE_PLUGIN_ROOT}` 환경변수가
   있으면 그 값을 쓴다. 없으면 이 커맨드 파일(`commands/bridge-guide.md`)의
   부모 폴더(플러그인 루트)를 기준으로 `webapp/bridge_guide.html`을 찾는다.
2. OS에 맞는 명령으로 그 파일을 기본 브라우저로 연다.
   - Windows: `start "" "<경로>"` (cmd) 또는 `Start-Process "<경로>"` (PowerShell)
   - macOS: `open "<경로>"`
   - Linux: `xdg-open "<경로>"`
3. 사용자가 `$ARGUMENTS`에 질문을 함께 넣었다면, 파일을 열 때 URL에
   `?q=<질문>&tab=search`를 붙여 본문 검색 탭이 그 질의로 바로 시작하게 한다.
   질문이 표 번호나 표 제목처럼 보이면(`tab=anchor`, 기본값) 표 조회 탭으로 연다.
   예: `file:///C:/.../webapp/bridge_guide.html?tab=search&q=%EC%84%B8%EA%B5%B4`
   (공백·한글은 URL 인코딩한다)
4. 열었다고 짧게 알리고, 화면 안에서 표 조회 / 등급 판정 / 본문 검색을 직접
   써보라고 안내한다. 브라우저를 열 수 없는 환경(순수 API, 헤드리스 등)이면
   대신 `skills/bridge-guide/SKILL.md`의 절차로 돌아가 텍스트로 답한다.
