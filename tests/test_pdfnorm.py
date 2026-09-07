"""pdfnorm - 연도마다 다른 PDF 레이아웃을 같은 좌표계로 맞추는 계층.

검증된 사실 (build/probe_fonts.py 및 직접 확인):

  2026: A4 세로 595x841, 78면, 1-up.   글꼴 절3=15.0 목=13.0 본문=11.0
  2023: A3 가로 841x595, 34면, 2-up.   글꼴이 2026의 1/sqrt(2) 배
  2024: A3 가로 841x595, 35면, 2-up.   같음
  2022: PDF 없음 (HWP만)

  인쇄 면번호는 모든 연도에서 "1-N" 형식이며 연도 무관 안정 좌표다.
    2024 물리2면 좌="1-1" 우="1-2"    (2-up)
    2026 물리3면    ="1-1"            (1-up)
"""
from __future__ import annotations

import pytest

from bridgekb import pdfnorm

pytestmark = pytest.mark.skipif(
    not pdfnorm.pdf_path("2026").exists(), reason="원본 PDF 없음")


# ---------------------------------------------------------------- 레이아웃 탐지

def test_2026은_1up으로_판별한다():
    layout = pdfnorm.detect_layout("2026")
    assert layout.up == 1
    assert layout.scale == pytest.approx(1.0, abs=0.02)


@pytest.mark.parametrize("year", ["2023", "2024"])
def test_A3가로판본은_2up으로_판별한다(year):
    layout = pdfnorm.detect_layout(year)
    assert layout.up == 2
    # 글꼴이 2026의 1/sqrt(2)이므로 되돌리려면 sqrt(2)를 곱해야 한다
    assert layout.scale == pytest.approx(2 ** 0.5, abs=0.03)


# ---------------------------------------------------------------- 논리 페이지 분할

def test_2up은_물리면당_논리면_2개로_쪼갠다():
    pages = pdfnorm.logical_pages("2024", limit_physical=3)
    # 물리 3면 -> 논리 6면
    assert len(pages) == 6
    assert [p.physical for p in pages] == [1, 1, 2, 2, 3, 3]
    assert [p.side for p in pages] == ["L", "R"] * 3


def test_1up은_쪼개지_않는다():
    pages = pdfnorm.logical_pages("2026", limit_physical=3)
    assert len(pages) == 3
    assert all(p.side is None for p in pages)


# ---------------------------------------------------------------- 인쇄 면번호

def test_2up의_인쇄면번호를_좌우로_읽는다():
    pages = pdfnorm.logical_pages("2024", limit_physical=2)
    # 물리 1면은 표지라 번호가 없고, 물리 2면부터 1-1 / 1-2
    printed = [p.printed for p in pages]
    assert printed[2:4] == ["1-1", "1-2"]


def test_1up의_인쇄면번호를_읽는다():
    pages = pdfnorm.logical_pages("2026", limit_physical=4)
    assert pages[2].printed == "1-1"
    assert pages[3].printed == "1-2"


def test_같은_내용은_연도가_달라도_같은_인쇄면번호를_갖는다():
    """표1.11 콘크리트 바닥판 상태평가기준은 2024/2026 모두 인쇄 1-27면에서 시작한다.

    물리 면수로는 15 vs 29로 어긋나지만 인쇄 면번호로는 일치한다.
    이것이 인용에 인쇄 면번호를 써야 하는 이유다.
    """
    p2024 = pdfnorm.find_caption("2024", "표 1.11")
    p2026 = pdfnorm.find_caption("2026", "표 1.11")

    assert p2024 is not None and p2026 is not None
    assert p2024.printed == p2026.printed == "1-27"
    # 물리 면수는 서로 다르다 - 이게 기존 데이터가 어긋난 원인
    assert p2024.physical != p2026.physical


# ---------------------------------------------------------------- 글꼴 정규화

def test_글꼴크기를_2026기준으로_정규화한다():
    """2024의 9.2(목)와 7.8(본문)이 정규화 후 13.0 / 11.0 근처가 돼야 한다."""
    pages = pdfnorm.logical_pages("2024", limit_physical=6)
    sizes = {round(line.size) for p in pages for line in p.lines}

    assert 13 in sizes, "목(가.나.다) 계층이 13.0으로 정규화되지 않았다"
    assert 11 in sizes, "본문 계층이 11.0으로 정규화되지 않았다"


def test_정규화후_2026매핑이_모든_연도에_적용된다():
    """DB/스크립트/공통.py의 크기계층을 그대로 쓸 수 있어야 한다."""
    for year in ("2024", "2026"):
        pages = pdfnorm.logical_pages(year, limit_physical=8)
        roles = {pdfnorm.SIZE_TO_LEVEL.get(round(line.size))
                 for p in pages for line in p.lines}
        assert "목" in roles, "%s: 목 계층을 못 찾음" % year
        assert "본문" in roles, "%s: 본문 계층을 못 찾음" % year


# ---------------------------------------------------------------- 읽기 순서

def test_2up의_좌측이_우측보다_먼저_온다():
    pages = pdfnorm.logical_pages("2024", limit_physical=4)
    printed = [p.printed for p in pages if p.printed]
    numbers = [int(s.split("-")[1]) for s in printed]
    assert numbers == sorted(numbers), "인쇄 면번호가 오름차순이 아니다"
