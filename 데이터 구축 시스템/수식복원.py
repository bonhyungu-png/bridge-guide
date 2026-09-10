# -*- coding: utf-8 -*-
"""한컴 수식폰트(PUA) 복원 — 글자 치환 + 분수 2차원 구조 선형화.

두 가지를 고친다.

1) 글자 치환
   HyhwpEQ / HancomEQN 폰트에는 ToUnicode CMap이 없어 pdfplumber가 글리프 번호
   (U+E000~U+F8FF)를 그대로 돌려준다. 글리프사전.json이 그 번호를 실제 문자로 바꾼다.

2) 분수 선형화
   분수는 종이 위에서 위/아래로 쌓여 있는데 extract_text()는 y좌표로 줄을 나눠
   위에서 아래로 이어붙인다. 그래서 "½c′"가 "1 … c′ … ― … 2"로 흩어진다.
   분수 가로줄을 찾아 그 x범위 안의 위/아래 글자를 분자·분모로 모아
   "분자/분모" 한 덩어리로 되돌린 뒤, 나머지 글자와 x순서로 다시 엮는다.

분수 가로줄은 두 형태로 나온다.
  - 글리프 U+E06D (수식 폰트가 그리는 줄)
  - 얇은 그래픽 선 (한글 본문 크기 분수는 이쪽)
둘 다 잡는다.
"""
import json, re
from pathlib import Path

_사전경로 = Path(__file__).with_name("글리프사전.json")
_본 = json.loads(_사전경로.read_text(encoding="utf-8"))
글리프 = _본["글리프"]

PUA = lambda ch: "\ue000" <= ch <= "\uf8ff"
미해독 = set()          # 사전에 없는 코드를 만나면 여기 쌓인다
추정사용 = set()        # 육안확인이 아닌 '추정' 항목을 쓴 경우


def 문자(c):
    """char dict → 실제 문자. 분수선 글리프는 빈 문자열(구조로만 쓰임)."""
    t = c["text"]
    if not PUA(t):
        return t
    k = f"{ord(t):04X}"
    v = 글리프.get(k)
    if v is None:
        미해독.add(k)
        return t
    if v.get("상태") == "추정":
        추정사용.add(k)
    return v["문자"] or ""


def 분수선글리프(c):
    t = c["text"]
    if not PUA(t):
        return False
    return (글리프.get(f"{ord(t):04X}") or {}).get("역할") == "분수선"


# ------------------------------------------------------------------ 분수선 찾기

def _글리프바(chars):
    바 = []
    for c in chars:
        if 분수선글리프(c):
            # 글리프 상자 안에서 실제 가로줄은 위에서 약 15% 지점에 그려진다
            # (2024 p31 ½, 2026 p30 균열률 두 사례로 확인)
            바.append({"x0": c["x0"], "x1": c["x1"],
                       "y": c["top"] + (c["bottom"] - c["top"]) * 0.15,
                       "출처": "글리프", "char": c})
    return 바


def _분수모양(x0, x1, 위, 아래):
    """그려진 가로선이 진짜 분수선인지 가린다.

    분수선은 분자·분모 폭에 맞춰 그 가운데에 그어진다. 표 괘선이나 제목 밑줄은
    위아래 글자보다 훨씬 길고 가운데도 안 맞는다 - 그 차이로 거른다.
    (오탐 사례: 2024 6면, 폭 297pt 표 괘선이 '철근콘크리트 거더'와
     '점검부위 손상종류'를 분자·분모로 삼켜 제목 한 줄이 통째로 사라졌다.)
    """
    폭 = x1 - x0
    가운데 = (x0 + x1) / 2
    허용 = max(3.0, 폭 * 0.12)
    내용폭 = 0.0
    for 쪽 in (위, 아래):
        a = min(o["x0"] for o in 쪽)
        b = max(o["x1"] for o in 쪽)
        if abs((a + b) / 2 - 가운데) > 허용:
            return False                  # 선 가운데에 안 놓임
        if a < x0 - 2 or b > x1 + 2:
            return False                  # 선 밖으로 삐져나옴
        내용폭 = max(내용폭, b - a)
    return 폭 <= 내용폭 * 1.35 + 6         # 선이 내용보다 지나치게 길다


def _그래픽바(page, chars, 제외bbox=()):
    """얇은 가로선 중 분수선 모양을 갖춘 것만 고른다."""
    바 = []
    for o in list(page.lines) + list(page.rects):
        if o["height"] > 1.0 or o["width"] < 8 or o["width"] > 320:
            continue
        y = (o["top"] + o["bottom"]) / 2
        if any(o["x0"] >= bx0 - 2 and o["x1"] <= bx1 + 2
               and o["top"] >= bt - 2 and o["bottom"] <= bb + 2
               for bx0, bt, bx1, bb in 제외bbox):
            continue                      # 표 안 괘선
        후보 = [c for c in chars
                if o["x0"] - 1 <= (c["x0"] + c["x1"]) / 2 <= o["x1"] + 1]
        위 = _가까운줄(후보, y, True)
        아래 = _가까운줄(후보, y, False)
        if not 위 or not 아래:
            continue
        높이 = max(o["bottom"] - o["top"] for o in 위 + 아래) or 10.0
        if y - max(o["bottom"] for o in 위) > 높이 * 0.8:
            continue                      # 분자가 너무 멀다
        if min(o["top"] for o in 아래) - y > 높이 * 0.8:
            continue                      # 분모가 너무 멀다
        if not _분수모양(o["x0"], o["x1"], 위, 아래):
            continue
        바.append({"x0": o["x0"], "x1": o["x1"], "y": y, "출처": "선", "char": None})
    return 바


