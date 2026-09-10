# -*- coding: utf-8 -*-
"""데이터 구축 — 한 번 실행하면 4개 판본 데이터가 전부 다시 만들어진다.

기존 DB/스크립트의 00~05단계를 그대로 쓰되, 텍스트가 만들어지는 두 지점에만
수식복원을 끼워 넣는다.

  · 02_표추출.셀글자()       — 표 한 칸의 글자
  · 00_본문추출.병합스트림()  — 본문 한 줄

끼워 넣는 조건은 "그 자리에 깨진 글자(PUA)나 분수가 있을 때"뿐이다. 나머지
글자는 기존 코드가 만든 값을 그대로 쓴다 - 이미 검증된 파일을 건드리지 않기
위해서다.

원본 DB는 읽기만 하고, 결과는 전부 이 폴더의 결과/ 아래에 새로 쓴다.

사용:
    python 구축.py            # 4개 판본 전부
    python 구축.py 2026       # 한 판본만
"""
import importlib.util
import re
import shutil
import sys
from pathlib import Path

여기 = Path(__file__).resolve().parent
프로젝트 = 여기.parent
스크립트 = 프로젝트 / "DB" / "스크립트"
원본DB = 프로젝트 / "DB"
결과DB = 여기 / "결과"

sys.path.insert(0, str(여기))
sys.path.insert(0, str(스크립트))
sys.path.insert(0, str(프로젝트 / "연구_2"))

import pdfplumber                      # noqa: E402
import 수식복원 as 복원                  # noqa: E402
from bridgekb import pdfnorm           # noqa: E402

판본들 = ["2023", "2024", "2026"]
통계 = {"셀": 0, "본문줄": 0, "분수": 0}

# ------------------------------------------------------------------ 원본 PDF
# 연구_2/data/원본pdf 의 2022~2024 파일은 제목·표캡션·면번호가 전부 그림으로
# 구워진 사본이라(이미지 2,900여 개) 절도 표번호도 읽히지 않는다. 원본 폴더의
# 2단 편집본이 진짜다. 2026은 애초에 PDF로 배포돼 그대로 쓴다.
# 2022는 쓸 만한 PDF가 없어(HWP만 있음) 판본들에서 뺐다 - README 참고.
_법령 = 프로젝트 / "시설물의 안전 및 유지관리 세부지침.pdf"
_교량편 = "01. 시설물의 안전 및 유지관리 실시 세부지침(안전점검·진단 편)_교량편.pdf"
원본PDF = {
    "2023": _법령 / "2023 교량 관련 법령" / _교량편,
    "2024": _법령 / "2024 교량 관련 법령" / _교량편,
    "2026": 프로젝트 / "연구_2" / "data" / "원본pdf" / "2026.pdf",
}
_원래경로 = pdfnorm.pdf_path
pdfnorm.pdf_path = lambda 연도: 원본PDF.get(연도) or _원래경로(연도)
pdfnorm.detect_layout.cache_clear()


def _모듈(이름, 파일명):
    spec = importlib.util.spec_from_file_location(이름, 스크립트 / 파일명)
    m = importlib.util.module_from_spec(spec)
    sys.modules[이름] = m
    spec.loader.exec_module(m)
    return m


# ------------------------------------------------------------------ 표 한 칸

def 셀글자_수정(page, bbox):
    x0, top, x1, bottom = bbox
    if x1 - x0 < 1 or bottom - top < 1:
        return ""
    try:
        crop = page.crop((x0 + 0.5, top + 0.5, x1 - 0.5, bottom - 0.5))
        cs = crop.chars
    except Exception:
        return ""
    if not any(복원.PUA(c["text"]) for c in cs):    # 멀쩡한 칸은 기존 경로 그대로
        try:
            t = crop.extract_text(x_tolerance=1.5, y_tolerance=2) or ""
        except Exception:
            return ""
        return re.sub(r"\s+", " ", t).strip()
    통계["셀"] += 1
    바 = 복원.분수선들(crop, cs, (), 그래픽=False)   # 셀 안에서는 괘선을 쓰지 않는다
    return re.sub(r"\s+", " ", 복원.선형화(cs, 바)).strip()


