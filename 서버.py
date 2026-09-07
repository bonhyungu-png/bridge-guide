# -*- coding: utf-8 -*-
"""로컬 웹 서버 - 터미널의 엔진을 웹 화면에 붙인다.

터미널에서 질문이 잘 되는 이유는 Claude Code 자신이 엔진이기 때문이다.
웹 화면에는 엔진이 없으니 어디선가 빌려와야 하는데, 길이 둘이다:

- Artifact = 보는 사람의 Claude를 빌린다 → claude.ai 뷰어 안에서만 켜진다
- 여기(`claude -p`) = **터미널의 그 엔진을 그대로 쓴다** → 어디서 열든 켜진다

이미 로그인된 구독을 그대로 쓰므로 API 키가 없고, 표준 라이브러리만 쓰므로
설치할 것도 없다.

    브라우저 질문 → 이 서버 → claude -p → bridge-guide MCP 도구 6개 → 답

화면은 새로 만들지 않고 `webapp/bridge_guide.html`을 그대로 낸다. 어디서 열든
같은 화면이어야 하기 때문이다. 그 페이지는 `/_engine`을 찔러보고 이 서버가
붙어 있으면 질문을 `/ask`로 보낸다.

사용:
    python 서버.py            # http://127.0.0.1:8765 를 열어준다
    python 서버.py --port 9000
    python 서버.py --no-open  # 브라우저를 자동으로 열지 않는다
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from bridgekb import tools  # noqa: E402  (경로를 넣은 뒤라야 import된다)

HTML = ROOT / "webapp" / "bridge_guide.html"

# 도구는 이것만 허용한다. 셸도 파일 쓰기도 주지 않는다 - 이 서버가 하는 일은
# 지침서를 읽어 답하는 것뿐이고, 질문은 브라우저에서 들어오는 입력이다.
ALLOWED_TOOLS = ["mcp__bridge-guide__" + spec["name"] for spec in tools.SPECS]

# SKILL.md의 0단계가 "무엇보다 먼저 GUI를 연다"고 시키는데, 여기서는 이미
# GUI 안이므로 그러면 답 대신 승인 요청만 돌아온다. 그 규칙을 여기서 끈다.
EXTRA_RULES = """
이 호출은 웹 화면에 표시할 텍스트 답을 만드는 것이다. 이미 GUI 안에서 물어본
것이므로 브라우저나 GUI를 열지 마라. 셸을 쓰지 말고 bridge-guide MCP 도구만
호출해 답하라. 도구를 아끼지 말고 필요한 만큼 부르되, 답은 화면에서 읽기 좋게
짧게 쓴다.
"""

TIMEOUT_SEC = 180


def claude_path() -> str | None:
    return shutil.which("claude")


def flatten(turns: list) -> str:
    """대화를 한 덩어리 프롬프트로 만든다. `claude -p`는 턴을 받지 않는다."""
    if not turns:
        return ""
    *before, last = turns
    lines = []
    if before:
        lines.append("이전 대화:")
        for t in before:
            who = "사용자" if t.get("role") == "user" else "도우미"
            lines.append("%s: %s" % (who, str(t.get("content") or "").strip()))
        lines.append("")
        lines.append("지금 질문:")
    lines.append(str(last.get("content") or "").strip())
    return "\n".join(lines)


def ask_claude(turns: list) -> dict:
    """`claude -p`를 돌려 답을 받는다. 반환은 페이지가 기대하는 모양이다."""
    exe = claude_path()
    if not exe:
        return {"error": "claude 명령을 찾지 못했습니다. Claude Code가 설치돼 있어야 합니다.",
                "code": "upstream_error"}

    prompt = flatten(turns)
    if not prompt.strip():
        return {"error": "질문이 비었습니다.", "code": "empty_completion"}

    cmd = [exe, "-p", prompt,
           "--output-format", "json",
           "--allowedTools", " ".join(ALLOWED_TOOLS),
           "--append-system-prompt", tools.SYSTEM_RULES + EXTRA_RULES]

    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return {"error": "답이 %d초 안에 오지 않았습니다." % TIMEOUT_SEC,
                "code": "upstream_error"}

    out = proc.stdout.decode("utf-8", "replace").strip()
    err = proc.stderr.decode("utf-8", "replace").strip()

    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        # JSON이 아니면 대개 한도·로그인 같은 평문 안내다. 그대로 전한다.
        message = out or err or "답을 받지 못했습니다."
        code = "rate_limited" if "limit" in message.lower() else "upstream_error"
        return {"error": message[:400], "code": code}

    if data.get("is_error"):
        return {"error": str(data.get("result") or "오류가 났습니다.")[:400],
                "code": "upstream_error"}

    text = str(data.get("result") or "").strip()
    if not text:
        return {"error": "빈 답이 돌아왔습니다.", "code": "empty_completion"}

    result = {"text": text}
    denials = data.get("permission_denials")
    if denials:
        # 도구가 막히면 등급을 코드가 판정하지 못한 채 답이 나온다 - 숨기면 안 된다.
        result["warning"] = "허용되지 않은 도구 호출이 %d건 있었습니다." % len(denials)
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
        path = self.path.split("?", 1)[0]

        if path == "/_engine":
            self._json(200, {"ok": bool(claude_path()), "engine": "claude-cli"})
            return

        # 임의 파일을 내주지 않는다. 이 서버가 아는 파일은 화면 하나뿐이다.
        if path in ("/", "/index.html", "/bridge_guide.html"):
            if not HTML.exists():
                self._send(500, "웹앱 파일이 없습니다. python build/21_웹앱_빌드.py 를 먼저 도세요."
                           .encode("utf-8"), "text/plain; charset=utf-8")
                return
            self._send(200, HTML.read_bytes(), "text/html; charset=utf-8")
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
        result = ask_claude(turns)
        self._json(200, result)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="교량 지침서 가이드 로컬 서버")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="브라우저를 자동으로 열지 않는다")
    args = ap.parse_args(argv)

    if not HTML.exists():
        print("웹앱 파일이 없습니다: %s" % HTML, file=sys.stderr)
        print("먼저: python build/20_아티팩트_데이터.py && python build/21_웹앱_빌드.py",
              file=sys.stderr)
        return 1
    if not claude_path():
        print("경고: claude 명령을 못 찾았습니다. 질문하기 탭이 꺼집니다.", file=sys.stderr)
        print("표 조회·등급 판정·본문 검색은 그대로 됩니다.", file=sys.stderr)

    url = "http://127.0.0.1:%d/" % args.port
    # 127.0.0.1에만 묶는다. 이 서버는 claude를 실행하므로 밖에 열면 안 된다.
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
