"""도구 6개 - 등급이 정해지는 유일한 자리.

질문에 답하는 경로는 웹 하나뿐이다(`서버.py`). 브라우저가 `/ask`로 질문을
보내면 서버가 AI를 빌려 오고, AI는 여기 있는 도구를 호출한다. 도구 구현은
**이 파일 하나**다 - 예전에는 같은 도구가 웹앱 JS에도 복사돼 있어서 정렬
방식이 어긋나는 것만으로 창마다 다른 표를 돌려줬다. 사본을 없애 그 종류의
어긋남을 구조적으로 막는다.

등급은 `grade_lookup`에서만 정해진다. 모델이 수치를 직접 비교해 등급을
말하는 것은 금지이고, 그 규칙은 `SYSTEM_RULES`에 적혀 있다.

이름이 애매하면 **하나를 골라 답하지 않는다.** 걸린 후보를 그대로 돌려주고
모델이 되묻게 한다 - 조용히 고른 답에 출처까지 붙으면 틀렸다는 걸 아무도
알아챌 수 없기 때문이다.
"""
from __future__ import annotations

from . import anchor, kb

# 모델에게 주는 행동 지침. 서버가 시스템 프롬프트로 실어 보낸다.
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
8. 도구가 candidates를 돌려주며 "여러 개에 걸립니다"라고 하면, 그중 하나를 임의로 고르지 마세요. 후보를 사용자에게 보여주고 어느 것인지 되묻습니다. 예: 교면포장은 시멘트와 아스팔트가 서로 다른 표이고 등급도 다릅니다.

알려진 함정: "데크플레이트 부식"은 철근부식이 아니라 누수 및 백태 계열 항목입니다. 표면손상은 부재에 따라 표면손상 / 열화 및 손상 / 표면열화로 이름이 다릅니다.

답변은 짧고 구체적으로. 등급이 나오면 첫 줄에 결론(등급), 다음 줄에 근거 원문, 마지막에 출처를 적습니다.

