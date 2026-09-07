"""도구 6개 - 모든 환경(MCP · CLI · 웹앱)이 공유하는 유일한 구현.

웹앱(`webapp/템플릿.html`)의 `TOOLS` 배열이 이 도구들의 명세이자 먼저 만들어진
JS 구현이다. 여기 파이썬 구현은 **같은 이름, 같은 입력, 같은 출력 키**를 쓴다 -
그래야 브라우저에서 물어도 Cursor에서 물어도 같은 답이 나온다. 출력 키를
영어로 두는 것도 그래서다(웹앱 쪽을 따라간 것).

등급은 여기(`grade_lookup`)에서만 정해진다. 모델이 수치를 직접 비교해
등급을 말하는 것은 금지다 - 그 규칙은 `SYSTEM_RULES`에 적혀 있고 MCP 서버가
서버 지시문으로 함께 실어 보낸다.
"""
from __future__ import annotations

from . import anchor, kb

# 모델에게 주는 행동 지침. 웹앱 템플릿의 RULES와 같은 내용이다.
SYSTEM_RULES = """당신은 「시설물의 안전 및 유지관리 실시 세부지침(안전점검·진단 편) 교량편」 질의응답 도우미입니다.
2022 / 2023 / 2024 / 2026 네 개 판본을 다룹니다. 한국어로 답합니다.

반드시 지킬 규칙:
1. 등급을 스스로 계산하지 마세요. 수치 판정은 반드시 grade_lookup 도구를 호출하고, 도구가 돌려준 등급만 인용합니다. "0.25는 0.1~0.3 사이니까 b"처럼 직접 비교하는 것은 금지입니다.
2. 모든 사실에 출처를 붙입니다: (연도판, 표번호, 면). 도구가 돌려준 출처를 그대로 씁니다.
3. 표 번호는 판본마다 밀립니다. 표 번호로 답하기 전에 table_lookup으로 연도를 확인하고, 연도마다 다른 표를 가리키면 그 경고를 반드시 함께 전합니다.
4. 질문에 연도가 없으면 2026년판을 기본으로 쓰되, 답변에 "2026년판 기준"이라고 명시합니다.
5. 수치 없는 서술형(정성) 기준은 등급을 확정하지 마세요. 해당 기준 원문을 보여주고 최종 판단은 점검자 몫이라고 밝힙니다.
6. 도구가 못 찾으면 모른다고 답합니다. 지침서에 없는 내용을 지어내지 마세요.
7. 부재명·지표명이 애매하면 list_members로 실제 이름을 확인한 뒤 진행합니다.

알려진 함정: "데크플레이트 부식"은 철근부식이 아니라 누수 및 백태 계열 항목입니다. 표면손상은 부재에 따라 표면손상 / 열화 및 손상 / 표면열화로 이름이 다릅니다.

답변은 짧고 구체적으로. 등급이 나오면 첫 줄에 결론(등급), 다음 줄에 근거 원문, 마지막에 출처를 적습니다."""

_YEAR_PROP = {"type": "string",
              "description": "연도. 2022/2023/2024/2026 중 하나. 생략하면 2026."}


# ---------------- 도구 구현 ----------------

def list_members(year: str | None = None) -> dict:
    y = kb.year_of(year)
    return {
        "year": y,
        "members": [{"member": m, "indicators": kb.indicators(y, m)}
                    for m in kb.members(y)],
    }


