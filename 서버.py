# -*- coding: utf-8 -*-
"""교량 지침서 가이드 - 질문을 받고 답하는 유일한 곳.

    브라우저 질문 → 이 서버 → engines.ask() → bridge-guide 도구 6개 → 답
                                            → 답에 인용된 PDF 쪽 그림

질문은 웹 화면에서만 받는다. 예전에는 터미널·MCP·플러그인으로도 답할 수
있었는데, 창마다 도구가 붙었는지 안 붙었는지가 달라서 **같은 질문에 다른 답**이
나왔다. 답하는 자리를 하나로 모으면 그 종류의 어긋남이 아예 생기지 않는다.

AI는 이 컴퓨터에 이미 있는 것을 빌려 쓴다(`bridgekb/engines.py`) - Claude Code
구독이 있으면 그것을, 없으면 API 키를. 도구는 어느 쪽이든 우리가 직접 물려
주므로 사용자가 따로 등록할 것이 없다.

사용:
    python 서버.py                       # 열고 브라우저를 띄운다
    python 서버.py --launch              # 뒤에서 띄우고 화면만 열고 끝낸다
                                        #   (/bridge-guide 커맨드가 쓰는 길)
    python 서버.py --port 9000
    python 서버.py --no-open             # 브라우저를 자동으로 열지 않는다
    python 서버.py --engine anthropic-api # 엔진을 직접 고른다
    python 서버.py --engines             # 쓸 수 있는 AI 목록
    python 서버.py --doctor              # 지식베이스·엔진 상태 점검
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from bridgekb import config, engines  # noqa: E402  (경로를 넣은 뒤라야 import된다)

HTML = ROOT / "webapp" / "bridge_guide.html"
PDF_DIR = ROOT / "data" / "원본pdf"
PAGE_IMG_DIR = ROOT / "data" / "출처페이지"
PAGE_IMG_RESOLUTION = 170

PORTS = [8765, 8766, 8767, 8768, 8769]

# --engine 으로 고정할 수 있다. 비우면 engines 가 우선순위대로 고른다.
ENGINE_NAME: str | None = None
PORT = PORTS[0]

# 이 서버는 AI를 실제로 실행시킨다. 그래서 127.0.0.1에만 묶고, 그 위에서 다시
# 요청이 우리 화면에서 온 것인지 확인한다 - 사용자가 서버를 켜 둔 채 아무
# 웹사이트나 방문하면 그 페이지가 이 주소로 POST를 쏠 수 있기 때문이다.
# 브라우저는 이런 사용자 정의 헤더를 교차 출처에서 프리플라이트 없이 붙이지
# 못하고, 우리는 프리플라이트에 답하지 않으므로 그 시점에서 막힌다.
GUARD_HEADER = "X-Bridge-Guide"

_RENDER_LOCK = threading.Lock()


def pdf_images_available() -> bool:
    """출처 그림을 만들 수 있는가.

    pdfplumber 는 선택 의존성이라 없을 수 있다. 없다는 사실을 **화면과 터미널이
    알 수 있어야** 한다 - 예전에는 조용히 요청이 죽어서, 다른 컴퓨터에서
    "그림만 안 뜬다"는 것 말고는 아무 단서가 없었다.
    """
    try:
        import pdfplumber  # noqa: F401
    except ImportError:
        return False
    return True


def render_page_png(year: str, page: int) -> bytes | None:
    """PDF 전체를 열지 않고 그 한 쪽만 잘라 그림으로 낸다. 한 번 만들면 디스크에 캐시한다."""
    cache_path = PAGE_IMG_DIR / year / ("%d.png" % page)
    if cache_path.exists():
        return cache_path.read_bytes()

    pdf_path = PDF_DIR / (year + ".pdf")
    if not pdf_path.exists():
        return None

    try:
        import pdfplumber  # 무거운 의존성이라 실제로 쓸 때만 불러온다
    except ImportError:
        # 여기서 예외가 튀어나가면 응답 없이 연결이 끊겨(RemoteDisconnected)
        # 브라우저에는 깨진 그림만 남는다. 답은 그대로 나와야 한다.
        return None

    with _RENDER_LOCK:
        if cache_path.exists():   # 잠그는 동안 다른 요청이 이미 만들어 놨을 수 있다
            return cache_path.read_bytes()
        with pdfplumber.open(pdf_path) as pdf:
            if not (1 <= page <= len(pdf.pages)):
                return None
            # antialias 기본값(False)으로 그리면 한글 획이 가늘어서 일부 글자가
            # 깨지거나 사라진다(예: "해설"이 "해실"처럼 보임) - 켜야 제대로 나온다.
            image = pdf.pages[page - 1].to_image(resolution=PAGE_IMG_RESOLUTION, antialias=True)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            # 다 그리기 전에 다른 요청이 읽어가지 않도록, 임시 이름으로 쓰고 나서
            # 한 번에 실제 이름으로 바꾼다(원자적 교체).
            tmp_path = cache_path.with_suffix(".tmp-%d" % threading.get_ident())
            image.save(str(tmp_path))
            tmp_path.replace(cache_path)
    return cache_path.read_bytes()


def ask_engine(turns: list) -> dict:
    """골라진 엔진에 물어보고, 화면이 기대하는 모양으로 돌려준다."""
    try:
        answer = engines.ask(turns, ENGINE_NAME)
    except engines.EngineError as exc:
        return {"error": exc.message, "code": exc.code}

    result = {"text": answer.text, "engine": answer.engine}
    if answer.sources:
        result["sources"] = answer.sources
    if answer.tools_used:
        result["tools"] = answer.tools_used
    if answer.warning:
        # 도구를 못 썼다면 등급이 코드로 판정되지 않은 것이다 - 숨기면 안 된다.
        result["warning"] = answer.warning
    return result


def _local_host(value: str | None) -> bool:
    """호스트가 이 컴퓨터를 가리키는가. DNS 리바인딩을 막는다."""
    if not value:
        return False
    host = value.rsplit(":", 1)[0].strip("[]")
    return host in ("127.0.0.1", "localhost", "::1")


class Handler(BaseHTTPRequestHandler):
    server_version = "bridge-guide"

    def log_message(self, fmt, *args):  # 기본 로그는 시끄럽다
        sys.stderr.write("  %s\n" % (fmt % args))

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _from_our_page(self) -> bool:
        """이 요청이 우리 화면에서 온 것인가."""
        if not _local_host(self.headers.get("Host")):
            return False
        if self.headers.get(GUARD_HEADER) != "1":
            return False
        origin = self.headers.get("Origin")
        if origin and not _local_host(urlparse(origin).netloc):
            return False
        return True

    def do_GET(self):
        path = unquote(self.path.split("?", 1)[0])

        if path == "/_engine":
            picked = engines.pick(ENGINE_NAME)
            self._json(200, {
                "ok": picked is not None,
                "engine": picked.name if picked else None,
                "available": [e.name for e in engines.available()],
                "pdf_images": pdf_images_available() and PDF_DIR.is_dir(),
            })
            return

        # 임의 파일을 내주지 않는다. 이 서버가 아는 파일은 화면 하나와 출처 페이지 그림뿐이다.
        if path in ("/", "/index.html", "/bridge_guide.html"):
            if not HTML.exists():
                self._send(500, ("웹 화면 파일이 없습니다: %s" % HTML).encode("utf-8"),
                           "text/plain; charset=utf-8")
                return
            self._send(200, HTML.read_bytes(), "text/html; charset=utf-8")
            return

        # 답 아래 "출처"에 원본 PDF를 통째로 열지 않고 그 한 쪽만 잘라 보여준다.
        if path.startswith("/data/출처페이지/"):
            parts = path.split("/")
            if len(parts) != 5 or not parts[4].endswith(".png"):
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            year, page_no = parts[3], parts[4][:-4]
            if year not in set(config.available_years()) or not page_no.isdigit():
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            png = render_page_png(year, int(page_no))
            if png is None:
                self._send(404, b"page not found", "text/plain; charset=utf-8")
                return
            self._send(200, png, "image/png")
            return

        self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/ask":
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return

        if not self._from_our_page():
            # 다른 웹사이트가 이 주소로 질문을 밀어 넣어 사용자의 AI를 돌리는 것을 막는다.
            self._json(403, {"error": "이 화면에서 보낸 요청이 아닙니다.",
                             "code": "forbidden"})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > 200_000:
            self._json(400, {"error": "요청이 비었거나 너무 큽니다.", "code": "prompt_too_large"})
            return

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            turns = payload["turns"]
            assert isinstance(turns, list) and turns
        except Exception:
            self._json(400, {"error": "요청 형식이 잘못됐습니다.", "code": "upstream_error"})
            return

        sys.stderr.write("질문: %s\n" % str(turns[-1].get("content", ""))[:80])
        self._json(200, ask_engine(turns))


# ---------------------------------------------------------------- 점검

def doctor() -> int:
    """지식베이스와 엔진이 준비됐는지 본다."""
    years = config.available_years()
    print("정본 데이터 : %s" % config.TABLE_DIR)
    print("  판본      : %s" % (", ".join(years) if years else "없음 ← 데이터가 빠졌습니다"))
    for y in years:
        p = config.rules_path_for(y)
        print("  %s 판정규칙: %s" % (y, "있음" if p.exists() else "없음 ← " + str(p)))
    print("웹 화면     : %s" % ("있음" if HTML.exists() else "없음 ← " + str(HTML)))
    print("원본 PDF    : %s" % ("있음" if PDF_DIR.exists() else "없음"))
    if pdf_images_available():
        print("출처 그림   : 됩니다")
    else:
        print("출처 그림   : 안 됩니다 ← pip install pdfplumber (답은 그대로 나옵니다)")

    found = engines.available()
    if found:
        print("답할 AI     : %s (기본: %s)" % (", ".join(e.name for e in found), found[0].name))
    else:
        print("답할 AI     : 없음 ← Claude Code를 설치해 로그인하거나 API 키를 넣으세요")

    ok = bool(years) and HTML.exists() and bool(found)
    print("\n%s" % ("준비됐습니다." if ok else "위의 '없음' 항목을 먼저 채우세요."))
    return 0 if ok else 1


def _running_here(port: int) -> bool:
    """이 포트에 우리 서버가 떠 있는가."""
    try:
        req = urllib.request.Request("http://127.0.0.1:%d/_engine" % port)
        with urllib.request.urlopen(req, timeout=1.5) as r:
            json.loads(r.read().decode("utf-8"))
            return r.headers.get("Server", "").startswith("bridge-guide")
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _free(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(1.0)
        return s.connect_ex(("127.0.0.1", port)) != 0


def _spawn_detached(port: int) -> bool:
    """서버를 뒤에서 띄우고, 응답할 때까지 기다린다.

    슬래시 커맨드(`/bridge-guide`)는 명령이 끝나야 대화가 이어진다. 그런데
    serve_forever()는 끝나지 않으므로, 화면을 여는 쪽과 서버를 도는 쪽을
    분리한다 - 띄운 뒤 이 프로세스는 빠진다.
    """
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
              "stdin": subprocess.DEVNULL, "cwd": str(ROOT)}
    if sys.platform == "win32":
        # 이 프로세스가 끝나도 서버는 살아 있어야 한다. 콘솔 창도 띄우지 않는다.
        kwargs["creationflags"] = (subprocess.CREATE_NO_WINDOW
                                   | subprocess.DETACHED_PROCESS)
    else:
        kwargs["start_new_session"] = True

    cmd = [sys.executable, str(Path(__file__).resolve()),
           "--port", str(port), "--no-open"]
    if ENGINE_NAME:
        cmd += ["--engine", ENGINE_NAME]
    try:
        subprocess.Popen(cmd, **kwargs)
    except OSError:
        return False

    deadline = time.time() + 20
    while time.time() < deadline:
        if _running_here(port):
            return True
        time.sleep(0.4)
    return False


def launch(question: str) -> int:
    """화면을 연다. 서버가 없으면 뒤에서 띄운다. 슬래시 커맨드가 쓰는 길이다."""
    base = None
    for port in PORTS:
        if _running_here(port):
            base = "http://127.0.0.1:%d/" % port
            break
    if base is None:
        for port in PORTS:
            if _free(port) and _spawn_detached(port):
                base = "http://127.0.0.1:%d/" % port
                break
    if base is None:
        print("서버를 띄우지 못했습니다. 이 폴더에서 python 서버.py 를 직접 실행해 보세요.",
              file=sys.stderr)
        return 1

    url = base + ("?q=" + quote(question) if question.strip() else "")
    if not webbrowser.open(url):
        print("브라우저를 열지 못했습니다. 직접 여세요:", file=sys.stderr)
        print(url)
        return 1
    print("교량 지침서 가이드를 열었습니다. 화면에 그냥 물어보면 됩니다.")
    print(url)
    return 0


def main(argv=None) -> int:
    global ENGINE_NAME, PORT

    ap = argparse.ArgumentParser(description="교량 지침서 가이드")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--no-open", action="store_true", help="브라우저를 자동으로 열지 않는다")
    ap.add_argument("--engine", default=None,
                    help="쓸 엔진 이름. 생략하면 자동으로 고른다 (--engines 로 목록 확인)")
    ap.add_argument("--engines", action="store_true", help="쓸 수 있는 AI를 보여주고 끝낸다")
    ap.add_argument("--doctor", action="store_true", help="지식베이스·엔진 상태 점검")
    ap.add_argument("--launch", action="store_true",
                    help="화면만 열고 끝낸다(서버가 없으면 뒤에서 띄운다). 슬래시 커맨드용")
    ap.add_argument("question", nargs="*", help="열면서 바로 물어볼 질문(선택)")
    args = ap.parse_args(argv)

    if args.doctor:
        return doctor()

    if args.launch:
        ENGINE_NAME = args.engine
        return launch(" ".join(args.question))

    if args.engines:
        found = engines.available()
        if not found:
            print("쓸 수 있는 엔진이 없습니다.")
            print("Claude Code를 설치해 로그인하거나,")
            print("ANTHROPIC_API_KEY · GEMINI_API_KEY · OPENAI_API_KEY 중 하나를 넣으세요.")
            return 1
        for i, e in enumerate(found):
            print("%s %-14s %-4s %s" % ("*" if i == 0 else " ", e.name, e.kind, e.detail))
        print("\n* 표시가 기본으로 골라지는 엔진입니다.")
        return 0

    ENGINE_NAME = args.engine

    if not HTML.exists():
        print("웹 화면 파일이 없습니다: %s" % HTML, file=sys.stderr)
        return 1

    # 이미 떠 있으면 새로 띄우지 않고 그 화면을 연다.
    for port in ([args.port] if args.port else PORTS):
        if _running_here(port):
            url = "http://127.0.0.1:%d/" % port
            print("이미 켜져 있습니다: %s" % url)
            if not args.no_open:
                webbrowser.open(url)
            return 0

    candidates = [args.port] if args.port else PORTS
    httpd = None
    for port in candidates:
        if not _free(port):
            continue
        try:
            # 127.0.0.1에만 묶는다. 이 서버는 AI를 실행하므로 밖에 열면 안 된다.
            httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            PORT = port
            break
        except OSError:
            continue
    if httpd is None:
        print("포트를 찾지 못했습니다: %s" % candidates, file=sys.stderr)
        return 1

    picked = engines.pick(ENGINE_NAME)
    if picked is None:
        print("경고: 쓸 수 있는 AI가 없어 「질문하기」가 꺼집니다.", file=sys.stderr)
        print("      python 서버.py --engines 로 무엇이 필요한지 확인하세요.", file=sys.stderr)
    else:
        print("엔진: %s (%s)" % (picked.name, picked.detail))

    if not pdf_images_available():
        print("참고: pdfplumber 가 없어 답 아래 출처 그림이 뜨지 않습니다. "
              "pip install pdfplumber", file=sys.stderr)

    url = "http://127.0.0.1:%d/" % PORT
    print("교량 지침서 가이드: %s" % url)
    print("멈추려면 Ctrl+C")
    if not args.no_open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n멈췄습니다.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
