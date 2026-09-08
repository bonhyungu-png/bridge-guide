"""pdfnorm - 판본마다 다른 PDF 인쇄 형태를 같은 좌표계로 맞추는 계층.

현재 원본(data/원본pdf/*.pdf)의 실측:

  2022: A4 세로 595x842, 68면, 1-up
  2023: A4 세로 595x842, 68면, 1-up
  2024: A4 세로 595x842, 69면, 1-up
  2026: A4 세로 595x841, 78면, 1-up

예전에는 2023/2024가 A3 가로 2-up이었고 이 모듈은 그것을 좌우로 쪼개는 게
주 임무였다. 지금은 네 판본 모두 보기 편하도록 1-up으로 다시 변환돼 있어
쪼갤 것이 없다. 2-up 처리 코드는 남겨 두되(다시 2-up 판본을 받을 수 있다),
테스트는 지금 파일의 사실만 검증한다.

또 하나 바뀐 사실: 캡션("[표 1.11] ...")은 지금 파일에서 텍스트로 추출되지
않는다(그림처럼 렌더링된 것으로 보인다). 그래서 표의 위치는 캡션이 아니라
표 본문의 낱말로 찾는다 - build/16_출처페이지매핑.py 가 그 일을 한다.
"""
from __future__ import annotations

import pytest

from bridgekb import pdfnorm

pytestmark = pytest.mark.skipif(
    not pdfnorm.pdf_path("2026").exists(), reason="원본 PDF 없음")

YEARS = ["2022", "2023", "2024", "2026"]


# ---------------------------------------------------------------- 레이아웃 탐지

@pytest.mark.parametrize("year", YEARS)
def test_네_판본_모두_1up_A4로_판별한다(year):
    layout = pdfnorm.detect_layout(year)
    assert layout.up == 1
    assert layout.scale == pytest.approx(1.0, abs=0.02)
    assert layout.height > layout.width, "세로 판형이어야 한다"


# ---------------------------------------------------------------- 논리 페이지

@pytest.mark.parametrize("year", YEARS)
def test_1up은_물리면과_논리면이_1대1이다(year):
    pages = pdfnorm.logical_pages(year, limit_physical=3)
    assert len(pages) == 3
    assert [p.physical for p in pages] == [1, 2, 3]
    assert all(p.side is None for p in pages)


# ---------------------------------------------------------------- 인쇄 면번호

def test_인쇄면번호를_읽는다():
    """하단에 인쇄된 "1-N"은 종이 지침서에서 찾을 때 쓰는 번호다."""
    pages = pdfnorm.logical_pages("2026", limit_physical=4)
    assert pages[2].printed == "1-1"
    assert pages[3].printed == "1-2"


def test_2026은_표1_11쪽에서_인쇄면_1_27을_읽는다():
    pages = pdfnorm.logical_pages("2026")
    assert pages[28].printed == "1-27"


@pytest.mark.parametrize("year", ["2022", "2023", "2024"])
def test_2026외_판본은_인쇄면번호가_글자로_안_읽힌다(year):
    """이 세 판본은 하단 면번호가 그림으로 그려져 있어 추출되지 않는다.

    그래서 표의 위치를 인쇄면으로 찾을 수 없고, 표 본문의 낱말로 물리 쪽을
    찾아 데이터에 박아 두는 방식(build/16_출처페이지매핑.py)을 쓴다.
    이 사실이 바뀌면(면번호가 글자로 들어오면) 이 테스트가 먼저 깨진다.
    """
    pages = pdfnorm.logical_pages(year, limit_physical=32)
    assert not [p for p in pages if p.printed]


# ---------------------------------------------------------------- 텍스트 추출

@pytest.mark.parametrize("year", YEARS)
def test_표_본문_글자는_추출된다(year):
    """캡션은 못 읽어도 표 안의 글자는 읽힌다 - 페이지를 찾는 근거가 된다."""
    pages = pdfnorm.logical_pages(year)
    joined = "".join(line.text for line in pages[28].lines).replace(" ", "")
    assert "데크플레이트" in joined
