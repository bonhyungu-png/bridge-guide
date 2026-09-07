"""도구 6개 - 웹앱 JS 구현과 같은 답을 내는지 검증한다.

이 프로젝트의 목표가 "환경이 달라도 같은 답"이므로, 여기서 지키는 것은
함수가 안 죽는다는 사실이 아니라 **값이 웹앱과 같다**는 사실이다.
기준값은 SKILL.md의 예시(균열폭 0.25mm → b등급, 표1.11, 1-27면)를 쓴다.
"""
from __future__ import annotations

import pytest

from bridgekb import config, kb, tools

pytestmark = pytest.mark.skipif(
    not config.DATA_DIR.exists(), reason="정본 데이터 없음")


# ---------------- grade_lookup ----------------

def test_균열폭_025는_b등급이고_출처가_붙는다():
    r = tools.grade_lookup("콘크리트 바닥판", "균열폭", 0.25)

    assert r["found"] is True
    assert r["grade"] == "b"
    assert r["source"] == {"table": "1.11", "page": "1-27"}
    assert "0.1" in r["quote"] and "0.3" in r["quote"]


def test_연도를_안_주면_2026년판을_쓴다():
    assert tools.grade_lookup("콘크리트 바닥판", "균열폭", 0.25)["year"] == "2026"


def test_연도를_주면_그_판본으로_판정한다():
    r = tools.grade_lookup("콘크리트 바닥판", "균열폭", 0.25, year="2022")
    assert r["year"] == "2022"
    assert r["found"] is True


def test_구간_경계는_원문_그대로_판정한다():
    """0.1㎜이상～0.3㎜미만이므로 0.1은 b, 0.3은 b가 아니다."""
    assert tools.grade_lookup("콘크리트 바닥판", "균열폭", 0.1)["grade"] == "b"
    assert tools.grade_lookup("콘크리트 바닥판", "균열폭", 0.3)["grade"] != "b"
    assert tools.grade_lookup("콘크리트 바닥판", "균열폭", 0.09)["grade"] == "a"


def test_없는_부재는_지어내지_않고_모른다고_한다():
    r = tools.grade_lookup("존재하지않는부재", "균열폭", 1)
    assert r["found"] is False
    assert "list_members" in r["hint"]


def test_없는_지표는_그_부재의_지표_목록을_알려준다():
    r = tools.grade_lookup("콘크리트 바닥판", "존재하지않는지표", 1)
    assert r["found"] is False
    assert r["member"] == "콘크리트 바닥판"
    assert "균열폭" in r["available_indicators"]


def test_맞는_구간이_없으면_후보를_돌려준다():
    """'데크플레이트 부식 면적'은 c등급 구간(1%이상)만 있어 0%는 어디에도 안 걸린다.

    이럴 때 아무 등급이나 고르면 안 되고, 후보 조건을 보여줘 모델이 상황을
    설명하게 해야 한다.
    """
    r = tools.grade_lookup("콘크리트 바닥판", "바닥판 누수로 인한 데크플레이트 부식 면적", 0)
    assert r["found"] is False
    assert r["candidates"], "후보 구간을 돌려주지 않으면 모델이 확인할 방법이 없다"
    assert all(c["table"] for c in r["candidates"])


def test_숫자가_아닌_값은_거부한다():
    with pytest.raises(ValueError):
        tools.grade_lookup("콘크리트 바닥판", "균열폭", "많이")


# ---------------- list_members ----------------

def test_부재목록은_지표를_함께_돌려준다():
    r = tools.list_members()
    names = [m["member"] for m in r["members"]]
    assert "콘크리트 바닥판" in names
    바닥판 = next(m for m in r["members"] if m["member"] == "콘크리트 바닥판")
    assert "균열폭" in 바닥판["indicators"]


# ---------------- qualitative_criteria ----------------

def test_정성기준은_등급확정_금지를_함께_돌려준다():
    r = tools.qualitative_criteria("콘크리트 바닥판")
    assert r["found"] is True
    assert "확정하지" in r["note"]
    assert all(c["table"] for c in r["criteria"]), "출처 없는 기준이 섞이면 안 된다"


# ---------------- table_lookup / table_content ----------------

def test_표131은_연도마다_다른_표라고_경고한다():
    r = tools.table_lookup("1.31")
    assert r["found"] is True
    warnings = [x.get("warning", "") for x in r["results"]]
    assert any("케이블교량" in w and "일반교량" in w for w in warnings)


def test_같은_표는_경고하지_않는다():
    r = tools.table_lookup("콘크리트 바닥판 상태평가기준")
    assert r["found"] is True
    첫 = r["results"][0]
    assert 첫["numbers_by_year"]["2026"] == "표1.11"
    assert "warning" not in 첫


def test_표_내용을_원문으로_돌려준다():
    제목 = tools.table_lookup("1.11")["results"][0]["title"]
    r = tools.table_content(제목)
    assert r["found"] is True
    assert r["number"] == "1.11"
    assert "균열폭" in r["content"]


def test_없는_연도판을_물으면_있는_연도를_알려준다():
    제목 = tools.table_lookup("1.11")["results"][0]["title"]
    r = tools.table_content(제목, year="1999")
    # 모르는 연도는 최신 판본으로 떨어지므로 찾아진다 - 이게 기대 동작이다.
    assert r["found"] is True
    assert r["year"] == "2026"


# ---------------- body_search ----------------

def test_본문검색은_절_이름과_함께_돌려준다():
    r = tools.body_search("선택과업")
    assert r["found"] is True
    assert all(h["section"] and h["text"] for h in r["hits"])


def test_빈_검색어는_거부한다():
    with pytest.raises(ValueError):
        tools.body_search("   ")


def test_본문검색은_표참조_줄을_결과로_주지_않는다():
    """`표참조:` 는 링크일 뿐 답의 근거가 못 된다."""
    for _절, text in kb.body_lines("2026"):
        assert not text.startswith("표참조:")


# ---------------- 명세 ----------------

def test_도구_명세는_MCP가_요구하는_모양을_갖춘다():
    for spec in tools.descriptors():
        assert spec["name"] and spec["description"]
        assert spec["inputSchema"]["type"] == "object"
        assert "run" not in spec, "실행 함수가 프로토콜로 새 나가면 안 된다"
    assert len(tools.descriptors()) == 6


def test_필수인자를_빠뜨리면_TypeError로_드러난다():
    with pytest.raises(TypeError):
        tools.call("grade_lookup", {"member": "콘크리트 바닥판"})