# ------------------------------------------------------------------ 본문 한 줄

def _합치기(구간들):
    합 = []
    for y0, y1 in sorted(구간들):
        if 합 and y0 <= 합[-1][1] + 1:
            합[-1] = (합[-1][0], max(합[-1][1], y1))
        else:
            합.append((y0, y1))
    return 합


def _밴드확정(씨앗, 상자들):
    """씨앗 구간을, 세로로 겹치는 줄들을 흡수할 때까지 넓힌다."""
    구간 = _합치기(씨앗)
    for _ in range(6):
        바뀜 = False
        새 = []
        for y0, y1 in 구간:
            for t, b in 상자들:
                if t < y1 and b > y0 and (t < y0 or b > y1):
                    y0, y1 = min(y0, t), max(y1, b)
                    바뀜 = True
            새.append((y0, y1))
        구간 = _합치기(새)
        if not 바뀜:
            break
    return 구간


def 병합스트림_수정(본문, 연도):
    """00_본문추출.병합스트림과 같되, 수식/깨진 글자가 있는 구간만 복원한다."""
    from bridgekb import pdfnorm
    cfg = 본문.문서형식감지(연도)
    스트림 = []
    with pdfplumber.open(pdfnorm.pdf_path(연도)) as pdf:
        for 면번호, page in enumerate(pdf.pages, 1):
            if 면번호 in cfg["목차면"]:
                continue
            bboxes = 본문.표bbox들(page)
            mid = page.width / 2

            def 칼럼(x0, x1):
                return 0 if not cfg["이단"] else (0 if (x0 + x1) / 2 < mid else 1)

            바깥 = [c for c in page.chars
                    if not any(c["x0"] >= b0 - 1 and c["x1"] <= b2 + 1
                               and c["top"] >= b1 - 1 and c["bottom"] <= b3 + 1
                               for b0, b1, b2, b3 in bboxes)]

            버킷 = {}
            for c in 바깥:
                키 = (칼럼(c["x0"], c["x1"]), round(c["top"]), round(c["size"], 1))
                버킷.setdefault(키, []).append(c)

            바들 = 복원.분수선들(page, 바깥, bboxes)
            씨앗 = list(복원.수식밴드(바깥, 바들))
            for cs in 버킷.values():                 # 깨진 글자가 있는 줄도 씨앗
                if any(복원.PUA(c["text"]) for c in cs):
                    씨앗.append((min(c["top"] for c in cs),
                                 max(c["bottom"] for c in cs)))

            줄들, 처리됨 = [], set()
            for col in ([0, 1] if cfg["이단"] else [0]):
                상자 = [(min(c["top"] for c in cs), max(c["bottom"] for c in cs))
                        for k, cs in 버킷.items() if k[0] == col]
                for y0, y1 in _밴드확정(씨앗, 상자):
                    키들 = [k for k, cs in 버킷.items()
                            if k[0] == col and k not in 처리됨
                            and min(c["top"] for c in cs) < y1
                            and max(c["bottom"] for c in cs) > y0]
                    if not 키들:
                        continue
                    묶음 = [c for k in 키들 for c in 버킷[k]]
                    안쪽바 = [b for b in 바들 if y0 - 1 <= b["y"] <= y1 + 1
                              and 칼럼(b["x0"], b["x1"]) == col]
                    if not any(복원.PUA(c["text"]) for c in 묶음) and not 안쪽바:
                        continue                     # 고칠 이유가 없는 구간
                    글 = 본문.라벨정리(복원.선형화(묶음, 안쪽바))
                    if not 글:
                        continue
                    처리됨.update(키들)
                    통계["본문줄"] += len(키들)
                    통계["분수"] += len(안쪽바)
                    크기 = max({c["size"] for c in 묶음},
                               key=lambda s: sum(1 for c in 묶음 if c["size"] == s))
                    줄들.append({"kind": "line", "col": col,
                                 "top": min(round(c["top"]) for c in 묶음),
                                 "size": round(크기, 1), "text": 글, "면": 면번호})

            for (col, top, size), cs in 버킷.items():
                if (col, top, size) in 처리됨:
                    continue
                cs = sorted(cs, key=lambda x: x["x0"])
                조각, 직전 = [], None
                for c in cs:
                    if 직전 is not None and c["x0"] - 직전["x1"] > 직전["size"] * 0.28:
                        조각.append(" ")
                    조각.append(c["text"])
                    직전 = c
                글 = 본문.라벨정리("".join(조각).strip())
                if 글:
                    줄들.append({"kind": "line", "col": col, "top": top,
                                 "size": size, "text": 글, "면": 면번호})

            표들 = [dict(t, kind="table", 면=면번호) for t in 본문.표읽기(page, cfg)]
            for it in 줄들 + 표들:
                it.setdefault("size", None)
            스트림.extend(sorted(줄들 + 표들, key=lambda it: (it["col"], it["top"])))
    return tuple(스트림), cfg


