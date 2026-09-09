"""지식베이스 적재 계층 - 판정규칙·본문을 읽고 이름을 맞춰준다.

`anchor.py`가 표를 맡고, 여기가 나머지(판정규칙 jsonl, 본문 문단)를 맡는다.
도구 계층(`tools.py`)은 이 두 모듈 위에서만 돌아간다 - 파일 경로를 직접
알지 못한다.

구간 판정(`satisfies`)은 이 프로젝트에서 수치를 비교하는 **유일한 자리**다.
예전에는 같은 규칙이 웹앱 JS에도 복사돼 있었는데, 사본이 생기면 언젠가
갈라진다 - 실제로 표 검색 정렬이 어긋나 창마다 다른 표가 나왔다. 지금은
구현이 하나뿐이고, 답하는 곳도 웹 하나뿐이다.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from . import config

_SQUASH = re.compile(r"[\s:：·・]+")


def squash(text: str | None) -> str:
    """공백·콜론·가운뎃점을 지운 비교용 형태. 표기 흔들림을 흡수한다."""
    return _SQUASH.sub("", text or "")


class UnknownYear(ValueError):
    """없는 판본을 물었다. 조용히 다른 연도로 바꿔치기하지 않는다."""

    def __init__(self, asked: str):
        self.asked = asked
        self.available = list(available_years())
        super().__init__("%s년판은 없습니다. 있는 판본: %s"
                         % (asked, ", ".join(self.available)))


def default_year() -> str:
    years = available_years()
    return years[-1] if years else config.DEFAULT_YEAR


def year_of(value: str | None) -> str:
    """연도를 확정한다.

    비어 있으면 최신 판본을 쓴다. 그러나 **모르는 연도를 조용히 최신판으로
    바꾸지는 않는다** - 이 도구의 존재 이유가 연도별로 기준이 다르다는 것인데,
    2021년을 물었는데 아무 말 없이 2026년 기준으로 답하면 그 자체가 오답이다.
    """
    y = str(value or "").strip()
    if not y:
        return default_year()
    if y in available_years():
        return y
    raise UnknownYear(y)


@lru_cache(maxsize=1)
def available_years() -> tuple[str, ...]:
    return tuple(config.available_years())


# ---------------- 판정규칙 ----------------

@lru_cache(maxsize=8)
def rules(year: str) -> tuple[dict, ...]:
    """해당 판본의 판정규칙 전체. 출처는 표/면으로 평탄화해 둔다."""
    path = config.rules_path_for(year)
    if not path.exists():
        return ()
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        출처 = r.get("출처") or {}
        r["표"] = 출처.get("표")
        r["면"] = 출처.get("면")
        out.append(r)
    return tuple(out)


def numeric_rules(year: str) -> list[dict]:
    """수치 판정이 가능한 규칙만. 지표명이 없는 것은 대조할 수 없으므로 뺀다."""
    return [r for r in rules(year) if r.get("연산") != "정성" and r.get("지표")]


def satisfies(rule: dict, value: float) -> bool:
    """실측값이 이 규칙의 구간을 만족하는가. 등급 판정의 유일한 계산 지점이다."""
    op = rule.get("연산")
    if op == "구간":
        lo = rule.get("최소")
        hi = rule.get("최대")
        if lo is None or hi is None:
            return False
        low_ok = value >= lo if rule.get("최소포함") else value > lo
        high_ok = value <= hi if rule.get("최대포함") else value < hi
        return low_ok and high_ok
    v = rule.get("값")
    if v is None:
        return False
    if op == "미만":
        return value < v
    if op == "이하":
        return value <= v
    if op == "초과":
        return value > v
    if op == "이상":
        return value >= v
    return False


class Match:
    """이름 조회 결과.

    지침서 원문은 같은 것을 여러 표기로 적어 둔 곳이 있고(띄어쓰기 차이),
    반대로 사용자가 짧게 말하면 서로 다른 부재 여럿에 걸린다. 둘을 구분하지
    않고 "하나만 골라" 돌려주면 조용히 틀린 답이 나온다 - 그래서 조회 결과를
    이 객체로 감싸 **몇 개가 걸렸는지**를 호출부가 반드시 보게 한다.

      names   : 걸린 이름 전부
      exact   : 표기만 다른 같은 이름인가(True) / 서로 다른 후보인가(False)
      ambiguous : 서로 다른 후보가 둘 이상 걸렸는가
    """

    __slots__ = ("names", "exact")

    def __init__(self, names: list[str], exact: bool):
        self.names = names
        self.exact = exact

    def __bool__(self) -> bool:
        return bool(self.names)

    @property
    def ambiguous(self) -> bool:
        return not self.exact and len(self.names) > 1

    @property
    def one(self) -> str | None:
        """확정된 이름 하나. 모호하면 None."""
        if not self.names or self.ambiguous:
            return None
        return self.names[0]


_NO_MATCH = Match([], False)


def _drop_nested(names: list[str]) -> list[str]:
    """다른 후보에 통째로 포함되는 짧은 후보를 뺀다.

    "프리스트레스 콘크리트 바닥판 균열폭"으로 물으면 '콘크리트 바닥판'과
    '프리스트레스 콘크리트 바닥판'이 함께 걸린다. 앞의 것은 뒤의 것 안에
    들어 있으므로 덜 구체적이다 - 이럴 때까지 모호하다고 되물으면 쓸 수 없다.
    반대로 '시멘트 콘크리트 교면포장'과 '아스팔트 콘크리트 교면포장'은 서로를
    포함하지 않으므로 둘 다 남고, 그때는 진짜로 모호한 것이다.
    """
    kept = []
    for name in names:
        s = squash(name)
        if any(s != squash(other) and s in squash(other) for other in names):
            continue
        kept.append(name)
    return kept or names


def match_name(candidates: list[str], query: str) -> Match:
    """이름을 찾는다. 표기 흔들림은 흡수하고, 진짜 모호함은 그대로 알린다."""
    target = squash(query)
    if not target:
        return _NO_MATCH

    # 1) squash가 정확히 같은 것들 - 표기만 다른 같은 이름이다. 전부 함께 쓴다.
    exact = [n for n in candidates if squash(n) == target]
    if exact:
        return Match(exact, True)

    # 2) 서로 부분 포함하는 것들 - 서로 다른 이름일 수 있으므로 모호함을 알린다.
    partial = [n for n in candidates
               if target in squash(n) or squash(n) in target]
    if not partial:
        return _NO_MATCH
    narrowed = _drop_nested(partial)
    if len(narrowed) == 1:
        # 후보가 하나로 좁혀졌다. 그 이름의 다른 표기까지 함께 모은다.
        s = squash(narrowed[0])
        return Match([n for n in candidates if squash(n) == s], True)
    return Match(narrowed, False)


def _match_name(candidates: list[str], query: str) -> str | None:
    """옛 이름 - 하나만 돌려준다. 모호하면 None."""
    return match_name(candidates, query).one


def members(year: str) -> list[str]:
    """수치 판정이 가능한 부재 목록."""
    return sorted({r["부재"] for r in numeric_rules(year) if r.get("부재")})


def indicators(year: str, member: str) -> list[str]:
    """그 부재에서 쓸 수 있는 지표 목록."""
    return sorted({r["지표"] for r in numeric_rules(year) if r.get("부재") == member})


def all_members(year: str) -> list[str]:
    """정성 기준까지 포함한 전체 부재(수치 규칙이 없는 부재도 있다)."""
    return sorted({r["부재"] for r in rules(year) if r.get("부재")})


def find_member(year: str, query: str) -> Match:
    return match_name(members(year), query)


def find_indicator(year: str, member: str, query: str) -> Match:
    """부재의 지표를 찾는다.

    같은 지표를 '표면 손상면적' / '표면손상면적' 두 표기로 나눠 적어 둔 표가
    있다(PSC 거더). 표기 하나만 골라 규칙을 거르면 나머지 표기로 적힌 등급이
    통째로 조회 불가가 된다 - 실제로 d등급(10%이상)이 그렇게 사라져 있었다.
    그래서 걸린 표기를 **전부** 돌려주고, 판정은 그 전부를 후보로 삼는다.
    """
    return match_name(indicators(year, member), query)


def find_any_member(year: str, query: str) -> Match:
    return match_name(all_members(year), query)


# ---------------- 본문 ----------------

@lru_cache(maxsize=8)
def body_sections(year: str) -> tuple[dict, ...]:
    """절2 단위 본문. {"절": 파일이름, "내용": 원문} 목록."""
    folder = config.BODY_DIR / f"{config.판본_접두}@{year}"
    if not folder.is_dir():
        return ()
    return tuple({"절": p.stem, "내용": p.read_text(encoding="utf-8")}
                 for p in sorted(folder.glob("*.md")))


_HEADING = re.compile(r"^#{2,5} ")


def body_lines(year: str):
    """본문에서 검색 대상이 되는 줄만 (절이름, 텍스트)로 흘려보낸다.

    `내용: ` 로 시작하는 문단과 소제목만 본다. 머리말(문서·판본·절)이나
    `표참조:` 줄은 검색어가 걸려도 답의 근거가 되지 못하므로 뺀다.
    """
    for sec in body_sections(year):
        for line in sec["내용"].split("\n"):
            if line.startswith("내용: "):
                yield sec["절"], line[4:]
            elif _HEADING.match(line):
                yield sec["절"], _HEADING.sub("", line)


def body_hits(year: str, query: str, limit: int = 8) -> tuple[list, int]:
    """본문에서 검색어가 든 줄을 절 고루 섞어 돌려준다. (뽑은 것, 전체 건수)

    앞에서부터 limit개를 채우고 멈추면 절 이름 정렬 순서상 앞선 절이 자리를 다
    차지한다 - "균열"을 찾으면 56건 중 42건이 1.4 상태평가기준에 있는데도
    1.1 관리일반에서만 8건이 나와 정작 필요한 절을 한 줄도 못 봤다.
    그래서 전부 모은 뒤 절을 돌아가며 한 줄씩 뽑는다.
    """
    by_section: dict = {}
    total = 0
    for section, text in body_lines(year):
        if query in text:
            total += 1
            by_section.setdefault(section, []).append(text)

    picked: list = []
    sections = list(by_section)
    while len(picked) < limit and any(by_section[s] for s in sections):
        for s in sections:
            if not by_section[s]:
                continue
            picked.append({"section": s, "text": by_section[s].pop(0)})
            if len(picked) >= limit:
                break
    return picked, total


def read_table(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")
