from pathlib import Path

from harness_eng.tools import TOOL_SCHEMAS, ToolContext, build_tool_list, dispatch


def _ctx(path: str = "product_01.html") -> ToolContext:
    return ToolContext(html_path=Path(path))


def test_read_html_returns_content():
    out = dispatch("read_html", _ctx())
    assert "Espresso Machine XR-7" in out


def test_css_select_hits_title():
    out = dispatch("css_select", _ctx(), selector="h1.title")
    assert out.startswith("Espresso Machine XR-7")


def test_css_select_no_match_sentinel():
    out = dispatch("css_select", _ctx(), selector=".does-not-exist")
    assert out == "NO_MATCH"


def test_extract_text_trims_tags():
    out = dispatch("extract_text", _ctx())
    assert "<html>" not in out
    assert "Espresso Machine XR-7" in out


def test_build_tool_list_subset():
    tools = build_tool_list(["css_select", "submit_answer"])
    names = [t["name"] for t in tools]
    assert names == ["css_select", "submit_answer"]


def test_submit_answer_schema_accepts_both_payloads():
    """submit_answer's schema overloads: fields for HTML tasks, code for code-gen."""
    schema = TOOL_SCHEMAS["submit_answer"]
    props = schema["input_schema"]["properties"]
    assert "fields" in props
    assert "code" in props
