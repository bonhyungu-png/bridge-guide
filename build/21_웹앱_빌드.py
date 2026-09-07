# -*- coding: utf-8 -*-
"""단일 파일 웹앱을 만든다 - webapp/템플릿.html + artifact_data.json → webapp/bridge_guide.html.

결과물은 완전 자체완결형이다. 인터넷도, 파이썬도, 서버도 필요 없다 - 브라우저로
파일을 열기만 하면 된다(file:// 프로토콜도 지원). /bridge-guide 커맨드가 이 파일을
기본 브라우저로 연다.

사용:
    python build/20_아티팩트_데이터.py   # 데이터 번들 먼저 최신화
    python build/21_웹앱_빌드.py         # 그다음 웹앱 조립
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "webapp" / "템플릿.html"
DATA = ROOT / "build" / "artifact_data.json"
OUT = ROOT / "webapp" / "bridge_guide.html"

MARKER = "/*__BRIDGE_DATA__*/{}"


def main():
    template = TEMPLATE.read_text(encoding="utf-8")
    data_json = DATA.read_text(encoding="utf-8")
    # </script> 문자열이 데이터 안에 우연히 있으면 스크립트 태그가 조기 종료되니 이스케이프한다.
    data_json_safe = data_json.replace("</script", "<\\/script")

    if MARKER not in template:
        raise SystemExit(f"플레이스홀더를 템플릿에서 못 찾음: {MARKER!r}")

    final = template.replace(MARKER, data_json_safe)
    OUT.write_text(final, encoding="utf-8")
    print(f"저장: {OUT}  ({OUT.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
