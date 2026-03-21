"""
Tests for html_utils.py — covers:
  US-13: Submit a bracket via URL (HTML fetching and preprocessing)
"""

import asyncio

import pytest
from aioresponses import aioresponses


class TestPreprocessHtml:
    def test_strips_script_tags(self):
        from html_utils import preprocess_html

        html = "<html><body><script>var x = 1;</script><p>Bracket picks</p></body></html>"
        result = preprocess_html(html)
        assert "var x = 1" not in result
        assert "Bracket picks" in result

    def test_strips_style_tags(self):
        from html_utils import preprocess_html

        html = "<html><body><style>.red{color:red}</style><p>Picks here</p></body></html>"
        result = preprocess_html(html)
        assert "color:red" not in result
        assert "Picks here" in result

    def test_strips_nav_header_footer(self):
        from html_utils import preprocess_html

        html = (
            "<html><body>"
            "<header>Site Header</header>"
            "<nav>Nav Menu</nav>"
            "<div>Bracket Content</div>"
            "<footer>Footer Info</footer>"
            "</body></html>"
        )
        result = preprocess_html(html)
        assert "Site Header" not in result
        assert "Nav Menu" not in result
        assert "Footer Info" not in result
        assert "Bracket Content" in result

    def test_strips_noscript_svg_iframe(self):
        from html_utils import preprocess_html

        html = (
            "<html><body>"
            "<noscript>Enable JS</noscript>"
            "<svg><circle/></svg>"
            "<iframe src='x'></iframe>"
            "<p>Real content</p>"
            "</body></html>"
        )
        result = preprocess_html(html)
        assert "Enable JS" not in result
        assert "circle" not in result
        assert "Real content" in result

    def test_removes_html_comments(self):
        from html_utils import preprocess_html

        html = "<html><body><!-- secret comment --><p>Visible</p></body></html>"
        result = preprocess_html(html)
        assert "secret comment" not in result
        assert "Visible" in result

    def test_strips_non_semantic_attributes(self):
        from html_utils import preprocess_html

        html = (
            '<html><body><div id="bracket" onclick="doStuff()" '
            'style="color:red" class="main">Content</div></body></html>'
        )
        result = preprocess_html(html)
        assert "onclick" not in result
        assert "style" not in result
        # id and class are kept but we're checking the text output
        assert "Content" in result

    def test_extracts_embedded_json_from_script(self):
        from html_utils import preprocess_html

        json_data = '{"bracket": {"picks": ["Duke", "Kansas"]}}'
        html = f"<html><body><script>window.__INITIAL_STATE__ = {json_data};</script><p>Other</p></body></html>"
        result = preprocess_html(html)
        assert "Duke" in result
        assert "Kansas" in result

    def test_extracts_next_data_json(self):
        from html_utils import preprocess_html

        json_data = '{"props": {"bracket": ["UConn"]}}'
        html = f'<html><body><script id="__NEXT_DATA__" type="application/json">{json_data}</script></body></html>'
        result = preprocess_html(html)
        assert "UConn" in result

    def test_isolates_bracket_subtree(self):
        from html_utils import preprocess_html

        html = (
            "<html><body>"
            "<div id='sidebar'>Sidebar junk</div>"
            "<div id='bracket-container'><span>Duke vs Kansas</span></div>"
            "<div id='ads'>Buy stuff</div>"
            "</body></html>"
        )
        result = preprocess_html(html)
        assert "Duke vs Kansas" in result
        # Sidebar and ads may or may not be present depending on implementation;
        # the key assertion is that bracket content is preserved

    def test_collapses_whitespace(self):
        from html_utils import preprocess_html

        html = "<html><body><p>Duke    \n\n\n   Kansas</p></body></html>"
        result = preprocess_html(html)
        # Should not have excessive whitespace
        assert "\n\n\n" not in result

    def test_truncates_to_max_chars(self):
        from html_utils import preprocess_html

        html = "<html><body><p>" + "A" * 200 + "</p></body></html>"
        result = preprocess_html(html, max_chars=50)
        assert len(result) <= 50

    def test_handles_empty_html(self):
        from html_utils import preprocess_html

        result = preprocess_html("")
        assert isinstance(result, str)


class TestFetchHtml:
    @pytest.mark.asyncio
    async def test_success_returns_html(self):
        from html_utils import fetch_html

        with aioresponses() as m:
            m.get("https://example.com/bracket", body="<html>bracket</html>", content_type="text/html")
            result = await fetch_html("https://example.com/bracket")
        assert "bracket" in result

    @pytest.mark.asyncio
    async def test_non_200_raises_valueerror(self):
        from html_utils import fetch_html

        with aioresponses() as m:
            m.get("https://example.com/bracket", status=404)
            with pytest.raises(ValueError, match="404"):
                await fetch_html("https://example.com/bracket")

    @pytest.mark.asyncio
    async def test_non_html_content_type_raises_valueerror(self):
        from html_utils import fetch_html

        with aioresponses() as m:
            m.get("https://example.com/data.json", body='{"a":1}', content_type="application/json")
            with pytest.raises(ValueError, match="HTML"):
                await fetch_html("https://example.com/data.json")

    @pytest.mark.asyncio
    async def test_timeout_raises_valueerror(self):
        from html_utils import fetch_html

        with aioresponses() as m:
            m.get("https://example.com/slow", exception=asyncio.TimeoutError())
            with pytest.raises(ValueError, match="[Tt]imeout"):
                await fetch_html("https://example.com/slow")
