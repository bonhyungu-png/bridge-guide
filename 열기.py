# -*- coding: utf-8 -*-
"""웹 GUI를 연다. 필요하면 로컬 서버를 먼저 띄운다.

`/bridge-guide` 슬래시 커맨드가 이 스크립트를 부른다.

**왜 서버를 띄우나**: 파일을 그냥 열면(file://) 「질문하기」가 꺼진 채로 뜬다.
그 페이지에는 Claude로 가는 통로가 없기 때문이다. 로컬 서버를 거쳐 열면
터미널과 같은 엔진(`claude -p`)이 뒤에 붙어 질문이 된다. 그래서 기본은
서버다 - 파일로 여는 건 서버를 못 띄울 때의 대비책이다.

이미 서버가 떠 있으면 그걸 쓴다. 매번 새로 띄우지 않는다.

의존성 없음. 파이썬 3.10 이상이면 그대로 돈다.

사용:
    python 열기.py                  # 서버를 띄우고(또는 재사용) 연다
    python 열기.py 세굴              # 본문 검색 탭을 그 질의로 열고
    python 열기.py 표1.31            # 표처럼 보이면 표 조회 탭으로 연다
    python 열기.py --파일            # 서버 없이 파일로만 연다(오프라인)
"""
import json
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
HTML = ROOT / "webapp" / "bridge_guide.html"
SERVER = ROOT / "서버.py"

PORTS = [8765, 8766, 8767, 8768, 8769]
START_TIMEOUT = 20  # 초. 서버가 뜨기를 기다리는 한도

# "1.31", "표1.31", "표 1.31" 처럼 보이면 표 조회 탭으로 연다.
표번호 = re.compile(r"^표?\s*\d+\.\d+(?:의\d+)?$")


def tab_and_query(question: str):
    q = (question or "").strip()
    if not q:
        return None, None
    return ("anchor" if 표번호.match(q) else "search"), q


def with_query(base: str, question: str) -> str:
    tab, q = tab_and_query(question)
    if not q:
        return base
    sep = "&" if "?" in base else "?"
    return "%s%stab=%s&q=%s" % (base, sep, tab, quote(q))


def 서버_응답(port: int) -> bool:
    """이 포트에 우리 서버가 떠 있는가. 남의 서버를 우리 것으로 착각하면 안 된다."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/_engine" % port, timeout=1.5) as r:
            return json.loads(r.read().decode("utf-8")).get("engine") == "claude-cli"
    except (urllib.error.URLError, OSError, ValueError):
        return False


def 포트_비었나(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(1.0)
        return s.connect_ex(("127.0.0.1", port)) != 0


def 서버_띄우기(port: int) -> bool:
    """서버를 백그라운드로 띄우고 응답할 때까지 기다린다."""
    if not SERVER.exists():
        return False

    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
              "stdin": subprocess.DEVNULL, "cwd": str(ROOT)}
    if sys.platform == "win32":
        # 이 스크립트가 끝나도 서버는 살아 있어야 한다. 콘솔 창도 띄우지 않는다.
        kwargs["creationflags"] = (subprocess.CREATE_NO_WINDOW
                                   | subprocess.DETACHED_PROCESS)
    else:
        kwargs["start_new_session"] = True

    try:
        subprocess.Popen([sys.executable, str(SERVER),
                          "--port", str(port), "--no-open"], **kwargs)
    except OSError:
        return False

    마감 = time.time() + START_TIMEOUT
    while time.time() < 마감:
        if 서버_응답(port):
            return True
        time.sleep(0.4)
    return False


def 서버_주소() -> str | None:
    """쓸 수 있는 서버 주소. 떠 있으면 재사용하고, 없으면 띄운다."""
    for port in PORTS:
        if 서버_응답(port):
            return "http://127.0.0.1:%d/" % port
    for port in PORTS:
        if 포트_비었나(port) and 서버_띄우기(port):
            return "http://127.0.0.1:%d/" % port
    return None


def 파일로(question: str) -> int:
    if not HTML.exists():
        print("웹앱 파일이 없습니다: %s" % HTML, file=sys.stderr)
        print("먼저 만드세요: python build/20_아티팩트_데이터.py "
              "&& python build/21_웹앱_빌드.py", file=sys.stderr)
        return 1

    url = with_query(HTML.as_uri(), question)
    if not webbrowser.open(url):
        print("브라우저를 열지 못했습니다. 직접 여세요:", file=sys.stderr)
        print(url)
        return 1

    print("교량 지침서 가이드를 열었습니다. (파일 모드 — 「질문하기」는 꺼져 있습니다)")
    print(url)
    return 0


def main(argv) -> int:
    # 이 출력은 슬래시 커맨드를 통해 대화에 그대로 주입된다. 윈도우 콘솔
    # 기본 인코딩(cp949)으로 나가면 한글이 깨진 채로 모델에게 전달된다.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    파일모드 = "--파일" in argv or "--file" in argv
    question = " ".join(a for a in argv if not a.startswith("--"))

    if 파일모드:
        return 파일로(question)

    base = 서버_주소()
    if not base:
        print("로컬 서버를 띄우지 못해 파일로 엽니다.", file=sys.stderr)
        return 파일로(question)

    url = with_query(base, question)
    if not webbrowser.open(url):
        print("브라우저를 열지 못했습니다. 직접 여세요:", file=sys.stderr)
        print(url)
        return 1

    print("교량 지침서 가이드를 열었습니다. 「질문하기」에 그냥 물어보면 됩니다.")
    print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
