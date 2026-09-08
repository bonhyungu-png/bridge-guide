# bridge-guide

「시설물의 안전 및 유지관리 실시 세부지침(**안전점검·진단 편**) **교량편**」 질의응답 플러그인.

---

## 왜 필요한가

미국 FHWA가 현직 교량점검자 49명에게 같은 교량을 점검시킨 연구(FHWA-RD-01-020)에서,
주요 부재 하나당 **평균 4~5개의 서로 다른 등급**이 매겨졌고 평균 ±1점 이내에 든 판정은 68%뿐이었다.
지침서를 못 찾아서가 아니라, 찾아 읽고도 다르게 판정하기 때문이다.

이 저장소는 그 변동성을 줄이는 것을 목표로 한다. 실제 정본 데이터를 진단해 보면
다음과 같은 문제가 측정된다:

| 문제 | 실측 |
|---|---|
| 본문의 `표참조:` 링크 깨짐 | **14 / 271건 (5.2%)** — 2026 신설 5단계 종합등급 절차표 집중 |
| 지표명 오염 | 42개 중 **9개** (구간값 혼입, 문장 잘림) |
| 동의어 미통합 | `표면 손상면적` ≡ `표면손상 면적` ≡ `표면손상면적` 등 **3쌍** |
| 표 번호 연도별 밀림 | **5건** — 표1.31이 2024=케이블교량, 2026=일반교량 |
| 법령 참조 미연결 | **5종 20건** |
| 외부기준 미해결 | 건설기준코드 **91회** (조항 번호 없음) |

---

## 쓰는 법 — 세 가지 창구

같은 엔진(`bridgekb`)을 세 가지 창구가 나눠 쓴다. 창만 다르고 답은 같다.
설치할 것은 파이썬 3.10 이상뿐이고, **특정 회사 도구에 매이지 않는다.**

| 창구 | 무엇이 필요한가 | 언제 쓰나 |
|---|---|---|
| **웹 화면** (`서버.py`) | 이 컴퓨터의 AI 하나 (아래 참고) | 사람이 직접 물어볼 때 |
| **MCP 서버** (`bridge_mcp.py`) | MCP를 지원하는 AI 도구 | 이미 쓰는 AI에 붙일 때 |
| **CLI / 파이썬** (`python -m bridgekb`) | 없음 | 스크립트·자동화 |

### 1. 웹 화면 — 물어보고, 근거가 된 PDF 쪽을 눈으로 본다

```bash
python 서버.py
```

http://127.0.0.1:8765 이 열린다. 질문을 넣으면 왼쪽에 질문 목록이 쌓이고,
가운데에 답이 뜬다. 답 아래 **출처**에는 그 답이 인용한 표가 실제로 실린
**원본 PDF 쪽을 잘라낸 그림**이 나열된다 — 누르면 크게 볼 수 있고
Ctrl+휠로 확대·축소된다.

```
브라우저 질문 → 서버.py → engines.ask() → 도구 6개 → 답 + 인용한 PDF 쪽
```

**엔진은 이 컴퓨터에 있는 것을 자동으로 고른다.** 무엇이 잡히는지 확인:

```bash
python 서버.py --engines
```

| 엔진 | 필요한 것 | 비고 |
|---|---|---|
| `claude-cli` | Claude Code 설치·로그인 | 도구 호출 내역을 정확히 읽는다 |
| `gemini-cli` | Gemini CLI 설치·로그인 | MCP 등록 필요 (아래) |
| `codex-cli` | Codex CLI 설치·로그인 | MCP 등록 필요 (아래) |
| `anthropic-api` | `ANTHROPIC_API_KEY` | 도구 루프를 서버가 직접 돈다 |
| `gemini-api` | `GEMINI_API_KEY` | 〃 |
| `openai-api` | `OPENAI_API_KEY` | 〃 |

CLI 엔진은 **이미 낸 구독을 그대로 쓴다**(API 키·추가 요금 없음). API 엔진은
키에 요금이 붙지만 도구 호출을 서버가 직접 돌리므로 출처가 가장 정확하다.
직접 고르려면 `python 서버.py --engine gemini-cli` 또는 환경변수
`BRIDGE_GUIDE_ENGINE`.

> 출처 그림에는 `pdfplumber`와 `data/원본pdf/*.pdf`가 필요하다.
> 없으면 답은 그대로 나오고 그림만 안 뜬다.

### 1-2. 터미널에서 바로 묻기

화면 없이도 같은 답을 받는다. 엔진 선택 규칙도 같다.

```bash
python -m bridgekb ask "콘크리트 바닥판 균열폭 0.25mm면 몇 등급이야?"
python -m bridgekb engines        # 쓸 수 있는 AI 목록
```

### 2. 자유 질문 — MCP 서버

