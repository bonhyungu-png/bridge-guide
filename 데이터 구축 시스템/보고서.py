# -*- coding: utf-8 -*-
"""보고/변경내역.md 생성 — 무엇이 어떻게 바뀌었는지 전부 적는다."""
import difflib
import json
import re
import sys
from pathlib import Path

여기 = Path(__file__).resolve().parent
프로젝트 = 여기.parent
sys.path.insert(0, str(여기))
import 수식복원 as 복원  # noqa: E402

보고 = 여기 / "보고"
보고.mkdir(exist_ok=True)


def 보이기(s):
    return "".join("〈%04X〉" % ord(c) if 복원.PUA(c) else c for c in s)


def 잘라(s, n=150):
    s = 보이기(s).replace("\t", " ")
    return s if len(s) <= n else s[:n] + " …"


줄 = ["# 변경내역", "",
      "깨진 글자(한컴 수식폰트 PUA)를 고친 결과. 바꾼 값은 전부 PDF의 같은 자리에서",
      "다시 읽어 만든 것이고, 사람이 지어낸 문장은 없다.", ""]

# ── 2026: 전체 재생성
원 = 프로젝트 / "DB" / "파생"
새 = 여기 / "결과" / "파생"
줄 += ["## 2023 · 2024 · 2026 — PDF에서 전부 다시 생성", "",
       "`python 구축.py`. 아래에 없는 파일은 기존 결과와 **바이트 단위로 동일**하다.", ""]
같음 = 0
덩이 = []
for a in sorted(원.rglob("*")):
    if not a.is_file() or not any(y in str(a) for y in ("@2023", "@2024", "@2026")):
        continue
    b = 새 / a.relative_to(원)
    if not b.exists():
        continue
    x = a.read_text(encoding="utf-8").splitlines()
    y = b.read_text(encoding="utf-8").splitlines()
    if x == y:
        같음 += 1
        continue
    d = [l for l in difflib.unified_diff(x, y, lineterm="", n=0)
         if l[:1] in "+-" and l[:3] not in ("---", "+++")]
    덩이.append((str(a.relative_to(원)), d))
줄 += ["- 동일한 파일: **%d개**" % 같음, "- 바뀐 파일: **%d개**" % len(덩이), ""]
for f, d in 덩이:
    줄 += ["### " + f.replace("\\", "/"), ""]
    전 = [l[1:] for l in d if l.startswith("-")]
    후 = [l[1:] for l in d if l.startswith("+")]
    for i in range(max(len(전), len(후))):
        if i < len(전):
            줄.append("- 전: `%s`" % 잘라(전[i]))
        if i < len(후):
            줄.append("- 후: `%s`" % 잘라(후[i]))
        줄.append("")

# ── 2022~2024: 자리 보정
경로 = 여기 / "작업" / "보정내역.json"
if 경로.exists():
    기록 = json.loads(경로.read_text(encoding="utf-8"))
    줄 += ["", "## 2022 판본 — 기존 파일 자리 보정", "",
           "2022는 쓸 만한 PDF가 없다(HWP만 있음. 지금 있는 2022.pdf는 제목·표캡션·",
           "면번호가 전부 그림으로 구워진 사본). 그래서 기존 파일의 깨진 자리만",
           "바꿔 끼웠다 — README 참고.", "",
           "- **구조복원**: PDF의 같은 칸을 찾아 분수·차례까지 되살린 줄",
           "- **글자만치환**: 짝을 못 찾아 글자만 사전대로 바꾼 줄 (뜻은 읽히지만 차례는 흐트러진 채)", "",
           "| 판본 | 파일 | 구조복원 | 글자만치환 | 남은 깨짐 |", "|---|---|---:|---:|---:|"]
    for r in 기록:
        if r["출처"] != "연구_2":
            continue
        줄.append("| %s | %s | %d | %d | %d |" % (
            r["판본"], r["파일"].replace("\\", "/"), r["구조복원"], r["글자만치환"], r["남은깨짐"]))
    남은줄 = [(r["판본"], r["파일"], l) for r in 기록 if r["출처"] == "연구_2"
              for l in r["글자만치환_줄"]]
    if 남은줄:
        줄 += ["", "### 글자만 바꾼 줄 (차례가 흐트러진 채로 남음)", "",
               "총 %d줄. 뜻을 읽는 데는 지장이 없지만 수식의 앞뒤 차례는 원문과 다르다." % len(남은줄), ""]
        for 판, f, l in 남은줄:
            줄 += ["- `%s` %s" % (판, Path(f).name), "  - `%s`" % 잘라(l, 200)]

(보고 / "변경내역.md").write_text("\n".join(줄) + "\n", encoding="utf-8")
print("보고/변경내역.md 생성 — 2026 변경 %d파일 / 동일 %d파일" % (len(덩이), 같음))
