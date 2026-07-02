"""auto 모드: C/C++/커널 드라이버 C 함수 추출기 테스트."""

from __future__ import annotations

from pathlib import Path

from genut_service.services.c_function_parser import (
    FunctionSpan,
    extract_functions,
    extract_functions_from_file,
)


def _names(text: str) -> list[str]:
    return [span.name for span in extract_functions(text)]


def test_simple_c_functions_with_line_ranges() -> None:
    text = (
        "int first(void)\n"
        "{\n"
        "    return 1;\n"
        "}\n"
        "\n"
        "int second(int x) { return x; }\n"
    )
    spans = extract_functions(text)
    assert spans == [
        FunctionSpan(name="first", start_line=1, end_line=4),
        FunctionSpan(name="second", start_line=6, end_line=6),
    ]


def test_multiline_signature_start_line_is_name_line() -> None:
    text = (
        "static long\n"
        "compute_total(int a,\n"
        "              int b)\n"
        "{\n"
        "    return a + b;\n"
        "}\n"
    )
    spans = extract_functions(text)
    assert spans == [FunctionSpan(name="compute_total", start_line=2, end_line=6)]


def test_prototypes_and_function_pointers_are_not_functions() -> None:
    text = (
        "int declared(int x);\n"
        "typedef void (*callback_t)(int);\n"
        "int (*handler)(int) = 0;\n"
        "extern int external_fn(void);\n"
    )
    assert _names(text) == []


def test_comments_strings_and_preprocessor_are_masked() -> None:
    text = (
        "// int fake_line(void) {\n"
        "/* int fake_block(void) {\n"
        "   } */\n"
        "const char *snippet = \"int fake_str(void) { }\";\n"
        "char brace = '{';\n"
        "#define WRAP(x) \\\n"
        "    do_call(x)\n"
        "\n"
        "int real(void) { return 0; }\n"
    )
    assert _names(text) == ["real"]


def test_keywords_and_toplevel_braces_are_ignored() -> None:
    text = "for (;;) {}\nint ok(void) { return 1; }\n"
    assert _names(text) == ["ok"]


def test_struct_definition_and_initializer_are_skipped() -> None:
    text = (
        "struct point { int x; int y; };\n"
        "static struct point origin = { 0, 0 };\n"
        "enum color { RED, BLUE };\n"
        "int after(void) { return 0; }\n"
    )
    assert _names(text) == ["after"]


# ---------------------------------------------------------------------------
# 커널 디바이스 드라이버 C
# ---------------------------------------------------------------------------


def test_kernel_driver_source() -> None:
    text = (
        "#include <linux/module.h>\n"
        "#include <linux/init.h>\n"
        "\n"
        'MODULE_LICENSE("GPL");\n'
        "MODULE_DEVICE_TABLE(of, my_ids)\n"
        "\n"
        "static const struct file_operations my_fops = {\n"
        "    .owner = THIS_MODULE,\n"
        "    .open = my_open,\n"
        "};\n"
        "\n"
        "static irqreturn_t my_irq_handler(int irq, void *dev_id)\n"
        "{\n"
        "    return IRQ_HANDLED;\n"
        "}\n"
        "\n"
        "static int __init my_driver_init(void)\n"
        "{\n"
        "    return my_probe();\n"
        "}\n"
        "\n"
        "static void __exit my_driver_exit(void)\n"
        "{\n"
        "}\n"
        "\n"
        "module_init(my_driver_init);\n"
        "module_exit(my_driver_exit);\n"
    )
    # 매크로 호출(module_init 등)·구조체 초기화(.open = my_open)는 함수가 아니다.
    # __init/__exit 같은 이름 앞 수식이 있어도 함수명을 정확히 뽑는다.
    assert _names(text) == ["my_irq_handler", "my_driver_init", "my_driver_exit"]


def test_kernel_attribute_after_paren_and_sparse_annotations() -> None:
    text = (
        "static int helper(void) __attribute__((cold))\n"
        "{\n"
        "    return 0;\n"
        "}\n"
        "\n"
        "static void locked_op(struct s *p) __must_hold(&p->lock)\n"
        "{\n"
        "}\n"
    )
    assert _names(text) == ["helper", "locked_op"]


def test_macro_call_without_semicolon_does_not_swallow_next_function() -> None:
    # 세미콜론 없는 최상위 매크로 호출 뒤의 진짜 함수를 놓치지 않는다
    text = (
        "MODULE_DEVICE_TABLE(of, ids)\n"
        "static int probe_it(void)\n"
        "{\n"
        "    return 0;\n"
        "}\n"
    )
    assert _names(text) == ["probe_it"]


# ---------------------------------------------------------------------------
# C++
# ---------------------------------------------------------------------------


def test_cpp_namespace_and_extern_c_are_transparent() -> None:
    text = (
        "namespace outer {\n"
        "namespace inner {\n"
        "int add(int a, int b) {\n"
        "    return a + b;\n"
        "}\n"
        "}\n"
        "}\n"
        "\n"
        'extern "C" {\n'
        "int c_api(void) { return 1; }\n"
        "}\n"
    )
    assert _names(text) == ["add", "c_api"]


def test_cpp_class_member_definitions_and_ctor_initializer() -> None:
    text = (
        "class Widget {\n"
        "public:\n"
        "    int inline_method() { return 0; }\n"  # 한계: 클래스 본문 내부는 미검출
        "};\n"
        "\n"
        "Widget::Widget() : x_(1), y_(2) {\n"
        "}\n"
        "\n"
        "int Widget::value() const {\n"
        "    return x_;\n"
        "}\n"
    )
    # Class::method 정의는 method 이름으로 추출된다
    assert _names(text) == ["Widget", "value"]


def test_cpp_template_and_trailing_return_type() -> None:
    text = (
        "template <typename T>\n"
        "T max_of(T a, T b) {\n"
        "    return a > b ? a : b;\n"
        "}\n"
        "\n"
        "auto make_id(int seed) -> long {\n"
        "    return seed;\n"
        "}\n"
    )
    assert _names(text) == ["max_of", "make_id"]


# ---------------------------------------------------------------------------
# 견고성
# ---------------------------------------------------------------------------


def test_garbage_input_returns_without_exception() -> None:
    assert extract_functions("") == []
    assert extract_functions("{{{ ))) \"unterminated\n#if 0\n") == []
    assert extract_functions("\x00\x01 int f(void) { }") == [
        FunctionSpan(name="f", start_line=1, end_line=1)
    ]


def test_extract_functions_from_file(tmp_path: Path) -> None:
    src = tmp_path / "aaa.c"
    src.write_text(
        "int bbb(void) { return 1; }\nint ddd(int x)\n{\n    return x;\n}\n",
        encoding="utf-8",
    )
    spans = extract_functions_from_file(src)
    assert [s.name for s in spans] == ["bbb", "ddd"]
    assert spans[1].start_line == 2
    assert spans[1].end_line == 5
