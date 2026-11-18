#!/usr/bin/env python3
"""
Configure an X11/XWayland window as a borderless, shadowless always-on-top overlay
by enabling override_redirect (same mechanism X11 uses for tooltips/popups).
"""
import ctypes
import sys


class XSetWindowAttributes(ctypes.Structure):
    _fields_ = [
        ("background_pixmap", ctypes.c_ulong),
        ("background_pixel", ctypes.c_ulong),
        ("border_pixmap", ctypes.c_ulong),
        ("border_pixel", ctypes.c_ulong),
        ("bit_gravity", ctypes.c_int),
        ("win_gravity", ctypes.c_int),
        ("backing_store", ctypes.c_int),
        ("backing_planes", ctypes.c_ulong),
        ("backing_pixel", ctypes.c_ulong),
        ("save_under", ctypes.c_int),
        ("event_mask", ctypes.c_long),
        ("do_not_propagate_mask", ctypes.c_long),
        ("override_redirect", ctypes.c_int),
        ("colormap", ctypes.c_ulong),
        ("cursor", ctypes.c_ulong),
    ]


CWOverrideRedirect = 1 << 9


def main() -> int:
    if len(sys.argv) < 2:
        return 1
    try:
        wid = int(sys.argv[1], 0)
    except ValueError:
        return 1

    xlib = ctypes.cdll.LoadLibrary("libX11.so.6")
    xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    xlib.XOpenDisplay.restype = ctypes.c_void_p
    xlib.XUnmapWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    xlib.XChangeWindowAttributes.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.POINTER(XSetWindowAttributes),
    ]
    xlib.XMapRaised.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    xlib.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]

    dpy = xlib.XOpenDisplay(None)
    if not dpy:
        return 1
    try:
        attrs = XSetWindowAttributes()
        attrs.override_redirect = 1
        xlib.XUnmapWindow(dpy, wid)
        xlib.XSync(dpy, 0)
        xlib.XChangeWindowAttributes(dpy, wid, CWOverrideRedirect, ctypes.byref(attrs))
        xlib.XMapRaised(dpy, wid)
        xlib.XSync(dpy, 0)
        return 0
    finally:
        xlib.XCloseDisplay(dpy)


if __name__ == "__main__":
    raise SystemExit(main())
