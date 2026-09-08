# -*- coding: utf-8 -*-
"""로컬 웹 서버 - 이미 쓰고 있는 AI를 웹 화면에 붙인다.

웹 화면에는 AI가 없으니 어디선가 빌려와야 한다. 이 서버는 **이 컴퓨터에 이미
있는 것**을 찾아 쓴다 - Claude Code든 Gemini CLI든 Codex CLI든, 아니면 API
키든(`bridgekb/engines.py`가 고른다). 그래서 특정 회사 도구에 매이지 않는다.

    브라우저 질문 → 이 서버 → engines.ask() → bridge-guide 도구 6개 → 답
                                              → 답에 인용된 PDF 쪽 그림

화면은 새로 만들지 않고 `webapp/bridge_guide.html`을 그대로 낸다. 어디서 열든
같은 화면이어야 하기 때문이다. 그 페이지는 `/_engine`을 찔러보고 이 서버가
붙어 있으면 질문을 `/ask`로 보낸다.

사용:
    python 서버.py                       # http://127.0.0.1:8765 를 열어준다
    python 서버.py --port 9000
    python 서버.py --no-open             # 브라우저를 자동으로 열지 않는다
    python 서버.py --engine gemini-cli   # 엔진을 직접 고른다
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from bridgekb import engines  # noqa: E402  (경로를 넣은 뒤라야 import된다)

HTML = ROOT / "webapp" / "bridge_guide.html"
PDF_DIR = ROOT / "data" / "원본pdf"
PAGE_IMG_DIR = ROOT / "data" / "출처페이지"
PDF_YEARS = {"2022", "2023", "2024", "2026"}
PAGE_IMG_RESOLUTION = 170

# --engine 으로 고정할 수 있다. 비우면 engines 가 우선순위대로 고른다.
ENGINE_NAME: str | None = None

# 서버가 요청마다 스레드를 새로 띄우는데(ThreadingHTTPServer), pdfplumber/pypdfium2
# 렌더링은 동시에 두 쪽을 그리면 서로 간섭해 한쪽이 빈 백지로 나올 수 있다(실제로
# 겪음 - 파일은 멀쩡한 PNG인데 내용이 통째로 비어 있었다). 그래서 렌더링 자체는
# 한 번에 하나씩만 하도록 잠근다. 캐시가 이미 있으면 잠글 필요 없다.
_RENDER_LOCK = threading.Lock()


def render_page_png(year: str, page: int) -> bytes | None:
    """PDF 전체를 열지 않고 그 한 쪽만 잘라 그림으로 낸다. 한 번 만들면 디스크에 캐시한다."""
    cache_path = PAGE_IMG_DIR / year / ("%d.png" % page)
    if cache_path.exists():
        return cache_path.read_bytes()

    pdf_path = PDF_DIR / (year + ".pdf")
    if not pdf_path.exists():
        return None

    import pdfplumber  # 무거운 의존성이라 실제로 쓸 때만 불러온다

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
    if answer.warning:
        # 도구를 못 썼다면 등급이 코드로 판정되지 않은 것이다 - 숨기면 안 된다.
        result["warning"] = answer.warning
    return result


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

    def do_GET(self):
        path = unquote(self.path.split("?", 1)[0])

        if path == "/_engine":
            picked = engines.pick(ENGINE_NAME)
            self._json(200, {
                "ok": picked is not None,
                "engine": picked.name if picked else None,
                "available": [e.name for e in engines.available()],
            })
            return

        # 임의 파일을 내주지 않는다. 이 서버가 아는 파일은 화면 하나와 표 출처 페이지 그림뿐이다.
        if path in ("/", "/index.html", "/bridge_guide.html"):
            if not HTML.exists():
                self._send(500, "웹앱 파일이 없습니다. python build/21_웹앱_빌드.py 를 먼저 도세요."
                           .encode("utf-8"), "text/plain; charset=utf-8")
                return
            self._send(200, HTML.read_bytes(), "text/html; charset=utf-8")
            return

        # 답 아래 "출처"에 원본 PDF를 통째로 열지 않고 그 한 쪽만 잘라 보여주려고 연다.
        # webapp/bridge_guide.html이 쓰는 상대경로(../data/출처페이지/2026/29.png)와
        # 똑같이 맞춰서, 서버로 열든 file://로 열든 같은 링크가 통하게 한다.
        if path.startswith("/data/출처페이지/"):
            parts = path.split("/")
            if len(parts) != 5 or not parts[4].endswith(".png"):
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            year = parts[3]
            page_no = parts[4][:-4]
            if year not in PDF_YEARS or not page_no.isdigit():
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
            assert isinstance(turns, list)
        except Exception:
            self._json(400, {"error": "요청 형식이 잘못됐습니다.", "code": "upstream_error"})
            return

        sys.stderr.write("질문: %s\n" % str(turns[-1].get("content", ""))[:80] if turns else "")
        result = ask_engine(turns)
        self._json(200, result)


def main(argv=None) -> int:
    global ENGINE_NAME

    ap = argparse.ArgumentParser(description="교량 지침서 가이드 로컬 서버")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="브라우저를 자동으로 열지 않는다")
    ap.add_argument("--engine", default=None,
                    help="쓸 엔진 이름. 생략하면 자동으로 고른다 (--engines 로 목록 확인)")
    ap.add_argument("--engines", action="store_true", help="쓸 수 있는 엔진을 보여주고 끝낸다")
    args = ap.parse_args(argv)

    if args.engines:
        found = engines.available()
        if not found:
            print("쓸 수 있는 엔진이 없습니다.")
            print("claude / gemini / codex 중 하나를 설치하거나,")
            print("ANTHROPIC_API_KEY · GEMINI_API_KEY · OPENAI_API_KEY 중 하나를 넣으세요.")
            return 1
        for i, e in enumerate(found):
            print("%s %-14s %-4s %s" % ("*" if i == 0 else " ", e.name, e.kind, e.detail))
        print("\n* 표시가 기본으로 골라지는 엔진입니다.")
        return 0

    ENGINE_NAME = args.engine

    if not HTML.exists():
        print("웹앱 파일이 없습니다: %s" % HTML, file=sys.stderr)
        print("먼저: python build/20_아티팩트_데이터.py && python build/21_웹앱_빌드.py",
              file=sys.stderr)
        return 1

    picked = engines.pick(ENGINE_NAME)
    if picked is None:
        print("경고: 쓸 수 있는 AI가 없어 「질문하기」가 꺼집니다.", file=sys.stderr)
        print("      python 서버.py --engines 로 무엇이 필요한지 확인하세요.", file=sys.stderr)
    else:
        print("엔진: %s (%s)" % (picked.name, picked.detail))

    url = "http://127.0.0.1:%d/" % args.port
    # 127.0.0.1에만 묶는다. 이 서버는 AI 명령을 실행하므로 밖에 열면 안 된다.
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)

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
