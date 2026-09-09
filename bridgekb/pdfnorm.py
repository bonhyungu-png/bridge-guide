"""연도마다 다른 PDF 레이아웃을 하나의 좌표계로 맞춘다.

같은 지침서인데 판본마다 인쇄 형태가 다르다.

    2026: A4 세로 595x841, 78면, 한 장에 한 쪽(1-up)
    2023: A3 가로 841x595, 34면, 한 장에 두 쪽(2-up)
    2024: A3 가로 841x595, 35면, 2-up
    2022: PDF 없음 (HWP만 있어 변환이 선행돼야 한다)

이 차이가 두 가지 문제를 만든다.

1. **글꼴 크기가 다르다.** 2-up 판본은 내용을 1/sqrt(2)로 줄여 실었다.
   DB/스크립트/공통.py는 계층을 글꼴 크기로 판별하는데(절3=15.0 목=13.0 본문=11.0)
   그 값이 2026 전용이라 다른 연도에 그대로 쓸 수 없다.

2. **면수가 어긋난다.** 2-up의 물리 시트 번호는 실제 지침서 면수의 절반이다.
   실제로 [표 1.11]은 2024년 물리 15면, 2026년 물리 29면에 있는데 같은 내용이다.
   점검자가 종이에서 찾는 번호는 하단에 인쇄된 "1-27"이고, 이것만이 연도 무관이다.

그래서 이 모듈은 물리 페이지를 논리 페이지로 쪼개고, 글꼴을 2026 기준으로
되돌리고, 인쇄 면번호를 읽어 붙인다. 그러면 위 파이프라인을 모든 연도에 쓸 수 있다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pdfplumber

from . import config

# 원본 PDF는 저장소 안에 번들돼 있다(data/원본pdf/{연도}.pdf).
# 예전에는 저장소 **바깥**의 옛 작업 폴더를 가리키고 있어서, 새로 클론한
# 컴퓨터에서는 available_years()가 빈 목록이었고 pdfnorm 테스트 17개가
# 조용히 skip 됐다 - 초록불인데 실제로는 안 돌던 상태였다.
PDF_DIR = config.DATA_ROOT / "원본pdf"

# 기준 판본(2026)의 A4 세로 폭. 다른 판본의 배율은 이 값 대비로 계산한다.
A4_WIDTH = 595.0

# DB/스크립트/공통.py의 크기계층. 정규화 후에는 모든 연도에 이 매핑이 적용된다.
SIZE_TO_LEVEL = {20: "절2", 15: "절3", 13: "목", 11: "본문"}

# 하단에 인쇄된 면번호. "1-27" 형태로 장-면을 함께 담는다.
PRINTED_NO = re.compile(r"^\s*(\d+-\d+)\s*$")

# 표·그림의 **캡션**. 줄 맨 앞에 와야 한다 - DB/스크립트/공통.py의 캡션패턴과 같다.
# 본문 한가운데의 "[표 1.11]"은 캡션이 아니라 상호참조이므로 잡으면 안 된다
# (예: 1.1.4 중대한 결함 조항이 [표 1.11]을 참조한다).
CAPTION = re.compile(r"^\[\s*(표|그림)\s*([\d.]+(?:의\d+)?)\s*\]")

# 본문 속 상호참조. 캡션과 구분해서 다룬다.
CROSSREF = re.compile(r"\[\s*(표|그림)\s*([\d.]+(?:의\d+)?)\s*\]")

# 2-up 판별용. 가운데 이 비율만큼의 띠가 비어 있으면 두 쪽으로 본다.
_GUTTER_BAND = (0.45, 0.55)


def pdf_path(year: str) -> Path:
    """해당 연도의 원본 PDF."""
    return PDF_DIR / ("%s.pdf" % year)


def available_years() -> list:
    """PDF가 실제로 있는 연도 목록."""
    if not PDF_DIR.is_dir():
        return []
    return sorted(p.stem for p in PDF_DIR.glob("*.pdf") if p.stem.isdigit())


@dataclass(frozen=True)
class Layout:
    """판본의 인쇄 형태."""
    year: str
    up: int             # 물리 한 장에 실린 논리 쪽 수 (1 또는 2)
    scale: float        # 글꼴을 2026 기준으로 되돌리는 배율
    width: float
    height: float

    @property
    def logical_width(self) -> float:
        return self.width / self.up


@dataclass
class Line:
    """한 줄. size는 2026 기준으로 정규화된 값이다."""
    top: float
    size: float
    text: str
    x0: float


@dataclass
class LogicalPage:
    """논리 페이지 하나. 2-up이면 물리 한 장에서 둘이 나온다."""
    year: str
    physical: int              # 물리 PDF 면수 (1부터)
    side: str | None           # 2-up일 때 "L" 또는 "R", 1-up이면 None
    printed: str | None        # 하단에 인쇄된 면번호 ("1-27"). 인용에 쓸 값
    lines: list = field(default_factory=list)

    @property
    def label(self) -> str:
        """사람에게 보여줄 좌표."""
        if self.printed:
            return self.printed
        return "물리%d면%s" % (self.physical, self.side or "")


def _has_empty_gutter(page) -> bool:
    """가운데 세로 띠가 비어 있으면 2-up이다."""
    w = page.width
    lo, hi = w * _GUTTER_BAND[0], w * _GUTTER_BAND[1]
    return not any(lo <= c["x0"] <= hi for c in page.chars)


@lru_cache(maxsize=8)
def detect_layout(year: str) -> Layout:
    """판본의 인쇄 형태를 자동 판별한다. 크기를 하드코딩하지 않는다."""
    path = pdf_path(year)
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[min(8, len(pdf.pages) - 1)]
        w, h = page.width, page.height
        # 가로가 세로보다 길고 가운데가 비어 있으면 두 쪽을 나란히 실은 것이다.
        landscape = w > h * 1.15
        up = 2 if (landscape and _has_empty_gutter(page)) else 1

    return Layout(year=year, up=up, scale=A4_WIDTH / (w / up), width=w, height=h)


def _group_lines(page, layout: Layout, x0: float, x1: float) -> list:
    """지정한 x 구간의 문자를 줄로 묶는다. 크기는 2026 기준으로 되돌린다.

    묶는 방식은 DB/스크립트/공통.py의 줄묶기와 같다 - y좌표와 글꼴 크기로 버킷을
    만들고, 문자 간격이 넓으면 공백을 넣어 단어를 살린다.
    """
    tol = 1.0 / layout.scale     # 축소된 판본은 허용오차도 같이 줄인다
    buckets: dict = {}
    for c in page.chars:
        if not (x0 <= c["x0"] < x1):
            continue
        key = (round(c["top"] / tol) * tol, round(c["size"], 1))
        buckets.setdefault(key, []).append(c)

    lines = []
    for key in sorted(buckets):
        chars = sorted(buckets[key], key=lambda x: x["x0"])
        parts, prev = [], None
        for c in chars:
            if prev is not None and c["x0"] - prev["x1"] > prev["size"] * 0.28:
                parts.append(" ")
            parts.append(c["text"])
            prev = c
        text = "".join(parts).strip()
        if text:
            lines.append(Line(
                top=key[0],
                size=round(key[1] * layout.scale, 1),   # 2026 기준으로 정규화
                text=text,
                x0=chars[0]["x0"] - x0,                 # 논리 페이지 원점으로 보정
            ))
    return lines


def read_printed_no(page, x0: float, x1: float) -> str | None:
    """하단에 인쇄된 면번호를 읽는다.

    01_문서골격/02_표추출처럼 원본 pdfplumber 페이지를 직접 다루는 다른
    스크립트도 같은 규칙으로 인쇄 면번호를 읽어야 하므로 공개 함수로 둔다.
    """
    h = page.height
    try:
        band = page.crop((x0, h * 0.93, x1, h))
        text = band.extract_text() or ""
    except Exception:
        return None
    for raw in reversed(text.splitlines()):
        m = PRINTED_NO.match(raw.strip())
        if m:
            return m.group(1)
    return None


# 하위 호환 별칭 - logical_pages 안에서 계속 쓰인다
_read_printed_no = read_printed_no


def page_blocks(layout: Layout, page_width: float) -> list:
    """물리 페이지 한 장을 논리 쪽 구간으로 나눈다.

    1-up이면 [(None, 0, width)] 하나, 2-up이면 좌/우 두 구간.
    01_문서골격/02_표추출이 원본 페이지를 직접 크롭할 때 이 경계를 그대로 쓴다.
    """
    if layout.up == 1:
        return [(None, 0.0, page_width)]
    half = page_width / 2
    return [("L", 0.0, half), ("R", half, page_width)]


def logical_pages(year: str, limit_physical: int | None = None) -> list:
    """물리 페이지를 논리 페이지로 펼쳐 읽기 순서대로 돌려준다.

    limit_physical: 앞에서부터 이만큼의 물리 면만 읽는다(테스트·탐색용).
    """
    layout = detect_layout(year)
    out: list = []

    with pdfplumber.open(pdf_path(year)) as pdf:
        pages = pdf.pages[:limit_physical] if limit_physical else pdf.pages
        for physical, page in enumerate(pages, 1):
            for side, x0, x1 in page_blocks(layout, page.width):
                out.append(LogicalPage(
                    year=year,
                    physical=physical,
                    side=side,
                    printed=_read_printed_no(page, x0, x1),
                    lines=_group_lines(page, layout, x0, x1),
                ))
    return out


def _caption_number(text: str) -> str | None:
    """'표 1.11' / '[표 1.11]' / '표1.11' 에서 번호만 뽑는다."""
    m = re.search(r"([\d.]+(?:의\d+)?)", text)
    return m.group(1).rstrip(".") if m else None


def find_caption(year: str, caption: str, limit_physical: int | None = None):
    """표·그림의 캡션이 실제로 붙어 있는 논리 페이지를 찾는다.

    본문 속 상호참조는 건너뛴다. 캡션은 줄 맨 앞에 오기 때문에 구분할 수 있다.
    """
    target = _caption_number(caption)
    if target is None:
        return None

    for page in logical_pages(year, limit_physical):
        for line in page.lines:
            m = CAPTION.match(line.text)
            if m and m.group(2).rstrip(".") == target:
                return page
    return None


def summary(year: str) -> dict:
    """판본의 레이아웃 요약. doctor 등에서 쓴다."""
    path = pdf_path(year)
    if not path.exists():
        return {"연도": year, "상태": "PDF 없음",
                "안내": "HWP만 있는 판본은 변환이 선행돼야 합니다."}
    layout = detect_layout(year)
    with pdfplumber.open(path) as pdf:
        physical = len(pdf.pages)
    return {
        "연도": year,
        "상태": "ok",
        "용지": "%.0f x %.0f" % (layout.width, layout.height),
        "배치": "%d-up" % layout.up,
        "물리면": physical,
        "논리면": physical * layout.up,
        "글꼴배율": round(layout.scale, 4),
    }
