"""표 조회 - 연도마다 밀리는 표 번호를 흡수한다.

표 번호는 판본이 바뀌면 밀린다. 2026년판에 [표 1.30 월류]가 새로 끼어들면서
그 뒤가 전부 한 칸씩 밀렸다: 일반교량 가중치가 2024년 표1.30에서 2026년 표1.31이 됐다.
그래서 "표1.31"이라는 질문에는 연도를 함께 확인하지 않으면 답할 수 없다.

표 제목은 연도가 바뀌어도 안정적이므로, 제목을 연도 무관 식별자(앵커)로 쓴다.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from . import config

# "표1.31 구조형식에 따른 ..." / "표1.11의2 콘크리트 ..." / "표_교면포장-1"
NUMBERED = re.compile(r"^표(?P<no>\d+\.\d+(?:의\d+)?)\s+(?P<title>.+)$")
UNNUMBERED = re.compile(r"^표_(?P<title>.+)$")


def _squash(text: str) -> str:
    """공백·콜론을 지운 비교용 형태. 표기 흔들림을 흡수한다."""
    return re.sub(r"[\s:：·・]+", "", text)


def _scan() -> dict:
    """정본의 표 파일을 전부 훑어 앵커 색인을 만든다.

    표 파일은 data/파생/본문표/{판본_접두}@{연도}/*.md에 판본별로 모여 있다
    (섹션별로 나뉘어 있지 않다 - 한 판본 안에서는 표 번호가 유일하므로 안전하다).

    반환: {앵커키: {"제목": str, "연도별": {연도: {"번호": str|None, "경로": Path}}}}
    """
    index: dict[str, dict] = defaultdict(lambda: {"제목": "", "연도별": {}})
    접두 = config.판본_접두 + "@"

    for 판본폴더 in sorted(config.TABLE_DIR.glob(f"{config.판본_접두}@*")):
        if not 판본폴더.is_dir() or not 판본폴더.name.startswith(접두):
            continue
        year = 판본폴더.name[len(접두):]
        for table_file in sorted(판본폴더.glob("*.md")):
            _index_table(index, table_file, year)

    return dict(index)


def _index_table(index: dict, table_file: Path, year: str) -> None:
    stem = table_file.stem

    m = NUMBERED.match(stem)
    if m:
        title, number = m.group("title").strip(), m.group("no")
    else:
        m = UNNUMBERED.match(stem)
        if not m:
            return
        title, number = m.group("title").strip(), None

    key = _squash(title)
    entry = index[key]
    entry["제목"] = entry["제목"] or title
    entry["연도별"][year] = {"번호": number, "경로": table_file}


_INDEX: dict | None = None


def index() -> dict:
    global _INDEX
    if _INDEX is None:
        _INDEX = _scan()
    return _INDEX


def by_number(number: str, year: str | None = None) -> dict:
    """표 번호로 조회한다. 연도마다 다른 표를 가리키면 경고를 붙인다.

    number: "1.31" 또는 "표1.31" 형태 모두 허용.
    """
    num = number.strip().lstrip("표").strip()

    # 이 번호를 쓰는 (연도, 앵커) 쌍을 모두 모은다.
    hits: dict[str, dict] = {}
    for key, entry in index().items():
        for y, info in entry["연도별"].items():
            if info["번호"] == num:
                hits.setdefault(y, {"앵커": key, "제목": entry["제목"], "경로": str(info["경로"])})

    if not hits:
        return {"status": "not_found", "질의": "표" + num,
                "안내": "해당 번호의 표를 찾지 못했습니다. 제목으로 검색해 보세요."}

    titles = {v["제목"] for v in hits.values()}
    result = {
        "status": "ok",
        "질의": "표" + num,
        "연도별": dict(sorted(hits.items())),
    }
    if len(titles) > 1:
        result["경고"] = (
            "같은 번호가 연도마다 다른 표를 가리킵니다. "
            + " / ".join("%s=%s" % (y, v["제목"]) for y, v in sorted(hits.items()))
        )
    if year:
        result["요청연도"] = year
        result["해당"] = hits.get(year)
        if year not in hits:
            result["경고_연도"] = "%s년판에는 표%s이 없습니다." % (year, num)
    return result


def by_title(query: str) -> dict:
    """표 제목(일부)으로 조회한다. 연도별 번호를 나란히 돌려준다."""
    target = _squash(query)
    matches = [(k, v) for k, v in index().items() if target in k]

    if not matches:
        return {"status": "not_found", "질의": query}

    out = []
    for key, entry in sorted(matches, key=lambda kv: kv[1]["제목"]):
        years = {y: {"번호": ("표" + i["번호"]) if i["번호"] else "(번호없음)",
                     "경로": str(i["경로"])}
                 for y, i in sorted(entry["연도별"].items())}
        numbers = {i["번호"] for i in entry["연도별"].values() if i["번호"]}
        item = {"앵커": key, "제목": entry["제목"], "연도별": years}
        if len(numbers) > 1:
            item["경고"] = "연도에 따라 표 번호가 다릅니다 (" + ", ".join(
                "%s=표%s" % (y, i["번호"]) for y, i in sorted(entry["연도별"].items()) if i["번호"]
            ) + ")"
        out.append(item)

    return {"status": "ok", "질의": query, "결과수": len(out), "결과": out}


def lookup(query: str, year: str | None = None) -> dict:
    """번호처럼 보이면 번호로, 아니면 제목으로 조회한다."""
    stripped = query.strip().lstrip("표").strip()
    if re.fullmatch(r"\d+\.\d+(?:의\d+)?", stripped):
        return by_number(stripped, year)
    return by_title(query)


def read_table(path: str | Path) -> str:
    """표 원문을 그대로 읽는다."""
    return Path(path).read_text(encoding="utf-8")