# ------------------------------------------------------------------ 실행

def 준비():
    결과DB.mkdir(parents=True, exist_ok=True)
    (결과DB / "검수").mkdir(exist_ok=True)
    for 연도, p in 원본PDF.items():
        if not p.exists():
            raise FileNotFoundError("{}년 원본 PDF 없음: {}".format(연도, p))


def _남은PUA(뿌리):
    n = 0
    for p in 뿌리.rglob("*"):
        if p.is_file() and p.suffix in {".md", ".json", ".jsonl"}:
            n += sum(1 for ch in p.read_text(encoding="utf-8") if 복원.PUA(ch))
    return n


def 실행(연도들):
    준비()
    골격 = _모듈("골격_p", "01_문서골격.py")
    표추출 = _모듈("표추출_p", "02_표추출.py")
    본문 = _모듈("본문추출_p", "00_본문추출.py")
    검수 = _모듈("검수_p", "03_검수.py")
    판정규칙 = _모듈("판정규칙_p", "04_판정규칙.py")
    읽기용 = _모듈("읽기용_p", "05_읽기용.py")

    표추출.셀글자 = 셀글자_수정
    본문._글자 = 셀글자_수정          # 00_본문추출은 자기 _글자()로 표 칸을 읽는다
    본문.병합스트림 = lambda 연도: 병합스트림_수정(본문, 연도)
    for m in (골격, 표추출, 본문, 검수, 판정규칙, 읽기용):
        m.DB = 결과DB
    판정규칙.파생 = 결과DB / "파생"
    판정규칙.파생.mkdir(parents=True, exist_ok=True)

    for 연도 in 연도들:
        print("\n-- " + 연도 + " --  " + 원본PDF[연도].name[:44])
        문서 = 골격.실행(연도)
        print("  문서골격 절 {}개 · 표캡션 {}개".format(
            len(문서["절"]), 문서["요약"]["표캡션_고유"]))
        표들, 미매칭 = 표추출.실행(연도)
        print("  표추출   {}개 (무번호 {})".format(len(표들), 미매칭))
        결과, _, _ = 본문.실행(연도)
        print("  본문추출 절 {}개".format(len(결과)))
        보고, _, _ = 검수.실행(연도)
        print("  검수     통과 {} / 검수필요 {}".format(보고["자동통과"], 보고["검수필요"]))
        n, _ = 판정규칙.실행(연도)
        print("  판정규칙 {}건".format(len(n) if hasattr(n, "__len__") else n))
        n, _ = 읽기용.실행(연도)
        print("  읽기용   {}개".format(n))

    print("\n복원: 표 {}칸 · 본문 {}줄 · 분수 {}개".format(
        통계["셀"], 통계["본문줄"], 통계["분수"]))
    남은 = _남은PUA(결과DB)
    print("결과 폴더에 남은 깨진 글자: {}개".format(남은))
    if 복원.미해독:
        print("[!] 사전에 없는 코드: " + str(sorted(복원.미해독)))
    if 복원.추정사용:
        print("[!] 육안확인 아닌 '추정' 매핑 사용: " + str(sorted(복원.추정사용)))
    return 남은


if __name__ == "__main__":
    실행(sys.argv[1:] or 판본들)
