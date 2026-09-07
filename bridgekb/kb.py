"""지식베이스 적재 계층 - 판정규칙·본문을 읽고 이름을 맞춰준다.

`anchor.py`가 표를 맡고, 여기가 나머지(판정규칙 jsonl, 본문 문단)를 맡는다.
도구 계층(`tools.py`)은 이 두 모듈 위에서만 돌아간다 - 파일 경로를 직접
알지 못한다.

부재명·지표명 매칭 규칙과 구간 판정(`satisfies`)은 웹앱
(`webapp/템플릿.html`)의 JS 구현과 **같은 규칙**이어야 한다. 같은 질문에
환경마다 다른 답이 나오면 이 프로젝트의 존재 이유가 없어진다.
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


def year_of(value: str | None) -> str:
    """연도를 정규화한다. 모르는 값이면 최신 판본으로 떨어진다."""
    years = available_years()
    y = str(value or "").strip()
    if y in years:
        return y
    return years[-1] if years else config.DEFAULT_YEAR


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


def _match_name(candidates: list[str], query: str) -> str | None:
    """정확히 같은 이름을 먼저, 없으면 서로 부분 포함하는 이름을 고른다."""
    target = squash(query)
    if not target:
        return None
    for name in candidates:
        if squash(name) == target:
            return name
    for name in candidates:
        s = squash(name)
        if target in s or s in target:
            return name
    return None


def members(year: str) -> list[str]:
    """수치 판정이 가능한 부재 목록."""
    return sorted({r["부재"] for r in numeric_rules(year) if r.get("부재")})


def indicators(year: str, member: str) -> list[str]:
    """그 부재에서 쓸 수 있는 지표 목록."""
    return sorted({r["지표"] for r in numeric_rules(year) if r.get("부재") == member})


def find_member(year: str, query: str) -> str | None:
    return _match_name(members(year), query)


def find_indicator(year: str, member: str, query: str) -> str | None:
    return _match_name(indicators(year, member), query)


def find_any_member(year: str, query: str) -> str | None:
    """정성 기준까지 포함한 전체 부재에서 찾는다(수치 규칙이 없는 부재도 있다)."""
    names = sorted({r["부재"] for r in rules(year) if r.get("부재")})
    return _match_name(names, query)


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


def read_table(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")