def 분수선들(page, chars, 제외bbox=(), 그래픽=True):
    """분수 가로줄 목록. 표 셀 안에서는 괘선을 분수선으로 오인하지 않도록 그래픽=False."""
    바 = _글리프바(chars)
    if 그래픽:
        바 += _그래픽바(page, chars, 제외bbox)
    return 바


# ------------------------------------------------------------------ 선형화

def _중심y(o):
    return (o["top"] + o["bottom"]) / 2


def _묶음(항목들, 여유=0.6):
    """세로 위치가 가까운 것끼리 줄로 묶는다."""
    if not 항목들:
        return []
    항목들 = sorted(항목들, key=_중심y)
    높이 = sorted(o["bottom"] - o["top"] for o in 항목들)[len(항목들) // 2]
    한계 = max(2.0, 높이 * 여유)
    줄들, 현재 = [], [항목들[0]]
    for o in 항목들[1:]:
        if _중심y(o) - _중심y(현재[-1]) > 한계:
            줄들.append(현재); 현재 = [o]
        else:
            현재.append(o)
    줄들.append(현재)
    return 줄들


def _가까운줄(후보, 바y, 위쪽):
    """분수선 바로 위(또는 아래) 한 줄만 고른다. 그 다음 줄까지 삼키지 않도록."""
    쪽 = [o for o in 후보 if (_중심y(o) < 바y) == 위쪽]
    if not 쪽:
        return []
    줄들 = _묶음(쪽)
    return 줄들[-1] if 위쪽 else 줄들[0]


def _글자잇기(항목들):
    """x순으로 이어붙인다. 간격이 넓으면 공백."""
    항목들 = sorted(항목들, key=lambda o: o["x0"])
    낸다, 직전 = [], None
    for o in 항목들:
        if not o["글"]:
            continue
        if 직전 is not None and o["x0"] - 직전["x1"] > 직전["size"] * 0.28:
            낸다.append(" ")
        낸다.append(o["글"])
        직전 = o
    return re.sub(r"\s+", " ", "".join(낸다)).strip()


def _줄잇기(항목들):
    """줄 단위로 묶어 위에서 아래로, 줄 안에서는 x순으로 잇는다."""
    return " ".join(_글자잇기(줄) for 줄 in _묶음(항목들) if _글자잇기(줄))


def _분수문자열(분자, 분모):
    if 분자 == "1" and 분모 == "2":
        return "½"
    if not 분자 or not 분모:
        return 분자 or 분모
    감싸기 = lambda s: f"({s})" if re.search(r"[ ×÷+\-−=/]", s) else s
    return f"{감싸기(분자)}/{감싸기(분모)}"


def _접기(chars, 바들):
    """분수를 안쪽부터 접어 (남은 조각들, 수식이 차지한 세로 구간들)을 돌려준다."""
    후보 = [{"x0": c["x0"], "x1": c["x1"], "top": c["top"], "bottom": c["bottom"],
            "size": c["size"], "글": 문자(c)}
           for c in chars if not 분수선글리프(c)]
    밴드 = []
    for 바 in sorted(바들, key=lambda b: b["x1"] - b["x0"]):
        안 = [o for o in 후보 if 바["x0"] - 1 <= (o["x0"] + o["x1"]) / 2 <= 바["x1"] + 1]
        분자항 = _가까운줄(안, 바["y"], True)
        분모항 = _가까운줄(안, 바["y"], False)
        쓴것 = 분자항 + 분모항
        if not 쓴것:
            continue
        밴드.append((min([o["top"] for o in 쓴것] + [바["y"]]),
                     max([o["bottom"] for o in 쓴것] + [바["y"]])))
        쓰임 = {id(o) for o in 쓴것}
        후보 = [o for o in 후보 if id(o) not in 쓰임]
        크기 = (바["char"] or {}).get("size") or 쓴것[0]["size"]
        후보.append({"x0": 바["x0"], "x1": 바["x1"],
                     "top": 바["y"] - 크기 / 2, "bottom": 바["y"] + 크기 / 2,
                     "size": 크기,
                     "글": _분수문자열(_글자잇기(분자항), _글자잇기(분모항))})
    return 후보, 밴드


def 선형화(chars, 바들):
    """글자들과 분수선들을 받아 사람이 읽는 한 줄로 되돌린다.

    분수선을 좁은 것(= 안쪽)부터 처리한다. 분수 하나를 접을 때마다 분자·분모
    글자를 후보에서 빼고 완성된 "분자/분모" 덩어리를 도로 넣기 때문에 중첩
    분수도 안쪽부터 자연히 접힌다. 남은 조각은 줄 단위로 묶어 위에서 아래로,
    줄 안에서는 x순으로 잇는다.
    """
    후보, _ = _접기(chars, 바들)
    return _줄잇기(후보)


def 수식밴드(chars, 바들):
    """분수 구조가 차지하는 세로 구간 [(y0, y1), ...]. 겹치는 것은 합친다."""
    _, 밴드 = _접기(chars, 바들)
    합 = []
    for y0, y1 in sorted(밴드):
        if 합 and y0 <= 합[-1][1] + 2:
            합[-1] = (합[-1][0], max(합[-1][1], y1))
        else:
            합.append((y0, y1))
    return 합
