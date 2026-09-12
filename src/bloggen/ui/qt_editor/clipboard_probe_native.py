"""Read-only Win32 clipboard format inventory for the clipboard probe."""

from __future__ import annotations

import sys
from dataclasses import dataclass


_STANDARD_FORMAT_NAMES = {
    1: "CF_TEXT",
    2: "CF_BITMAP",
    3: "CF_METAFILEPICT",
    4: "CF_SYLK",
    5: "CF_DIF",
    6: "CF_TIFF",
    7: "CF_OEMTEXT",
    8: "CF_DIB",
    9: "CF_PALETTE",
    10: "CF_PENDATA",
    11: "CF_RIFF",
    12: "CF_WAVE",
    13: "CF_UNICODETEXT",
    14: "CF_ENHMETAFILE",
    15: "CF_HDROP",
    16: "CF_LOCALE",
    17: "CF_DIBV5",
}


@dataclass(frozen=True, slots=True)
class NativeClipboardFormat:
    format_id: int
    name: str
    size_bytes: int | None


@dataclass(frozen=True, slots=True)
class NativeClipboardReport:
    available: bool
    formats: tuple[NativeClipboardFormat, ...] = ()
    message: str | None = None


def native_format_name(format_id: int, registered_name: str | None = None) -> str:
    """Return a readable Win32 clipboard format name without guessing its use."""

    if format_id in _STANDARD_FORMAT_NAMES:
        return _STANDARD_FORMAT_NAMES[format_id]
    if registered_name:
        return registered_name
    return f"format-{format_id}"


def enumerate_windows_clipboard_formats() -> NativeClipboardReport:
    """Enumerate current Win32 clipboard names and global sizes, read-only."""

    if sys.platform != "win32":
        return NativeClipboardReport(False, message="indisponible hors Windows")

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL
        user32.EnumClipboardFormats.argtypes = [wintypes.UINT]
        user32.EnumClipboardFormats.restype = wintypes.UINT
        user32.GetClipboardFormatNameW.argtypes = [
            wintypes.UINT,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetClipboardFormatNameW.restype = ctypes.c_int
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = wintypes.HANDLE
        kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalSize.restype = ctypes.c_size_t
    except (AttributeError, ImportError, OSError) as exc:
        return NativeClipboardReport(False, message=f"API Win32 indisponible : {exc}")

    if not user32.OpenClipboard(None):
        return NativeClipboardReport(False, message="presse-papiers Win32 occupé")

    formats: list[NativeClipboardFormat] = []
    try:
        format_id = 0
        while True:
            format_id = int(user32.EnumClipboardFormats(format_id))
            if format_id == 0:
                break

            registered_name = None
            if format_id >= 0xC000:
                buffer = ctypes.create_unicode_buffer(256)
                length = user32.GetClipboardFormatNameW(format_id, buffer, len(buffer))
                if length:
                    registered_name = buffer.value

            handle = user32.GetClipboardData(format_id)
            size = int(kernel32.GlobalSize(handle)) if handle else 0
            formats.append(
                NativeClipboardFormat(
                    format_id=format_id,
                    name=native_format_name(format_id, registered_name),
                    size_bytes=size or None,
                )
            )
    except OSError as exc:
        return NativeClipboardReport(
            False,
            formats=tuple(formats),
            message=f"énumération Win32 interrompue : {exc}",
        )
    finally:
        user32.CloseClipboard()

    return NativeClipboardReport(True, formats=tuple(formats))