def grade_lookup(member: str, indicator: str, value, year: str | None = None) -> dict:
    y = kb.year_of(year)
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError("value가 숫자가 아닙니다: %r" % (value,))

    m = kb.find_member(y, str(member or ""))
    if not m:
        return {"found": False, "reason": "그런 부재가 없습니다",
                "hint": "list_members로 실제 부재명을 확인하세요", "year": y}

    ind = kb.find_indicator(y, m, str(indicator or ""))
    if not ind:
        return {"found": False, "reason": "그 부재에 그런 지표가 없습니다",
                "member": m, "available_indicators": kb.indicators(y, m), "year": y}

    cands = [r for r in kb.numeric_rules(y) if r["부재"] == m and r["지표"] == ind]
    for r in cands:
        if kb.satisfies(r, v):
            return {"found": True, "year": y, "member": m, "indicator": ind, "value": v,
                    "grade": r["등급"], "quote": r["원문"], "unit": r.get("단위"),
                    "source": {"table": r["표"], "page": r["면"]}}

    return {"found": False, "reason": "이 값에 맞는 수치 구간이 없습니다", "year": y,
            "member": m, "indicator": ind, "value": v,
            "candidates": [{"grade": r["등급"], "quote": r["원문"],
                            "table": r["표"], "page": r["면"]} for r in cands]}


def qualitative_criteria(member: str, year: str | None = None) -> dict:
    y = kb.year_of(year)
    m = kb.find_member(y, str(member or "")) or kb.find_any_member(y, str(member or ""))
    if not m:
        return {"found": False, "reason": "그런 부재가 없습니다", "year": y}

    quals = [r for r in kb.rules(y) if r.get("연산") == "정성" and r.get("부재") == m]
    return {
        "found": bool(quals), "year": y, "member": m,
        "note": "정성 기준입니다. 등급을 확정하지 말고 후보로만 제시하세요.",
        "criteria": [{"grade": r["등급"], "item": r.get("항목"),
                      "text": str(r.get("원문") or "")[:300],
                      "table": r["표"], "page": r["면"]} for r in quals[:40]],
    }


def _number_index(index: dict) -> dict:
    """번호 -> {연도: 제목} 역색인. 같은 번호가 다른 표를 가리키는지 보려면 필요하다."""
    out: dict = {}
    for entry in index.values():
        for yr, info in entry["연도별"].items():
            if info["번호"]:
                out.setdefault(info["번호"], {})[yr] = entry["제목"]
    return out


def table_lookup(query: str) -> dict:
    q = kb.squash(str(query or ""))
    if not q:
        return {"found": False, "query": query}
    q_num = q.replace(".", "")

    index = anchor.index()
    hits = []
    for key, entry in index.items():
        번호일치 = any(info["번호"] and info["번호"].replace(".", "") == q_num
                   for info in entry["연도별"].values())
        if q in key or 번호일치:
            hits.append(entry)
    hits.sort(key=lambda e: e["제목"])
    hits = hits[:6]

    if not hits:
        return {"found": False, "query": str(query or "")}

    number_index = _number_index(index)
    results = []
    for entry in hits:
        by_year = {yr: ("표" + info["번호"]) if info["번호"] else "무번호"
                   for yr, info in sorted(entry["연도별"].items())}
        out = {"title": entry["제목"], "numbers_by_year": by_year}
        for yr, info in sorted(entry["연도별"].items()):
            no = info["번호"]
            if not no:
                continue
            others = number_index.get(no, {})
            if len(set(others.values())) > 1:
                out["warning"] = ("표%s은 연도마다 다른 표를 가리킵니다: " % no + " / ".join(
                    "%s=%s" % (yy, others[yy]) for yy in sorted(others)))
        results.append(out)
    return {"found": True, "results": results}


def table_content(title: str, year: str | None = None) -> dict:
    y = kb.year_of(year)
    t = kb.squash(str(title or ""))
    index = anchor.index()

    entry = index.get(t)
    if entry is None and t:
        for key, e in sorted(index.items(), key=lambda kv: kv[1]["제목"]):
            if t in key:
                entry = e
                break
    if entry is None:
        return {"found": False, "reason": "그 제목의 표가 없습니다"}

    info = entry["연도별"].get(y)
    if info is None:
        return {"found": False, "reason": "%s년판에는 이 표가 없습니다" % y,
                "available_years": sorted(entry["연도별"])}

    return {"found": True, "year": y, "title": entry["제목"], "number": info["번호"],
            "content": kb.read_table(info["경로"])[:6000]}


