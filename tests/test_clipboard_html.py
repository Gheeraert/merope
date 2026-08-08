"""Real clipboard round-trip test for read_html_clipboard().

Writes HTML to the Windows clipboard directly through ctypes (mirroring
what Word/browsers do) and checks read_html_clipboard() gets it back.
Skipped on non-Windows platforms.
"""

from __future__ import annotations

import sys

import pytest

from bloggen.ui.clipboard_html import read_html_clipboard

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows clipboard API only")


def _set_html_clipboard(html: str) -> None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

    payload = html.encode("utf-8") + b"\x00"
    html_format = user32.RegisterClipboardFormatW("HTML Format")

    handle = kernel32.GlobalAlloc(0x0042, len(payload))  # GMEM_MOVEABLE | GMEM_ZEROINIT
    pointer = kernel32.GlobalLock(handle)
    ctypes.memmove(pointer, payload, len(payload))
    kernel32.GlobalUnlock(handle)

    if not user32.OpenClipboard(None):
        raise OSError("cannot open clipboard")
    try:
        user32.EmptyClipboard()
        user32.SetClipboardData(html_format, handle)
    finally:
        user32.CloseClipboard()


def _set_full_envelope_html_clipboard(fragment: str) -> None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

    prefix_template = (
        "Version:0.9\r\n"
        "StartHTML:{start_html:010d}\r\n"
        "EndHTML:{end_html:010d}\r\n"
        "StartFragment:{start_frag:010d}\r\n"
        "EndFragment:{end_frag:010d}\r\n"
    )
    header_len = len(prefix_template.format(start_html=0, end_html=0, start_frag=0, end_frag=0).encode("utf-8"))
    html_doc = "<html><body><!--StartFragment-->" + fragment + "<!--EndFragment--></body></html>"
    start_html = header_len
    start_frag = start_html + html_doc.index("<!--StartFragment-->") + len("<!--StartFragment-->")
    end_frag = start_html + html_doc.index("<!--EndFragment-->")
    end_html = start_html + len(html_doc.encode("utf-8"))
    prefix = prefix_template.format(start_html=start_html, end_html=end_html, start_frag=start_frag, end_frag=end_frag)
    full = (prefix + html_doc).encode("utf-8") + b"\x00"

    html_format = user32.RegisterClipboardFormatW("HTML Format")
    handle = kernel32.GlobalAlloc(0x0042, len(full))
    pointer = kernel32.GlobalLock(handle)
    ctypes.memmove(pointer, full, len(full))
    kernel32.GlobalUnlock(handle)

    if not user32.OpenClipboard(None):
        raise OSError("cannot open clipboard")
    try:
        user32.EmptyClipboard()
        user32.SetClipboardData(html_format, handle)
    finally:
        user32.CloseClipboard()


def test_read_html_clipboard_raw_no_envelope():
    html = "<html><body><p>Un <b>test</b> sans enveloppe.</p></body></html>"
    _set_html_clipboard(html)
    assert read_html_clipboard() == html


def test_read_html_clipboard_full_cf_html_envelope():
    fragment = "<p>Un <b>test</b> avec enveloppe complete.</p>"
    _set_full_envelope_html_clipboard(fragment)
    assert read_html_clipboard() == fragment


def test_read_html_clipboard_returns_none_without_html():
    import ctypes

    ctypes.windll.user32.OpenClipboard(None)
    try:
        ctypes.windll.user32.EmptyClipboard()
        # Put plain text only, via Tk-independent Win32 CF_UNICODETEXT.
    finally:
        ctypes.windll.user32.CloseClipboard()
    assert read_html_clipboard() is None
