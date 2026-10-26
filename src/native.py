"""Foreground-only Windows screen capture and short, releasable input events."""
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import time
from PIL import ImageGrab

u32 = C.WinDLL("user32", use_last_error=True)
k32 = C.WinDLL("kernel32", use_last_error=True)
ULONG_PTR = C.c_size_t

class MOUSEINPUT(C.Structure):
    _fields_ = [("dx", W.LONG), ("dy", W.LONG), ("mouseData", W.DWORD),
                ("dwFlags", W.DWORD), ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]
class KEYBDINPUT(C.Structure):
    _fields_ = [("wVk", W.WORD), ("wScan", W.WORD), ("dwFlags", W.DWORD),
                ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]
class HARDWAREINPUT(C.Structure):
    _fields_ = [("uMsg", W.DWORD), ("wParamL", W.WORD), ("wParamH", W.WORD)]
class InputUnion(C.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]
class INPUT(C.Structure):
    _anonymous_ = ("payload",)
    _fields_ = [("type", W.DWORD), ("payload", InputUnion)]

u32.GetForegroundWindow.restype = W.HWND
u32.GetWindowTextLengthW.argtypes = [W.HWND]
u32.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
u32.GetClientRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
u32.ClientToScreen.argtypes = [W.HWND, C.POINTER(W.POINT)]
u32.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
u32.SendInput.argtypes = [W.UINT, C.POINTER(INPUT), C.c_int]
u32.SendInput.restype = W.UINT
u32.GetAsyncKeyState.argtypes = [C.c_int]
u32.GetAsyncKeyState.restype = C.c_short
u32.IsIconic.argtypes = [W.HWND]
k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.OpenProcess.restype = W.HANDLE
k32.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
k32.CloseHandle.argtypes = [W.HANDLE]
k32.CreateMutexW.argtypes = [C.c_void_p, W.BOOL, W.LPCWSTR]
k32.CreateMutexW.restype = W.HANDLE

def single_instance():
    handle = k32.CreateMutexW(None, False, 'Local\\NTE_SweetSwing_Helper')
    if not handle:
        raise C.WinError(C.get_last_error())
    if C.get_last_error() == 183:
        k32.CloseHandle(handle)
        u32.MessageBoxW(None, '助手已经在运行。使用 F8 开始/暂停，F9 停止。', '异环小游戏助手', 64)
        return None
    return handle

def dpi_awareness():
    try:
        u32.SetProcessDpiAwarenessContext.argtypes = [C.c_void_p]
        u32.SetProcessDpiAwarenessContext(C.c_void_p(-4))
    except Exception:
        u32.SetProcessDPIAware()

def title(hwnd):
    buf = C.create_unicode_buffer(u32.GetWindowTextLengthW(hwnd) + 1)
    u32.GetWindowTextW(hwnd, buf, len(buf))
    return buf.value.strip()

def is_game(hwnd):
    if not hwnd or title(hwnd) != "异环":
        return False
    pid = W.DWORD()
    u32.GetWindowThreadProcessId(hwnd, C.byref(pid))
    handle = k32.OpenProcess(0x1000, False, pid.value)
    if not handle:
        return False
    try:
        path = C.create_unicode_buffer(32768)
        size = W.DWORD(len(path))
        return bool(k32.QueryFullProcessImageNameW(handle, 0, path, C.byref(size))
                    and Path(path.value).name.lower() == "htgame.exe")
    finally:
        k32.CloseHandle(handle)

def foreground_game():
    hwnd = u32.GetForegroundWindow()
    return hwnd if is_game(hwnd) and not u32.IsIconic(hwnd) else None

def bounds(hwnd):
    rect, point = W.RECT(), W.POINT(0, 0)
    if not u32.GetClientRect(hwnd, C.byref(rect)) or not u32.ClientToScreen(hwnd, C.byref(point)):
        raise RuntimeError("无法读取游戏窗口尺寸")
    return point.x, point.y, point.x + rect.right, point.y + rect.bottom

def capture(hwnd):
    box = bounds(hwnd)
    w, h = box[2] - box[0], box[3] - box[1]
    if w < 1280 or h < 720 or abs(w / h - 16 / 9) > .04:
        raise RuntimeError("请将游戏设为 16:9 窗口/无边框模式，分辨率不低于 1280×720")
    return ImageGrab.grab(bbox=box, all_screens=True), box

def pressed(vk):
    return bool(u32.GetAsyncKeyState(vk) & 0x8000)

class Input:
    SCAN = {"w": 0x11, "a": 0x1e, "s": 0x1f, "d": 0x20}
    def __init__(self, enabled):
        self.held = set()
        self.enabled = enabled

    def send(self, event):
        if u32.SendInput(1, C.byref(event), C.sizeof(INPUT)) != 1:
            raise RuntimeError("游戏未接受输入，请检查游戏和助手是否以相同权限运行")

    def allowed(self, hwnd):
        return self.enabled() and u32.GetForegroundWindow() == hwnd and not pressed(0x78)

    def key(self, key, down, hwnd=None):
        if down and not self.allowed(hwnd):
            return False
        event = INPUT(type=1, ki=KEYBDINPUT(0, self.SCAN[key], 0x0008 | (0 if down else 0x0002), 0, 0))
        self.send(event)
        if down:
            self.held.add(key)
        else:
            self.held.discard(key)
        return True

    def tap(self, key, hwnd):
        if self.key(key, True, hwnd):
            try:
                time.sleep(.045)
            finally:
                self.key(key, False)

    def release_all(self):
        errors = []
        for key in list(self.held):
            try:
                self.key(key, False)
            except Exception as error:
                errors.append(error)
        if errors:
            raise errors[0]

    def click(self, name, hwnd, captured_bounds):
        if not self.allowed(hwnd) or bounds(hwnd) != captured_bounds:
            return
        positions = {"retry": (928, 743), "start": (1158, 783)}
        x, y = positions[name]
        l, t, r, b = captured_bounds
        u32.SetCursorPos(int(l + x * (r - l) / 1536), int(t + y * (b - t) / 864))
        time.sleep(.035)
        if not self.allowed(hwnd):
            return
        self.send(INPUT(type=0, mi=MOUSEINPUT(0, 0, 0, 0x0002, 0, 0)))
        try:
            time.sleep(.040)
        finally:
            self.send(INPUT(type=0, mi=MOUSEINPUT(0, 0, 0, 0x0004, 0, 0)))
