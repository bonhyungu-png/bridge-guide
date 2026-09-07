# bridge-guide

「시설물의 안전 및 유지관리 실시 세부지침(**안전점검·진단 편**) **교량편**」 질의응답 플러그인.

2022 / 2023 / 2024 / 2026 네 판본을 함께 다루며, **모든 답변에 표 번호와 면수를 붙인다.**

---

## 왜 필요한가

미국 FHWA가 현직 교량점검자 49명에게 같은 교량을 점검시킨 연구(FHWA-RD-01-020)에서,
주요 부재 하나당 **평균 4~5개의 서로 다른 등급**이 매겨졌고 평균 ±1점 이내에 든 판정은 68%뿐이었다.
지침서를 못 찾아서가 아니라, 찾아 읽고도 다르게 판정하기 때문이다.

이 저장소는 그 변동성을 줄이는 것을 목표로 한다. 실제 정본 데이터를 진단해 보면
다음과 같은 문제가 측정된다 (`python build/00_validate.py`):

| 문제 | 실측 |
|---|---|
| 본문의 `표참조:` 링크 깨짐 | **14 / 271건 (5.2%)** — 2026 신설 5단계 종합등급 절차표 집중 |
| 지표명 오염 | 42개 중 **9개** (구간값 혼입, 문장 잘림) |
| 동의어 미통합 | `표면 손상면적` ≡ `표면손상 면적` ≡ `표면손상면적` 등 **3쌍** |
| 표 번호 연도별 밀림 | **5건** — 표1.31이 2024=케이블교량, 2026=일반교량 |
| 법령 참조 미연결 | **5종 20건** |
| 외부기준 미해결 | 건설기준코드 **91회** (조항 번호 없음) |

---

## 쓰는 법 — 두 가지

이 저장소는 **화면**과 **자유 질문**을 따로 제공한다. 둘 다 설치도 서버도 API 키도 필요 없다.

### 1. 화면 — 웹 GUI

`webapp/bridge_guide.html` **한 파일**에 4개 판본의 표·본문·판정규칙이 전부 들어 있다.
브라우저로 열기만 하면 인터넷 없이도 그대로 돈다.

- **표 조회** — 번호나 제목으로 찾고, 연도별 번호 밀림을 배지로 경고한다
- **등급 판정** — 부재·지표·값을 넣으면 페이지 안의 코드가 구간을 대조해 등급·원문·출처를 보여준다
- **본문 검색** — 문단을 찾고, `표참조:` 칩을 눌러 해당 표를 바로 편다

```bash
python build/20_아티팩트_데이터.py   # 데이터가 바뀌었을 때만
python build/21_웹앱_빌드.py         # webapp/bridge_guide.html 재생성
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
  "source": { "table": "1.11", "page": "1-27" }
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
4. **내용은 한 곳, 어댑터는 얇게.** 행동 지침은 `skills/bridge-guide/SKILL.md`에만 있고,
   `CLAUDE.md` · `GEMINI.md` · `AGENTS.md`는 그 파일을 가리키는 한 줄이다.
5. **어느 창에서 물어도 같은 답.** 모든 경로가 `bridgekb` 한 엔진을 부른다.

---

## 구조

```
bridge-guide/
├── .claude-plugin/       Claude Code 플러그인 매니페스트
├── commands/             /bridge-guide 슬래시 커맨드
├── skills/bridge-guide/  ★ 행동 지침 (유일한 원본)
├── bridge_mcp.py         MCP 진입점 (어느 폴더에서 실행해도 됨)
├── .mcp.json             이 저장소를 열었을 때의 자동 등록
├── bridgekb/             ★ 조회 엔진 - LLM을 모른다
│   ├── anchor.py         표 조회 (연도 밀림 흡수)
│   ├── kb.py             판정규칙·본문 적재, 이름 맞추기
│   ├── tools.py          ★ 도구 6개 - MCP·CLI·웹앱이 공유하는 유일한 구현
│   ├── mcp_server.py     MCP stdio 서버 (의존성 없음)
│   ├── cli.py            모든 환경의 단일 진입점
│   └── providers/        API 어댑터 (교체 가능)
├── data/                 ★ 정본·파생 (번들 - 외부 폴더에 의존하지 않는다)
├── webapp/               웹 GUI (템플릿.html + 빌드된 bridge_guide.html)
├── index.html            GitHub Pages 진입점
├── build/                지식 빌드 파이프라인
│   ├── 00_validate.py    Phase 0 진단
│   ├── 20_아티팩트_데이터.py  웹앱용 데이터 번들
│   └── 21_웹앱_빌드.py    단일 파일 웹앱 조립
├── knowledge/            빌드 산출물 (손으로 고치지 않음)
│   └── _report/          진단 리포트
├── CLAUDE.md GEMINI.md AGENTS.md    한 줄 포인터
└── docs/design.md        설계 문서
```

---

## 진행 상황

- [x] **Phase 0** 진단 — 참조 무결성·지표명 품질 측정
- [x] 플러그인 골격 · 환경 어댑터 · `anchor` 도구
- [x] **Phase 1** 정본 통일 — 신버전 파서를 2022~2024에 소급, 4개 판본 일치 (잔여 4건은 계획 문서 참조)
- [ ] **Phase 2** 지식 빌드 (개념 사전 · 양방향 참조 · 법령 수집 · BM25)
- [x] **Phase 3** `grade` `search` + MCP 도구 6개 — `concept` `compare` `law`는 Phase 2 대기
- [x] **Phase 4** 웹 GUI · MCP 서버 — GitHub Pages 배포만 남음
- [ ] **Phase 5** 골든셋 검증 · 환경 간 답변 일치 테스트

## 라이선스

MIT