등급을 코드가 판정한다는 원칙은 지키면서 자유롭게 묻고 싶다면 MCP로 붙인다.
**우리가 AI를 부르는 게 아니라, 이미 쓰고 있는 AI가 우리 도구를 집어 쓴다** —
그래서 API 키도 서버 비용도 들지 않는다.

명령어가 아니라 도구다. `/무언가`를 치는 게 아니라 **그냥 자연어로 물으면** 된다.

```
콘크리트 바닥판 균열폭 0.25mm면 몇 등급이야?
표1.31이 2024년이랑 2026년이랑 같은 표야?
선택과업은 언제 실시해?
```

의존성은 없다. **파이썬 3.10 이상**만 있으면 된다.

#### 등록 방법 (환경마다 한 번씩)

아래에서 `<저장소>`는 이 폴더의 **절대경로**다.

**Claude Code**

```bash
claude mcp add bridge-guide -- python <저장소>/bridge_mcp.py
```

이 저장소를 열어서 쓰는 경우엔 `.mcp.json`이 이미 있으므로 등록이 필요 없다.

**Cursor** — `~/.cursor/mcp.json` (프로젝트 한정이면 `.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "bridge-guide": { "command": "python", "args": ["<저장소>/bridge_mcp.py"] }
  }
}
```

**VS Code (GitHub Copilot)** — `.vscode/mcp.json`

```json
{
  "servers": {
    "bridge-guide": { "type": "stdio", "command": "python", "args": ["<저장소>/bridge_mcp.py"] }
  }
}
```

**Gemini CLI** — `~/.gemini/settings.json`

```json
{
  "mcpServers": {
    "bridge-guide": { "command": "python", "args": ["<저장소>/bridge_mcp.py"] }
  }
}
```

**Codex CLI** — `~/.codex/config.toml`

```toml
[mcp_servers.bridge-guide]
command = "python"
args = ["<저장소>/bridge_mcp.py"]
```

**ChatGPT** — 붙지 않는다. ChatGPT는 원격(HTTP) MCP 커넥터만 지원하고 이 서버는
로컬 stdio 방식이다. ChatGPT에서 쓰려면 웹 GUI를 쓰거나, 서버를 HTTP로
감싸 어딘가에 올려야 한다(그러면 무료·무설치라는 전제가 깨진다).

#### 등록됐는지 확인

```bash
python -m bridgekb tools     # 노출되는 도구 6개의 명세
python -m bridgekb doctor    # 지식베이스 상태
```

#### MCP 도구 6개

| 도구 | 하는 일 |
|---|---|
| `list_members` | 그 판본의 부재·지표 목록 (이름이 애매할 때 먼저 부른다) |
| `grade_lookup` | 부재·지표·값 → **등급 + 근거 원문 + 출처**. 등급이 정해지는 유일한 자리 |
| `qualitative_criteria` | 서술형(정성) 기준 목록. 등급을 확정하지 않고 후보만 준다 |
| `table_lookup` | 표 번호·제목 검색 + 연도별 번호 밀림 경고 |
| `table_content` | 표 하나의 실제 내용 |
| `body_search` | 본문 문단 검색 |

서버는 접속할 때 행동 지침(`instructions`)도 함께 보낸다 — 등급을 직접
계산하지 말 것, 모든 사실에 출처를 붙일 것, 표 번호는 연도를 확인할 것.

---

## 도구 (CLI)

MCP·웹앱·CLI가 **같은 파이썬 함수**를 부른다. 창만 다르고 답은 같다.
출력은 전부 JSON이다.

```bash
python -m bridgekb doctor                          # 지식베이스 상태 점검
python -m bridgekb tools                           # 도구 명세 (MCP와 동일)
python -m bridgekb mcp                             # MCP 서버 (stdio)
python -m bridgekb anchor "1.31"                   # 표 조회 (연도별 번호 밀림 경고)
python -m bridgekb anchor "일반교량 가중치"          # 제목으로 조회
python -m bridgekb grade "콘크리트 바닥판" 균열폭 0.25  # 등급 판정
python -m bridgekb search 선택과업                   # 본문 검색
python -m bridgekb concept <검색어>                 # 손상 이름 -> 정식 항목 (준비 중)
python -m bridgekb compare <부재> <항목>             # 연도별 비교 (준비 중)
python -m bridgekb law <조문>                       # 법령 원문 (준비 중)
```

### 예시 — 등급 판정

```
$ python -m bridgekb grade "콘크리트 바닥판" 균열폭 0.25
{
  "found": true,
  "year": "2026",
  "grade": "b",
  "quote": "균열폭 0.1㎜이상～0.3㎜미만",
  "source": { "table": "1.11", "page": 29 }
}
```

### 예시 — 표 번호 밀림

```
$ python -m bridgekb anchor "1.31"
{
  "질의": "표1.31",
  "연도별": {
    "2022": { "제목": "구조형식에 따른 케이블교량의 부재별 가중치" },
    "2026": { "제목": "구조형식에 따른 일반교량의 부재별 가중치" }
  },
  "경고": "같은 번호가 연도마다 다른 표를 가리킵니다."
}
```

---

## 설계 원칙

1. **사실은 코드가, 문장은 LLM이.** 등급 판정·표 조회·연도 비교는 전부 파이썬이 한다.
   LLM이 직접 수치를 비교해 등급을 정하지 않는다. 비용 때문이 아니라 **재현성** 때문이다.
2. **출처 없는 사실 문장을 쓰지 않는다.** 모든 답에 (연도, 표번호, 면수)를 붙인다.
3. **정본은 하나.** PDF → 정본 → 지식(빌드 산출물). 파생물을 손으로 고치지 않는다.
4. **지침은 한 곳에서 쓰고, 도구마다 복사해 둔다.** 원본은
   `skills/bridge-guide/SKILL.md` 하나뿐이고 `CLAUDE.md` · `GEMINI.md` ·
   `AGENTS.md`는 거기서 생성한다(`python build/30_지침_동기화.py`).
   `@경로` 한 줄 포인터로 두면 그 문법을 모르는 도구(Codex·Cursor·순수 API)에서는
   지침이 통째로 없는 것과 같아지기 때문이다. 어긋나면 테스트가 먼저 깨진다.
5. **어느 창에서 물어도 같은 답.** 모든 경로가 `bridgekb` 한 엔진을 부른다.
6. **AI 회사에 매이지 않는다.** 질문을 보낼 AI는 `bridgekb/engines.py`가 고른다 —
   Claude Code · Gemini CLI · Codex CLI · 세 공급사 API 중 있는 것을 쓴다.

---

## 구조

```
bridge-guide/
├── skills/bridge-guide/  ★ 행동 지침 (유일한 원본)
├── CLAUDE.md GEMINI.md AGENTS.md   위에서 생성 (build/30) - 도구별로 읽는 파일
├── .cursor/rules/        Cursor 규칙
├── .claude-plugin/ .codex-plugin/ gemini-extension.json   도구별 매니페스트
├── commands/             /bridge-guide 슬래시 커맨드 (Claude Code)
├── bridge_mcp.py         MCP 진입점 (어느 폴더에서 실행해도 됨)
├── .mcp.json             이 저장소를 열었을 때의 자동 등록
├── bridgekb/             ★ 조회 엔진 - LLM을 모른다
│   ├── anchor.py         표 조회 (연도 밀림 흡수)
│   ├── kb.py             판정규칙·본문 적재, 이름 맞추기
│   ├── tools.py          ★ 도구 6개 - MCP·CLI·웹앱이 공유하는 유일한 구현
│   ├── engines.py        ★ 질문을 보낼 AI 고르기 (CLI 3종 · API 3종)
│   ├── mcp_server.py     MCP stdio 서버 (의존성 없음)
│   ├── pdfnorm.py        원본 PDF 좌표계 맞추기
│   └── cli.py            모든 환경의 단일 진입점
├── 서버.py                웹 화면 + /ask + 출처 PDF 쪽 렌더링
├── 열기.py                서버를 띄우고 브라우저로 연다
├── examples/             순수 API로 붙이는 최소 예제
├── data/                 ★ 정본·파생 + 원본pdf (번들 - 외부 폴더에 의존하지 않는다)
├── webapp/               웹 GUI (템플릿.html + 빌드된 bridge_guide.html)
├── build/                빌드 파이프라인
│   ├── 16_출처페이지매핑.py     표 -> 실제 PDF 쪽 찾기
│   ├── 17_페이지값_보정.py      찾은 쪽을 데이터에 박기
│   ├── 20_아티팩트_데이터.py    웹앱용 데이터 번들
│   ├── 21_웹앱_빌드.py         단일 파일 웹앱 조립
│   └── 30_지침_동기화.py       SKILL.md -> CLAUDE/GEMINI/AGENTS.md
└── knowledge/            표 -> PDF 쪽 지도 (빌드 산출물)
```

---

## 진행 상황

- [x] **Phase 0** 진단 — 참조 무결성·지표명 품질 측정
- [x] 플러그인 골격 · 환경 어댑터 · `anchor` 도구
- [x] **Phase 1** 정본 통일 — 신버전 파서를 2022~2024에 소급, 4개 판본 일치
- [ ] **Phase 2** 지식 빌드 (개념 사전 · 양방향 참조 · 법령 수집 · BM25)
- [x] **Phase 3** `grade` `search` + MCP 도구 6개 — `concept` `compare` `law`는 Phase 2 대기
- [x] **Phase 4** 웹 GUI · MCP 서버 · 답 아래 원본 PDF 쪽 출처
- [x] **Phase 4-2** 엔진 다중화 — Claude Code 외 Gemini·Codex·API로도 질문
- [ ] **Phase 5** 골든셋 검증 · 환경 간 답변 일치 테스트

## 라이선스

MIT
