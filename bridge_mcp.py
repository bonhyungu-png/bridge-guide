# -*- coding: utf-8 -*-
"""MCP 서버 진입점 - 어느 폴더에서 실행하든 돌아간다.

`서버.py`가 AI를 부를 때 `--mcp-config`로 이 파일의 절대경로를 물려 준다.
사용자가 직접 실행할 일은 없다.

의존성 없음. 파이썬 3.10 이상이면 그대로 돈다.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from bridgekb.mcp_server import serve  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(serve())
