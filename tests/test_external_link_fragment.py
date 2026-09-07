"""Tests for render_external_link_fragment's iframe sandboxing and scheme
guard (see the external audit: iframes were embedded with no sandbox, no
referrerpolicy, and no restriction on the URL scheme).
"""

from __future__ import annotations

from bloggen.render.html_templates import render_external_link_fragment


def test_iframe_carries_sandbox_and_referrer_policy():
    html = render_external_link_fragment(label="Wikipédia", url="https://fr.wikipedia.org")

    assert '<iframe class="external-embed-frame"' in html
    assert 'sandbox="allow-scripts allow-same-origin allow-popups allow-forms"' in html
    assert 'referrerpolicy="no-referrer"' in html
    # Never delegates any browser permission (camera, geolocation, ...).
    assert " allow=" not in html


def test_fallback_link_keeps_noopener_noreferrer():
    html = render_external_link_fragment(label="Wikipédia", url="https://fr.wikipedia.org")
    assert 'rel="noopener noreferrer"' in html
    assert 'target="_blank"' in html


def test_https_url_is_embedded_normally():
    html = render_external_link_fragment(label="Site", url="https://example.org/page")
    assert '<iframe class="external-embed-frame" src="https://example.org/page"' in html
    assert '<a href="https://example.org/page"' in html


def test_http_url_is_embedded_normally():
    html = render_external_link_fragment(label="Site", url="http://example.org/page")
    assert "<iframe" in html


def test_javascript_scheme_is_never_embedded():
    html = render_external_link_fragment(label="Malveillant", url="javascript:alert(1)")
    assert "<iframe" not in html
    assert "javascript:" not in html
    assert "invalide" in html


def test_data_scheme_is_never_embedded():
    html = render_external_link_fragment(label="Malveillant", url="data:text/html,<script>alert(1)</script>")
    assert "<iframe" not in html
    assert "data:" not in html


def test_file_scheme_is_never_embedded():
    html = render_external_link_fragment(label="Local", url="file:///etc/passwd")
    assert "<iframe" not in html
    assert "file:" not in html


def test_scheme_check_is_case_insensitive():
    html = render_external_link_fragment(label="Malveillant", url="JavaScript:alert(1)")
    assert "<iframe" not in html


def test_invalid_scheme_message_escapes_the_label():
    html = render_external_link_fragment(label='<script>alert(1)</script>', url="javascript:alert(1)")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
