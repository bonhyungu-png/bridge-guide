"""도구 6개 - 답이 흔들리지 않는지 검증한다.

도구 구현은 이제 bridgekb 하나뿐이다(웹앱 JS 사본을 지웠다). 그래서 여기서
지키는 것은 "환경끼리 값이 같다"가 아니라 **이 구현이 지침서 원문과 같다**는
사실이다. 기준값은 균열폭 0.25mm → b등급, 표1.11, 29면.
"면"은 원본 PDF의 실제 쪽 번호다 - 답 아래 "출처"에 그 쪽을 그대로 띄우려면
인쇄면("1-27")이 아니라 파일 안의 물리 쪽이어야 한다(build/17_페이지값_보정.py).
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
    assert r["source"] == {"table": "1.11", "page": 29}
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
    """없는 연도를 조용히 최신판으로 바꾸지 않는다.

    예전에는 1999년을 물으면 아무 말 없이 2026년 기준으로 답했다. 연도마다
    기준이 다르다는 것이 이 도구의 존재 이유인데, 그러면 그 자체가 오답이다.
    """
    제목 = tools.table_lookup("1.11")["results"][0]["title"]
    r = tools.table_content(제목, year="1999")
    assert r["found"] is False
    assert "1999" in r["reason"]
    assert r["available_years"] == ["2022", "2023", "2024", "2026"]


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


# ---------------- 이름 매칭 회귀 ----------------

def test_표기가_갈린_지표도_모든_등급이_조회된다():
    """지침서가 같은 지표를 두 표기로 적어 둔 곳이 있다.

    PSC 거더의 표면손상은 b·c가 "표면 손상면적", d가 "표면손상면적"으로
    띄어쓰기만 다르게 적혀 있다. 표기 하나만 골라 규칙을 거르면 d등급이
    통째로 조회 불가가 됐다 - 손상이 가장 심한 구간이 사라지는 셈이다.
    """
    부재 = "프리스트레스 콘크리트 거더"
    assert tools.grade_lookup(부재, "표면손상면적", 1)["grade"] == "b"
    assert tools.grade_lookup(부재, "표면손상면적", 5)["grade"] == "c"

    r = tools.grade_lookup(부재, "표면손상면적", 15)
    assert r["found"] is True
    assert r["grade"] == "d"
    assert "10%이상" in r["quote"].replace(" ", "")


def test_이름이_여러_부재에_걸리면_등급을_고르지_않는다():
    """교면포장은 시멘트와 아스팔트가 서로 다른 표이고 등급도 다르다.

    예전에는 정렬상 앞선 시멘트를 말없이 골라 b등급을 출처까지 붙여 답했다.
    아스팔트였다면 c등급이므로 사용자는 틀렸다는 걸 알 방법이 없었다.
    """
    r = tools.grade_lookup("교면포장", "포장불량률", 5)
    assert r["found"] is False
    assert r["candidates"] == ["시멘트 콘크리트 교면포장", "아스팔트 콘크리트 교면포장"]

    # 어느 쪽인지 정해 주면 그때는 서로 다른 등급이 나온다.
    assert tools.grade_lookup("시멘트 콘크리트 교면포장", "포장불량률", 5)["grade"] == "b"
    assert tools.grade_lookup("아스팔트 콘크리트 교면포장", "포장불량률", 5)["grade"] == "c"


def test_더_구체적인_이름은_모호하게_보지_않는다():
    """'프리스트레스 콘크리트 바닥판'은 '콘크리트 바닥판'도 함께 걸리지만
    앞의 것이 뒤의 것을 통째로 품고 있으므로 더 구체적인 쪽으로 확정한다."""
    r = tools.grade_lookup("프리스트레스 콘크리트 바닥판", "균열폭", 0.25)
    assert r["found"] is True
    assert r["member"] == "프리스트레스 콘크리트 바닥판"


def test_본문검색이_한_절에_자리를_다_뺏기지_않는다():
    """'균열'은 56건 중 42건이 1.4 상태평가기준에 있는데, 앞에서부터 8건을
    채우면 1.1 관리일반만 8건 나오고 정작 필요한 절을 한 줄도 못 봤다."""
    r = tools.body_search("균열", year="2026")
    절 = {h["section"] for h in r["hits"]}
    assert len(절) > 1
    assert any("1.4" in s for s in 절)
    assert r["total"] > len(r["hits"])
    assert r["truncated"] is True
