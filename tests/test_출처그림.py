# -*- coding: utf-8 -*-
"""출처 PDF 쪽 그림 - 없는 의존성 때문에 조용히 깨지지 않는지 지킨다.

pdfplumber 는 선택 의존성이다. README 도 "없으면 답은 그대로 나오고 그림만
안 뜬다"고 약속한다. 그런데 실제로는 ModuleNotFoundError 가 요청 처리 도중
그대로 튀어나와 **응답 없이 연결이 끊겼다**(RemoteDisconnected). 브라우저에는
깨진 그림만 보이고, 사용자는 무엇을 설치해야 하는지 알 방법이 없었다.
다른 컴퓨터에서 "그림만 안 뜬다"는 신고가 실제로 이것이었다.
"""
from __future__ import annotations

import builtins
import importlib.util

import pytest

from bridgekb import config

ROOT = config.ROOT


def _load_server():
    spec = importlib.util.spec_from_file_location("서버", ROOT / "서버.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def 서버():
    return _load_server()


@pytest.fixture
def pdfplumber_없음(monkeypatch):
    """pdfplumber 가 설치되지 않은 컴퓨터를 흉내 낸다."""
    real = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "pdfplumber":
            raise ModuleNotFoundError("No module named 'pdfplumber'")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)


def test_pdfplumber_없어도_요청이_죽지_않는다(서버, pdfplumber_없음, tmp_path):
    """예외가 튀어나가면 응답 없이 연결이 끊겨 원인을 알 수 없다."""
    서버.PAGE_IMG_DIR = tmp_path / "출처페이지"   # 캐시를 비워 실제 렌더 경로를 타게 한다

    result = 서버.render_page_png("2026", 29)

    assert result is None, "그림은 못 만들어도 None 으로 돌려줘야 한다"


def test_그림을_못_만드는_이유를_화면이_알_수_있다(서버, pdfplumber_없음):
    """왜 안 뜨는지 화면이 알려주려면 서버가 그 사실을 노출해야 한다."""
    assert 서버.pdf_images_available() is False


def test_pdfplumber_가_있으면_쓸_수_있다고_알린다(서버):
    pytest.importorskip("pdfplumber")
    assert 서버.pdf_images_available() is True