def body_search(query: str, year: str | None = None) -> dict:
    y = kb.year_of(year)
    q = str(query or "").strip()
    if not q:
        raise ValueError("query가 비었습니다")

    hits = []
    for section, text in kb.body_lines(y):
        if q in text:
            hits.append({"section": section, "text": text[:400]})
            if len(hits) >= 8:
                break
    return {"found": bool(hits), "year": y, "query": q, "hits": hits}


# ---------------- 명세 ----------------

SPECS = [
    {
        "name": "list_members",
        "description": "해당 연도판에서 수치 판정이 가능한 부재 목록과 각 부재의 지표 목록을 돌려준다. 사용자가 말한 부재·지표 이름이 실제 지침서 표기와 다를 때 정확한 이름을 찾기 위해 먼저 호출한다.",
        "inputSchema": {"type": "object", "properties": {"year": _YEAR_PROP}},
        "run": list_members,
    },
    {
        "name": "grade_lookup",
        "description": "부재·지표·실측값으로 등급을 판정한다. 판정규칙표를 코드가 직접 대조해 등급·근거 원문·출처(표번호,면)를 돌려준다. 등급은 반드시 이 도구로만 구한다. 맞는 구간이 없으면 후보 조건들을 돌려준다.",
        "inputSchema": {"type": "object", "properties": {
            "year": _YEAR_PROP,
            "member": {"type": "string", "description": "부재명. 예: 콘크리트 바닥판"},
            "indicator": {"type": "string", "description": "지표명. 예: 균열폭"},
            "value": {"type": "number", "description": "실측값(숫자). 예: 0.25"},
        }, "required": ["member", "indicator", "value"]},
        "run": grade_lookup,
    },
    {
        "name": "qualitative_criteria",
        "description": "해당 부재의 서술형(정성) 상태평가기준 목록을 등급별로 돌려준다. 수치가 없는 손상(균열 형태, 부식 상태 등)을 물었을 때 근거 원문을 보여주기 위해 쓴다. 이 기준으로는 등급을 확정하지 말고 후보로만 제시한다.",
        "inputSchema": {"type": "object", "properties": {
            "year": _YEAR_PROP,
            "member": {"type": "string", "description": "부재명"},
        }, "required": ["member"]},
        "run": qualitative_criteria,
    },
    {
        "name": "table_lookup",
        "description": "표 번호나 제목으로 표를 찾는다. 연도별 표 번호를 나란히 돌려주고, 같은 번호가 연도마다 다른 표를 가리키면 경고를 함께 돌려준다. 표 내용 자체가 필요하면 이어서 table_content를 호출한다.",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string",
                      "description": "표 번호(1.31) 또는 제목 일부(부재별 가중치)"},
        }, "required": ["query"]},
        "run": table_lookup,
    },
    {
        "name": "table_content",
        "description": "표 하나의 실제 내용(등급별 기준 원문)을 돌려준다. table_lookup으로 제목을 확인한 뒤 그 제목으로 호출한다. 길면 잘라서 돌려준다.",
        "inputSchema": {"type": "object", "properties": {
            "title": {"type": "string",
                      "description": "표 제목(table_lookup이 돌려준 title을 그대로)"},
            "year": _YEAR_PROP,
        }, "required": ["title"]},
        "run": table_content,
    },
    {
        "name": "body_search",
        "description": "지침서 본문 문단을 검색해 일치하는 문단들을 절 이름과 함께 돌려준다. 절차·정의·적용범위 같은 서술형 질문(선택과업은 언제 하는가, 중대한 결함이란)에 쓴다.",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string", "description": "검색어"},
            "year": _YEAR_PROP,
        }, "required": ["query"]},
        "run": body_search,
    },
]

BY_NAME = {spec["name"]: spec for spec in SPECS}


def descriptors() -> list[dict]:
    """MCP tools/list 에 실어 보낼 형태 (실행 함수는 뺀다)."""
    return [{k: v for k, v in spec.items() if k != "run"} for spec in SPECS]


def call(name: str, arguments: dict | None = None) -> dict:
    """이름으로 도구를 실행한다. 없는 이름이면 KeyError."""
    return BY_NAME[name]["run"](**(arguments or {}))
