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

## 설치

### Claude Code

```
/plugin marketplace add <your-github-id>/bridge-guide
/plugin install bridge-guide@bridge-guide
```

설치 후 `/bridge-guide` 로 사용한다.

```
/bridge-guide 콘크리트 바닥판 균열폭 0.25mm면 몇 등급이야?
/bridge-guide 표1.31이 뭐야?
/bridge-guide 데크플레이트 녹은 어느 항목으로 봐야 해?
```

### Gemini CLI

저장소를 클론한 뒤 확장으로 등록한다. `GEMINI.md`가 자동으로 읽힌다.

### Cursor · Codex

저장소를 열면 `.cursor/rules/` · `AGENTS.md`가 자동 적용된다.

### API 직접 사용 (Claude / Gemini / OpenAI / Ollama)

```bash
pip install -r requirements.txt
python -m bridgekb doctor
```

`bridgekb/providers/` 에 API 키를 설정하면 같은 도구를 function call로 쓸 수 있다.

---

## 도구

모든 환경이 같은 CLI를 호출한다. 출력은 전부 JSON이다.

```bash
python -m bridgekb doctor                     # 지식베이스 상태 점검
python -m bridgekb anchor "1.31"              # 표 조회 (연도별 번호 밀림 경고)
python -m bridgekb anchor "일반교량 가중치"     # 제목으로 조회
python -m bridgekb concept <검색어>            # 손상 이름 -> 정식 항목 (준비 중)
python -m bridgekb grade <부재> <지표> <값>     # 등급 판정 (준비 중)
python -m bridgekb compare <부재> <항목>        # 연도별 비교 (준비 중)
python -m bridgekb search <질의>               # 본문 검색 (준비 중)
python -m bridgekb law <조문>                  # 법령 원문 (준비 중)
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
├── bridgekb/             ★ 조회 엔진 - LLM을 모른다
│   ├── anchor.py         표 조회 (연도 밀림 흡수)
│   ├── cli.py            모든 환경의 단일 진입점
│   ├── providers/        API 어댑터 (교체 가능)
│   └── surfaces/         웹 UI · MCP 서버
├── build/                지식 빌드 파이프라인
│   └── 00_validate.py    Phase 0 진단
├── knowledge/            빌드 산출물 (손으로 고치지 않음)
│   └── _report/          진단 리포트
├── CLAUDE.md GEMINI.md AGENTS.md    한 줄 포인터
└── docs/design.md        설계 문서
```

---

## 진행 상황

- [x] **Phase 0** 진단 — 참조 무결성·지표명 품질 측정
- [x] 플러그인 골격 · 환경 어댑터 · `anchor` 도구
- [ ] **Phase 1** 정본 통일 (신버전 파서를 2022~2024에 적용)
- [ ] **Phase 2** 지식 빌드 (개념 사전 · 양방향 참조 · 법령 수집 · BM25)
- [ ] **Phase 3** 도구 완성 (`concept` `grade` `compare` `search` `law`)
- [ ] **Phase 4** 웹 UI · API 프로바이더
- [ ] **Phase 5** 골든셋 검증 · 환경 간 답변 일치 테스트

## 라이선스

MIT
