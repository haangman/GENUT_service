"""C/C++/커널 드라이버 C 소스에서 함수 정의를 best-effort로 추출한다.

auto 모드가 (1) 누락 테스트 스캔에서 "파일에 어떤 함수가 있는지", (2) 변경 감지에서
"변경 라인이 어느 함수에 속하는지"를 판정하는 데 쓴다. 컴파일러가 아니므로 정확성은
best-effort이며, 어떤 입력에도 예외 없이 부분 결과를 반환한다.

지원 범위:
- C: 일반/static 함수, 여러 줄 시그니처.
- 커널 드라이버 C: `static int __init foo_init(void)`처럼 이름 앞 매크로 수식,
  `) __attribute__((...))`·`asm(...)` 등 닫는 괄호 뒤 수식, `module_init(x);` 같은
  최상위 매크로 호출(비매치), `= { .open = my_open }` 구조체 초기화(비매치).
- C++: `namespace X {`/`extern "C" {` 블록 내부(투명 처리), `T Class::method(...)`
  정의(이름=method), template 함수, 생성자 초기화 리스트(`: x_(1)`).

알려진 한계(비검출 또는 오검출 가능):
- K&R 스타일 정의(`int f(a) int a; { }`).
- 매크로가 만들어내는 함수(`SYSCALL_DEFINE3(open, ...)` → 매크로명으로 검출됨).
- operator 오버로드, 클래스/구조체 본문 안의 인라인 멤버 함수.
- `#if/#else` 분기의 중괄호가 불균형이면 그 이후 함수를 놓칠 수 있다
  (전처리기 라인은 통째로 마스킹된다).
- C++ raw string literal(`R"(...)"`).
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

# 함수명이 될 수 없는 식별자(제어문/연산자류). 본문은 통째로 건너뛰므로 실제로
# 등장할 일은 드물지만, 매크로로 뒤틀린 최상위 코드에 대한 안전망이다.
_KEYWORDS = frozenset(
    {
        "if", "for", "while", "switch", "return", "sizeof", "do", "else", "case",
        "defined", "alignof", "_Alignof", "typeof", "__typeof__", "decltype",
        "static_assert", "_Static_assert", "asm", "__asm__", "catch", "goto",
    }
)

# `)`와 `{` 사이에서 "괄호 그룹을 동반해도 되는" 수식 토큰.
# 그 외 식별자가 `(`를 동반하면 현재 후보를 버리고 그 식별자를 새 후보로 삼는다
# (세미콜론 없는 최상위 매크로 호출 뒤에 오는 진짜 함수를 놓치지 않기 위함).
_POST_PAREN_TOKENS = frozenset(
    {
        "__attribute__", "__declspec", "asm", "__asm__", "throw", "noexcept",
        # 커널 sparse 주석류
        "__acquires", "__releases", "__must_hold",
    }
)

_IDENT_RE = re.compile(r"[A-Za-z_]\w*")
_TRANSPARENT_RE = re.compile(
    # namespace X { / inline namespace { / extern "C" { (문자열 내용은 마스킹되지만
    # 따옴표 문자는 보존되므로 extern 뒤 "..."가 그대로 매칭된다)
    r"^(?:(?:inline\s+)?namespace(?:\s+[A-Za-z_][\w:]*)?|extern\s*\"[^\"]*\")$"
)


@dataclass(frozen=True)
class FunctionSpan:
    """함수 정의 1개: 이름과 소스 라인 범위(1-based, 양끝 포함)."""

    name: str
    start_line: int  # 시그니처 시작 줄(여러 줄 시그니처면 반환형/수식어 줄 포함)
    end_line: int    # 본문을 닫는 `}` 줄


def _mask(text: str) -> str:
    """주석/문자열 내용/전처리기 라인을 공백으로 치환한다(개행·길이 보존).

    문자열과 문자 리터럴은 따옴표 문자만 남기고 내용을 지운다 → `extern "C"` 인식과
    가짜 시그니처("int f() {") 제거를 동시에 만족한다.
    """
    out = list(text)
    n = len(text)
    i = 0
    line_start = True  # 현재 위치가 (공백만 지나온) 행 선두인지 — 전처리기 판정용

    def blank(idx: int) -> None:
        if out[idx] != "\n":
            out[idx] = " "

    while i < n:
        ch = text[i]
        if ch == "\n":
            line_start = True
            i += 1
            continue
        if line_start and ch in " \t":
            i += 1
            continue

        if ch == "#" and line_start:
            # 전처리기: 행 끝까지(말미 `\` 연속행 포함) 마스킹
            while i < n:
                if text[i] == "\n":
                    # 직전 비공백이 `\`면 다음 행도 이어서 마스킹
                    j = i - 1
                    while j >= 0 and text[j] in " \t":
                        j -= 1
                    if j >= 0 and text[j] == "\\":
                        i += 1
                        continue
                    break
                blank(i)
                i += 1
            line_start = True
            i += 1
            continue

        line_start = False

        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                blank(i)
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            blank(i)
            blank(i + 1)
            i += 2
            while i < n and not (text[i] == "*" and i + 1 < n and text[i + 1] == "/"):
                blank(i)
                i += 1
            if i < n:
                blank(i)
                blank(i + 1)
                i += 2
            continue
        if ch in "\"'":
            quote = ch
            i += 1  # 여는 따옴표는 보존
            while i < n and text[i] != quote:
                if text[i] == "\\" and i + 1 < n:
                    blank(i)
                    blank(i + 1)
                    i += 2
                    continue
                if text[i] == "\n":
                    break  # 닫히지 않은 리터럴 — 행 경계에서 중단(관용)
                blank(i)
                i += 1
            i += 1  # 닫는 따옴표(있다면)는 보존
            continue
        i += 1

    return "".join(out)


def _skip_ws(masked: str, i: int) -> int:
    n = len(masked)
    while i < n and masked[i] in " \t\n\r":
        i += 1
    return i


def _skip_balanced(masked: str, i: int, open_ch: str, close_ch: str) -> int:
    """masked[i]가 open_ch일 때 대응 close_ch 다음 인덱스를 반환. 불균형이면 len."""
    depth = 0
    n = len(masked)
    while i < n:
        ch = masked[i]
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def extract_functions(text: str) -> list[FunctionSpan]:
    """소스 텍스트에서 함수 정의 목록을 추출한다. 실패해도 예외 없이 부분 결과."""
    masked = _mask(text)
    n = len(masked)

    # 인덱스 → 라인 번호(1-based) 변환용 라인 시작 오프셋
    line_starts = [0]
    for idx, ch in enumerate(masked):
        if ch == "\n":
            line_starts.append(idx + 1)

    def line_of(idx: int) -> int:
        return bisect_right(line_starts, idx)

    spans: list[FunctionSpan] = []
    i = 0
    seg_start = 0  # 현재 문장 세그먼트 시작(직전 ; { } 이후) — `{` 분류용

    while i < n:
        ch = masked[i]

        if ch in ";}":
            seg_start = i + 1
            i += 1
            continue

        if ch == "{":
            segment = masked[seg_start:i].strip()
            if _TRANSPARENT_RE.match(segment):
                # namespace/extern "C" 블록: 내부도 최상위처럼 계속 스캔한다.
                # (닫는 `}`는 위의 ';}' 분기에서 세그먼트만 리셋하고 지나간다)
                seg_start = i + 1
                i += 1
                continue
            # 그 외(구조체/enum/초기화 리스트 등)는 통째로 건너뛴다
            i = _skip_balanced(masked, i, "{", "}")
            seg_start = i
            continue

        if ch.isalpha() or ch == "_":
            match = _IDENT_RE.match(masked, i)
            assert match is not None
            name = match.group(0)
            after = _skip_ws(masked, match.end())
            if after >= n or masked[after] != "(" or name in _KEYWORDS:
                i = match.end()
                continue

            # 후보: `이름 (` — 파라미터 괄호를 닫고 `{`까지 수식 토큰을 허용한다
            close = _skip_balanced(masked, after, "(", ")")
            j = close
            accepted = False
            rejected_at: int | None = None
            in_ctor_init = False
            while j < n:
                j = _skip_ws(masked, j)
                if j >= n:
                    break
                c = masked[j]
                if c == "{":
                    accepted = True
                    break
                if c in ";=,":
                    if c == "," and in_ctor_init:
                        j += 1
                        continue
                    # `;`는 메인 루프가 다시 처리해 세그먼트 경계를 리셋하도록
                    # 그 자리에서 멈춘다(건너뛰면 뒤따르는 namespace/extern "C"
                    # 블록이 불투명으로 오판돼 내부 함수를 전부 놓친다).
                    rejected_at = j
                    break
                if c == ":":
                    # `Foo::Foo() : x_(1), y_(2) {` 생성자 초기화 리스트
                    in_ctor_init = True
                    j += 1
                    continue
                if c == "-" and j + 1 < n and masked[j + 1] == ">":
                    j += 2  # C++ 후행 반환형 `-> T`
                    continue
                if c.isalpha() or c == "_":
                    tok = _IDENT_RE.match(masked, j)
                    assert tok is not None
                    tok_end = _skip_ws(masked, tok.end())
                    if tok_end < n and masked[tok_end] == "(":
                        if tok.group(0) in _POST_PAREN_TOKENS or in_ctor_init:
                            j = _skip_balanced(masked, tok_end, "(", ")")
                            continue
                        # 알 수 없는 `식별자(` — 현재 후보를 버리고 이 식별자부터 재스캔
                        # (세미콜론 없는 매크로 호출 뒤의 진짜 함수를 살린다)
                        rejected_at = tok.start()
                        break
                    j = tok.end()
                    continue
                # 그 외 문자(*, & 등) — 정의 시그니처로 보기 어렵다.
                # `}`는 메인 루프가 세그먼트 리셋을 하도록 그 자리에서 멈춘다.
                rejected_at = j if c == "}" else j + 1
                break

            if accepted:
                body_end = _skip_balanced(masked, j, "{", "}")
                # start_line은 시그니처의 시작(문장 세그먼트의 첫 유의미 문자) —
                # 여러 줄 시그니처에서 반환형/수식어 라인의 변경도 함수에 귀속시킨다.
                sig_start = _skip_ws(masked, max(seg_start, 0))
                if sig_start >= match.start():
                    sig_start = match.start()
                spans.append(
                    FunctionSpan(
                        name=name,
                        start_line=line_of(sig_start),
                        end_line=line_of(min(body_end - 1, n - 1)) if n else 1,
                    )
                )
                i = body_end
                seg_start = i
                continue
            i = rejected_at if rejected_at is not None else close
            continue

        i += 1

    return spans


def extract_functions_from_file(path: Path) -> list[FunctionSpan]:
    """파일을 읽어 extract_functions를 적용한다. 읽기 실패(OSError)는 전파한다."""
    text = path.read_text(encoding="utf-8", errors="replace")
    return extract_functions(text)
