"""anchor 모듈 - 연도별 표 번호 밀림을 실제로 흡수하는지 검증한다.

정본 데이터가 있어야 돌아간다. 없으면 건너뛴다.
"""
from __future__ import annotations

import pytest

from bridgekb import anchor, config

pytestmark = pytest.mark.skipif(
    not config.DATA_DIR.exists(), reason="정본 데이터 없음")


def test_표번호가_연도마다_다르면_경고한다():
    """표1.31은 2024년엔 케이블교량, 2026년엔 일반교량 가중치다."""
    result = anchor.by_number("1.31")

    assert result["status"] == "ok"
    assert "경고" in result, "같은 번호가 다른 표를 가리키는데 경고가 없다"
    assert "케이블교량" in result["연도별"]["2024"]["제목"]
    assert "일반교량" in result["연도별"]["2026"]["제목"]


def test_같은_표는_경고하지_않는다():
    """표1.11은 네 판본 모두 콘크리트 바닥판 상태평가기준이다."""
    result = anchor.by_number("1.11")

    assert result["status"] == "ok"
    assert "경고" not in result
    assert all("콘크리트 바닥판" in v["제목"] for v in result["연도별"].values())


def test_제목으로_찾으면_연도별_번호를_돌려준다():
    """일반교량 가중치는 2024년까지 표1.30, 2026년에 표1.31로 밀렸다."""
    result = anchor.by_title("일반교량의 부재별 가중치")

    assert result["status"] == "ok"
    assert result["결과수"] == 1

    years = result["결과"][0]["연도별"]
    assert years["2024"]["번호"] == "표1.30"
    assert years["2026"]["번호"] == "표1.31"
    assert "경고" in result["결과"][0]


def test_표기가_흔들려도_찾는다():
    """공백·콜론 차이는 조회를 막지 않아야 한다."""
    with_space = anchor.by_title("일반교량의 부재별 가중치")
    without_space = anchor.by_title("일반교량의부재별가중치")

    assert with_space["결과수"] == without_space["결과수"] == 1


def test_없는_표는_not_found():
    result = anchor.by_number("9.99")
    assert result["status"] == "not_found"


def test_번호와_제목을_자동으로_구분한다():
    assert anchor.lookup("표1.11")["질의"] == "표1.11"
    assert anchor.lookup("콘크리트 바닥판")["질의"] == "콘크리트 바닥판"
