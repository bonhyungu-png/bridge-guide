# -*- coding: utf-8 -*-
"""이미 만들어져 있는 파일을 그 자리에서 고친다 (재추출이 안 되는 판본용).

구축.py는 PDF에서 전부 다시 뽑는다. 그런데 2022~2024 판본은 지금 저장소에 있는
PDF로는 추출기가 절 위치를 못 찾아 처음부터 다시 만들 수가 없다(글자 깨짐과는
무관한, 원래 있던 문제 - README 참고). 그런 판본은 이미 만들어져 있는 파일을
받아서 깨진 자리만 바꿔 끼운다.

그 파일들은 지금 저장소에 없는 옛 PDF로 만들어졌기 때문에, 같은 내용이라도
깨진 조각이 흩어진 순서가 지금 PDF와 다르다. 그래서 문자열을 그대로 맞대지
않고 순서에 안 휘둘리는 열쇠로 짝을 찾는다.

    열쇠 = (그 조각에 든 깨진 글자 코드의 다중집합, 한글 낱말의 다중집합)

두 다중집합이 같으면 같은 자리로 본다. 세 단계로 맞춰 본다.

  1. 같은 머리를 단 연속 줄('기준: ' 여러 줄 = 표 한 칸)을 통째로
  2. 줄 하나, 또는 줄 안에서 수식이 차지한 구간만
  3. 그래도 짝이 없으면 글자만 사전대로 바꾼다 (순서는 그대로 남는다)

3번으로 처리된 줄은 작업/보정내역.json에 원문째 남긴다.

사용:
    python 보정.py                # 2022 (재추출 불가 판본)
    python 보정.py 2024           # 한 판본만
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

여기 = Path(__file__).resolve().parent
프로젝트 = 여기.parent
스크립트 = 프로젝트 / "DB" / "스크립트"

sys.path.insert(0, str(여기))
sys.path.insert(0, str(스크립트))
sys.path.insert(0, str(프로젝트 / "연구_2"))

import pdfplumber                        # noqa: E402
import 수식복원 as 복원                    # noqa: E402
from 본문공통 import 라벨정리, 항목쪼개기    # noqa: E402
from bridgekb import pdfnorm             # noqa: E402
from 구축 import _밴드확정                 # noqa: E402

기본판본 = ["2022"]   # 2023·2024는 구축.py가 원본 PDF로 다시 뽑는다
원본들 = {"연구_2": 프로젝트 / "연구_2" / "data" / "파생",
          "DB": 프로젝트 / "DB" / "파생"}
결과뿌리 = 여기 / "결과" / "보정"

낱말 = re.compile(r"[가-힣]+")
접두 = re.compile(r"^\s*(?:기준|내용|원문|비고|제목)\s*:\s*|^\s*[-*]\s+")
머리패턴 = re.compile(r"^(기준|내용):\s?")


def 열쇠(s):
    pua = tuple(sorted(ord(c) for c in s if 복원.PUA(c)))
    if not pua:
        return None
    return (pua, tuple(sorted(Counter(낱말.findall(s)).items())))


# ------------------------------------------------------------------ PDF 대조표

def 사전만들기(연도):
    """PDF를 훑어 (열쇠 → 고친 문자열) 대조표를 만든다."""
    표, 충돌 = {}, set()

    def 넣기(깨짐, 고침):
        k = 열쇠(깨짐)
        if k is None or not 고침:
            return
        if k in 표 and 표[k] != 고침:
            충돌.add(k)
        표.setdefault(k, 고침)

    with pdfplumber.open(pdfnorm.pdf_path(연도)) as pdf:
        for page in pdf.pages:
            표들 = [t for t in page.find_tables() if t.cells]
            bboxes = [t.bbox for t in 표들]

            for t in 표들:                                    # 표 한 칸
                for b in t.cells:
                    if b[2] - b[0] < 1 or b[3] - b[1] < 1:
                        continue
                    try:
                        crop = page.crop((b[0] + .5, b[1] + .5, b[2] - .5, b[3] - .5))
                        cs = crop.chars
                    except Exception:
                        continue
                    if not any(복원.PUA(c["text"]) for c in cs):
                        continue
                    깨짐 = re.sub(r"\s+", " ", crop.extract_text(
                        x_tolerance=1.5, y_tolerance=2) or "").strip()
                    고침 = re.sub(r"\s+", " ", 복원.선형화(
                        cs, 복원.분수선들(crop, cs, (), 그래픽=False))).strip()
                    넣기(깨짐, 고침)

            바깥 = [c for c in page.chars                      # 본문 한 줄 묶음
                    if not any(c["x0"] >= b0 - 1 and c["x1"] <= b2 + 1
                               and c["top"] >= b1 - 1 and c["bottom"] <= b3 + 1
                               for b0, b1, b2, b3 in bboxes)]
            if not 바깥:
                continue
            버킷 = {}
            for c in 바깥:
                버킷.setdefault((round(c["top"]), round(c["size"], 1)), []).append(c)
            바들 = 복원.분수선들(page, 바깥, bboxes)
            씨앗 = list(복원.수식밴드(바깥, 바들))
            for cs in 버킷.values():
                if any(복원.PUA(c["text"]) for c in cs):
                    씨앗.append((min(c["top"] for c in cs), max(c["bottom"] for c in cs)))
            if not 씨앗:
                continue
            상자 = [(min(c["top"] for c in cs), max(c["bottom"] for c in cs))
                    for cs in 버킷.values()]
            for y0, y1 in _밴드확정(씨앗, 상자):
                키들 = [k for k, cs in 버킷.items()
                        if min(c["top"] for c in cs) < y1
                        and max(c["bottom"] for c in cs) > y0]
                묶음 = [c for k in 키들 for c in 버킷[k]]
                if not any(복원.PUA(c["text"]) for c in 묶음):
                    continue
                안쪽바 = [b for b in 바들 if y0 - 1 <= b["y"] <= y1 + 1]
                조각 = []
                for k in sorted(키들):
                    cs = sorted(버킷[k], key=lambda x: x["x0"])
                    낸다, 직전 = [], None
                    for c in cs:
                        if 직전 is not None and c["x0"] - 직전["x1"] > 직전["size"] * 0.28:
                            낸다.append(" ")
                        낸다.append(c["text"])
                        직전 = c
                    글 = 라벨정리("".join(낸다).strip())
                    if 글:
                        조각.append(글)
                넣기(" ".join(조각), 라벨정리(복원.선형화(묶음, 안쪽바)))

    for k in 충돌:
        표.pop(k, None)                                       # 애매한 짝은 쓰지 않는다
    return 표, len(충돌)


# ------------------------------------------------------------------ 맞춰 넣기

def 글자만치환(s):
    """짝을 못 찾은 조각 - 글자만 사전대로 바꾼다(순서는 그대로)."""
    낸다 = []
    for ch in s:
        if not 복원.PUA(ch):
            낸다.append(ch)
            continue
        v = 복원.글리프.get("%04X" % ord(ch))
        if v is None:
            낸다.append(ch)
        elif v.get("역할") == "분수선":
            낸다.append("/")
        else:
            낸다.append(v["문자"] or "")
    return "".join(낸다)


def 조각들(줄):
    """한 줄에서 짝을 찾아볼 만한 조각 후보. 긴 것부터."""
    낸다 = [줄]
    m = 접두.match(줄)
    if m:
        낸다.append(줄[m.end():])
    if "|" in 줄:
        낸다 += 줄.split("|")
    낸다 += re.findall(r'"([^"]*)"', 줄)                       # jsonl 안의 문자열
    본 = []
    for s in 낸다:
        s = s.strip()
        if s and any(복원.PUA(c) for c in s) and s not in 본:
            본.append(s)
    return sorted(본, key=len, reverse=True)


def 구간후보(줄):
    """줄 안에서 수식이 차지한 구간 후보. 깨진 글자 양끝에서 낱말 단위로 넓힌다."""
    자리 = [i for i, c in enumerate(줄) if 복원.PUA(c)]
    if not 자리:
        return []
    왼 = 줄.rfind(" ", 0, 자리[0]) + 1
    오 = 줄.find(" ", 자리[-1])
    오 = len(줄) if 오 < 0 else 오
    앞 = [m.start() for m in re.finditer(r"\S+", 줄) if m.start() < 왼]
    뒤 = [m.end() for m in re.finditer(r"\S+", 줄) if m.end() > 오]
    본 = []
    for a in range(0, 10):
        for b in range(0, 10):
            i = 앞[-a] if a and a <= len(앞) else 왼
            j = 뒤[b - 1] if b and b <= len(뒤) else 오
            조각 = 줄[i:j].strip()
            if 조각 and 조각 not in 본:
                본.append(조각)
    return 본


def 묶음교체(줄들, 표):
    """'기준: ' 같은 머리를 단 연속 줄을 표 한 칸으로 보고 통째로 맞춰 본다."""
    낸다, i, 복원수 = [], 0, 0
    while i < len(줄들):
        m = 머리패턴.match(줄들[i])
        if not m:
            낸다.append(줄들[i])
            i += 1
            continue
        머리 = m.group(1)
        j = i
        while j < len(줄들) and 줄들[j].startswith(머리 + ":"):
            j += 1
        덩이 = " ".join(줄들[k][len(머리) + 1:].strip() for k in range(i, j))
        고침 = 표.get(열쇠(덩이)) if any(복원.PUA(c) for c in 덩이) else None
        if 고침:
            항목 = 항목쪼개기(고침) if 머리 == "기준" else [고침]
            낸다 += [머리 + ": " + x for x in 항목]
            복원수 += j - i
        else:
            낸다 += 줄들[i:j]
        i = j
    return 낸다, 복원수


# ------------------------------------------------------------------ 실행

def 실행(연도들):
    기록 = []
    for 연도 in 연도들:
        표, 충돌 = 사전만들기(연도)
        print("-- {} -- PDF 대조표 {}개 (애매해서 버림 {})".format(연도, len(표), 충돌))
        판본 = "안전점검진단_교량@" + 연도
        for 이름, 뿌리 in 원본들.items():
            if not 뿌리.is_dir():
                continue
            for p in sorted(뿌리.rglob("*")):
                if not p.is_file() or p.suffix not in {".md", ".jsonl", ".json"}:
                    continue
                if 판본 not in str(p):
                    continue
                원문 = p.read_text(encoding="utf-8")
                if not any(복원.PUA(c) for c in 원문):
                    continue

                줄들, 복원됨 = 묶음교체(원문.splitlines(), 표)     # 1단계

                새줄, 치환됨, 미해결 = [], 0, []
                for 줄 in 줄들:
                    if not any(복원.PUA(c) for c in 줄):
                        새줄.append(줄)
                        continue
                    for 조각 in 조각들(줄) + 구간후보(줄):        # 2단계
                        고침 = 표.get(열쇠(조각))
                        if 고침:
                            줄 = 줄.replace(조각, 고침)
                            복원됨 += 1
                            if not any(복원.PUA(c) for c in 줄):
                                break
                    if any(복원.PUA(c) for c in 줄):              # 3단계
                        미해결.append(줄[:160])
                        줄 = 글자만치환(줄)
                        치환됨 += 1
                    새줄.append(줄)

                새글 = "\n".join(새줄) + "\n"
                상대 = p.relative_to(뿌리)
                낼곳 = 결과뿌리 / 이름 / 상대
                낼곳.parent.mkdir(parents=True, exist_ok=True)
                낼곳.write_text(새글, encoding="utf-8")
                남 = sum(1 for c in 새글 if 복원.PUA(c))
                기록.append({"판본": 연도, "출처": 이름, "파일": str(상대),
                             "구조복원": 복원됨, "글자만치환": 치환됨,
                             "남은깨짐": 남, "글자만치환_줄": 미해결})
                print("   [{}] {:<50} 구조복원 {:>2} · 글자만 {:>2} · 남은깨짐 {}".format(
                    이름, str(상대)[-50:], 복원됨, 치환됨, 남))

    (여기 / "작업").mkdir(exist_ok=True)
    (여기 / "작업" / "보정내역.json").write_text(
        json.dumps(기록, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n파일 {}개 · 구조복원 {}줄 · 글자만 치환 {}줄 · 남은 깨진 글자 {}개".format(
        len(기록), sum(r["구조복원"] for r in 기록),
        sum(r["글자만치환"] for r in 기록), sum(r["남은깨짐"] for r in 기록)))
    return 기록


if __name__ == "__main__":
    실행(sys.argv[1:] or 기본판본)
