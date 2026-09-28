import ctypes, time
k32 = ctypes.WinDLL("kernel32")
k32.OpenProcess.restype = ctypes.c_void_p
k32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
# 枚举杀掉所有 ToMe.exe
psapi = ctypes.WinDLL("psapi")
import ctypes.wintypes as wt
arr = (wt.DWORD * 4096)()
cb = wt.DWORD()
psapi.EnumProcesses(ctypes.byref(arr), ctypes.sizeof(arr), ctypes.byref(cb))
n = cb.value // ctypes.sizeof(wt.DWORD)
killed = 0
for i in range(n):
    pid = arr[i]
    if not pid: continue
    h = k32.OpenProcess(0x1F0FFF, False, pid)
    if not h: continue
    buf = ctypes.create_unicode_buffer(260)
    sz = wt.DWORD(260)
    try:
        psapi.GetModuleFileNameExW(h, None, buf, ctypes.byref(sz))
    except Exception:
        k32.CloseHandle(h); continue
    name = buf.value.lower()
    k32.CloseHandle(h)
    if name.endswith("tome.exe"):
        ph = k32.OpenProcess(0x1F0FFF, False, pid)
        if ph:
            k32.TerminateProcess(ph, 1)
            k32.CloseHandle(ph)
            killed += 1
print("killed:", killed)