값이 여럿을 나란히 놓는 답(등급별 기준, 연도별 비교, 부재별 목록)은 **마크다운 표**로 쓰세요.
읽는 쪽이 표로 그려 줍니다. 열은 3~4개를 넘기지 말고, 출처(연도판·표번호·면)는 표 아래에 적습니다.
값이 하나뿐인 답에는 표를 쓰지 마세요."""

_YEAR_PROP = {"type": "string",
              "description": "연도. 2022/2023/2024/2026 중 하나. 생략하면 2026."}


# ---------------- 도구 구현 ----------------

def _year_error(exc: kb.UnknownYear) -> dict:
    return {"found": False, "reason": str(exc), "available_years": exc.available}


def _ambiguous(kind: str, query: str, names: list, year: str) -> dict:
    """어느 쪽인지 못 정했다. 하나를 골라 답하지 않고 후보를 돌려준다.

    예전에는 걸린 것 중 첫 번째를 말없이 골랐다. "교면포장 포장불량률 5%"가
    시멘트(b등급)로 붙을지 아스팔트(c등급)로 붙을지 사용자는 알 수 없는데
    출처까지 붙어 나오니 확인할 방법도 없었다.
    """
    return {
        "found": False,
        "reason": "%s 이름이 여러 개에 걸립니다. 어느 것인지 정해야 답할 수 있습니다." % kind,
        "query": query,
        "candidates": names,
        "year": year,
    }


def list_members(year: str | None = None) -> dict:
    try:
        y = kb.year_of(year)
    except kb.UnknownYear as exc:
        return _year_error(exc)
    return {
        "year": y,
        "members": [{"member": m, "indicators": kb.indicators(y, m)}
                    for m in kb.members(y)],
    }


def grade_lookup(member: str, indicator: str, value, year: str | None = None) -> dict:
    try:
        y = kb.year_of(year)
    except kb.UnknownYear as exc:
        return _year_error(exc)
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError("value가 숫자가 아닙니다: %r" % (value,))

    m = kb.find_member(y, str(member or ""))
    if not m:
        return {"found": False, "reason": "그런 부재가 없습니다",
                "hint": "list_members로 실제 부재명을 확인하세요", "year": y}
    if m.ambiguous:
        return _ambiguous("부재", str(member or ""), m.names, y)
    name = m.one

    ind = kb.find_indicator(y, name, str(indicator or ""))
    if not ind:
        return {"found": False, "reason": "그 부재에 그런 지표가 없습니다",
                "member": name, "available_indicators": kb.indicators(y, name), "year": y}
    if ind.ambiguous:
        return _ambiguous("지표", str(indicator or ""), ind.names, y)

    # 같은 지표를 여러 표기로 적어 둔 표가 있다("표면 손상면적"/"표면손상면적").
    # 표기 하나만 보면 등급 구간이 통째로 빠진다 - PSC 거더 d등급(10%이상)이
    # 실제로 그렇게 사라져 있었다. 걸린 표기 전부를 후보로 삼는다.
    spellings = set(ind.names)
    cands = [r for r in kb.numeric_rules(y)
             if r["부재"] == name and r["지표"] in spellings]
    for r in cands:
        if kb.satisfies(r, v):
            out = {"found": True, "year": y, "member": name, "indicator": r["지표"],
                   "value": v, "grade": r["등급"], "quote": r["원문"],
                   "unit": r.get("단위"), "source": {"table": r["표"], "page": r["면"]}}
            if len(spellings) > 1:
                out["indicator_spellings"] = sorted(spellings)
            return out

    return {"found": False, "reason": "이 값에 맞는 수치 구간이 없습니다", "year": y,
            "member": name, "indicator": sorted(spellings)[0], "value": v,
            "candidates": [{"grade": r["등급"], "quote": r["원문"],
                            "table": r["표"], "page": r["면"]} for r in cands]}


def qualitative_criteria(member: str, year: str | None = None) -> dict:
    try:
        y = kb.year_of(year)
    except kb.UnknownYear as exc:
        return _year_error(exc)

    m = kb.find_member(y, str(member or "")) or kb.find_any_member(y, str(member or ""))
    if not m:
        return {"found": False, "reason": "그런 부재가 없습니다", "year": y}
    if m.ambiguous:
        return _ambiguous("부재", str(member or ""), m.names, y)
    name = m.one

    quals = [r for r in kb.rules(y) if r.get("연산") == "정성" and r.get("부재") == name]
    return {
        "found": bool(quals), "year": y, "member": name,
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


MAX_TABLE_HITS = 6


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
    total = len(hits)
    hits = hits[:MAX_TABLE_HITS]

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

    result = {"found": True, "results": results, "total": total}
    if total > len(results):
        # 잘렸다는 사실을 숨기면 모델이 "그런 표는 없다"고 답해 버린다.
        result["truncated"] = True
        result["hint"] = ("%d개 중 %d개만 보입니다. 검색어를 더 구체적으로 주세요."
                          % (total, len(results)))
    return result


MAX_TABLE_CHARS = 6000


def table_content(title: str, year: str | None = None) -> dict:
    try:
        y = kb.year_of(year)
    except kb.UnknownYear as exc:
        return _year_error(exc)
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

    body = kb.read_table(info["경로"])
    out = {"found": True, "year": y, "title": entry["제목"], "number": info["번호"],
           "content": body[:MAX_TABLE_CHARS]}
    if len(body) > MAX_TABLE_CHARS:
        out["truncated"] = True
    return out


MAX_BODY_HITS = 8


def body_search(query: str, year: str | None = None) -> dict:
    try:
        y = kb.year_of(year)
    except kb.UnknownYear as exc:
        return _year_error(exc)
    q = str(query or "").strip()
    if not q:
        raise ValueError("query가 비었습니다")

    picked, total = kb.body_hits(y, q, MAX_BODY_HITS)
    hits = [{"section": h["section"], "text": h["text"][:400]} for h in picked]
    out = {"found": bool(hits), "year": y, "query": q, "hits": hits, "total": total}
    if total > len(hits):
        out["truncated"] = True
    return out


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
        "description": "부재·지표·실측값으로 등급을 판정한다. 판정규칙표를 코드가 직접 대조해 등급·근거 원문·출처(표번호,면)를 돌려준다. 등급은 반드시 이 도구로만 구한다. 이름이 여러 부재에 걸리면 등급 대신 candidates를 돌려주므로, 그때는 임의로 고르지 말고 사용자에게 되묻는다. 맞는 구간이 없으면 후보 조건들을 돌려준다.",
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
        "description": "표 하나의 실제 내용(등급별 기준 원문)을 돌려준다. table_lookup으로 제목을 확인한 뒤 그 제목으로 호출한다. 길면 잘라서 돌려주고 truncated를 표시한다.",
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
