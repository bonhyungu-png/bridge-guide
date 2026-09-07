# -*- coding: utf-8 -*-
"""웹 GUI를 기본 브라우저로 연다.

`/bridge-guide` 슬래시 커맨드가 이 스크립트를 부른다.

왜 스크립트인가: 예전에는 커맨드 파일이 모델에게 "경로를 찾아서 OS에 맞는
명령으로 열어라"고 시켰다. 그러면 매번 모델이 경로를 추측하고 `start`/`open`/
`xdg-open` 중에 고르는데, 그게 실패 지점이었다. 경로 계산과 브라우저 열기는
정해진 일이므로 코드가 한다.

의존성 없음. `webbrowser`가 OS별 차이를 흡수하고, 한글·공백이 든 경로는
`as_uri()`가 퍼센트 인코딩한다.

사용:
    python 열기.py                        # 그냥 연다
    python 열기.py 세굴                    # 본문 검색 탭을 그 질의로 열고
    python 열기.py 표1.31                  # 표처럼 보이면 표 조회 탭으로 연다
"""
import re
import sys
import webbrowser
from pathlib import Path
from urllib.parse import quote

HTML = Path(__file__).resolve().parent / "webapp" / "bridge_guide.html"

# "1.31", "표1.31", "표 1.31" 처럼 보이면 표 조회 탭으로 연다.
표번호 = re.compile(r"^표?\s*\d+\.\d+(?:의\d+)?$")


def url_for(question: str) -> str:
    base = HTML.as_uri()
    q = (question or "").strip()
    if not q:
        return base
    tab = "anchor" if 표번호.match(q) else "search"
    return "%s?tab=%s&q=%s" % (base, tab, quote(q))


def main(argv) -> int:
    # 이 출력은 슬래시 커맨드를 통해 대화에 그대로 주입된다. 윈도우 콘솔
    # 기본 인코딩(cp949)으로 나가면 한글이 깨진 채로 모델에게 전달된다.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    if not HTML.exists():
        print("웹앱 파일이 없습니다: %s" % HTML, file=sys.stderr)
        print("먼저 만드세요: python build/20_아티팩트_데이터.py "
              "&& python build/21_웹앱_빌드.py", file=sys.stderr)
        return 1

    url = url_for(" ".join(argv))
    if not webbrowser.open(url):
        # 헤드리스 등 브라우저를 못 여는 환경. 주소를 알려주고 물러난다.
        print("브라우저를 열지 못했습니다. 직접 여세요:", file=sys.stderr)
        print(url)
        return 1

    print("교량 지침서 가이드를 열었습니다.")
    print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
