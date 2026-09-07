# -*- coding: utf-8 -*-
"""Artifact(claude.ai)에 올릴 파일을 만든다 - webapp/bridge_guide.html에서 파생.

왜 따로 만드나: Artifact는 올린 내용을 <!doctype>...<head>...<body>로 감싸준다.
그래서 문서 골격을 우리가 넣으면 안 된다. 로컬 파일로 여는 쪽은 <meta charset>이
필요하고, Artifact 쪽은 그게 중복이라 그 한 줄만 걷어낸다.

내용이 같아야 하는 게 핵심이다 - 브라우저로 열든 링크로 열든 같은 화면,
같은 답이어야 한다. 그래서 새로 쓰지 않고 빌드된 웹앱에서 파생시킨다.

Artifact에서만 「질문하기」 탭이 살아난다. 그쪽에는 페이지가 Claude에게 물을
통로(sample capability)가 있고 file://에는 없기 때문이다.

사용:
    python build/20_아티팩트_데이터.py
    python build/21_웹앱_빌드.py
    python build/22_아티팩트_빌드.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "webapp" / "bridge_guide.html"
OUT = ROOT / "webapp" / "bridge_guide.artifact.html"

DROP = '<meta charset="utf-8">'


def main():
    if not SRC.exists():
        raise SystemExit("먼저 만드세요: python build/21_웹앱_빌드.py")

    html = SRC.read_text(encoding="utf-8")
    first, sep, rest = html.partition("\n")
    if first.strip() != DROP:
        raise SystemExit(f"첫 줄이 예상과 다릅니다: {first[:80]!r}")

    OUT.write_text(rest, encoding="utf-8")
    print(f"저장: {OUT}  ({OUT.stat().st_size / 1e6:.2f} MB)")
    print(f"첫 줄: {rest.partition(chr(10))[0][:60]}")


if __name__ == "__main__":
    main()
