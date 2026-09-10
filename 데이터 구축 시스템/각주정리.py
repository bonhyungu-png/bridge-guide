# -*- coding: utf-8 -*-
"""표 각주가 소제목(#####)으로 승격된 것을 되돌려 '내용:' 줄로 되돌린다.

00_본문추출.py의 주헤딩인가()는 "주N)" 뒤 글이 34자 이하이고 마침표로 끝나지
않으면 소제목으로 올린다. 그 판정이 표 각주까지 소제목으로 만들어, 뒤따르는
표참조가 각주 밑에 딸린 것처럼 문서 계층이 뒤틀렸다.

각주와 진짜 소제목을 가르는 기준:
    연속된 주1) 주2) … 묶음을 하나로 보고, 그 묶음 중 어느 하나라도 바로 아래에
    "주N)"으로 시작하지 않는 본문이 붙어 있으면 소제목 묶음으로 둔다.
    아무도 그런 본문을 갖고 있지 않으면 통째로 각주 묶음이다.

각주 묶음만 '내용:' 줄로 바꾸고, 소제목 서식으로 넣었던 빈 줄을 걷어낸다.
다른 줄은 손대지 않는다.

사용:
    python 각주정리.py --확인   # 무엇이 바뀌는지만 출력
    python 각주정리.py          # 실제로 고침
"""
import re
import sys
from pathlib import Path

여기 = Path(__file__).resolve().parent
대상뿌리 = 여기 / "결과"

헤딩 = re.compile(r"^##### 주(\d+)\)\s*(.*)$")
주내용 = re.compile(r"^내용:\s*주\d+\)")
본문줄 = re.compile(r"^(내용|표참조):")


def 묶음들(줄들):
    """연속된 ##### 주N) 헤딩을 (인덱스 목록)으로 묶는다. 사이에 본문이 있어도
    번호가 이어지면 같은 묶음으로 본다."""
    자리 = [i for i, l in enumerate(줄들) if 헤딩.match(l)]
    묶 = []
    for i in 자리:
        n = int(헤딩.match(줄들[i]).group(1))
        if 묶 and n == int(헤딩.match(줄들[묶[-1][-1]]).group(1)) + 1:
            묶[-1].append(i)
        else:
            묶.append([i])
    return 묶


def 각주묶음인가(줄들, 묶음):
    """묶음 안 어느 헤딩이든 '주N)'이 아닌 본문을 데리고 있으면 소제목이다."""
    for i in 묶음:
        j = i + 1
        while j < len(줄들) and not 줄들[j].strip():
            j += 1
        if j >= len(줄들):
            continue
        다음 = 줄들[j]
        if 헤딩.match(다음) or 주내용.match(다음):
            continue                      # 같은 각주 계열이 이어짐
        if 다음.startswith("#") or 다음.startswith("표참조:"):
            continue                      # 아래에 딸린 본문 없음
        return False                      # 진짜 설명이 붙어 있다 → 소제목
    return True


def 고치기(줄들):
    바꿀 = set()
    for 묶음 in 묶음들(줄들):
        if 각주묶음인가(줄들, 묶음):
            바꿀.update(묶음)
    if not 바꿀:
        return 줄들, []

    바뀜 = []
    새 = []
    for i, l in enumerate(줄들):
        if i in 바꿀:
            m = 헤딩.match(l)
            고침 = "내용: 주%s) %s" % (m.group(1), m.group(2))
            바뀜.append((i + 1, l, 고침))
            새.append(("변환", 고침))
        else:
            새.append(("그대로", l))

    # 소제목 서식으로 넣었던 빈 줄 걷어내기 - 변환된 줄에 맞닿은 것만
    낸다 = []
    k = 0
    while k < len(새):
        종류, 글 = 새[k]
        if 글.strip():
            낸다.append((종류, 글))
            k += 1
            continue
        j = k
        while j < len(새) and not 새[j][1].strip():
            j += 1
        앞 = 낸다[-1] if 낸다 else None
        뒤 = 새[j] if j < len(새) else None
        맞닿음 = (앞 and 앞[0] == "변환") or (뒤 and 뒤[0] == "변환")
        양쪽본문 = (앞 and 본문줄.match(앞[1])) and (뒤 and 본문줄.match(뒤[1]))
        if 맞닿음 and 양쪽본문:
            k = j                         # 빈 줄 버림
            continue
        낸다 += 새[k:j]
        k = j
    return [글 for _, 글 in 낸다], 바뀜


def 실행(확인만):
    총파일 = 총줄 = 0
    for p in sorted(대상뿌리.rglob("*.md")):
        원문 = p.read_text(encoding="utf-8")
        줄들 = 원문.splitlines()
        새줄, 바뀜 = 고치기(줄들)
        if not 바뀜:
            continue
        총파일 += 1
        총줄 += len(바뀜)
        print("== %s" % p.relative_to(대상뿌리))
        for 행, 전, 후 in 바뀜:
            print("   %4d  - %s" % (행, 전))
            print("         + %s" % 후)
        if not 확인만:
            p.write_text("\n".join(새줄) + "\n", encoding="utf-8")
    print("\n파일 %d개 · 줄 %d개%s" % (총파일, 총줄, " (확인만 함)" if 확인만 else " 고침"))


if __name__ == "__main__":
    실행("--확인" in sys.argv)
