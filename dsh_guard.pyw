# -*- coding: utf-8 -*-
"""DSH 守护：1) 更新时补回 office-skills  2) 清理残留进程避免安装器改名失败"""
import ctypes, io, json, os, shutil, time
from ctypes import wintypes

BASE = os.path.dirname(os.path.abspath(__file__))
STASH = os.path.join(BASE, "office-skills")
LOG = os.path.join(BASE, "guard.log")
ASAR = r"E:\DeepSeek\resources\app.asar"
ASAR_STAMP = os.path.join(BASE, "asar.stamp")
SKILLS = r"E:\DeepSeek\resources\runtime\office-skills"
APP_DIR = r"E:\DeepSeek"
APP_EXE = "deepseek harness.exe"
NAMES = ["office", "office-docx", "office-pptx", "office-xlsx", "office-render", "office-recalculate", "office-export-pdf"]

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
k32.CloseHandle.argtypes = [wintypes.HANDLE]

class PE32(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260)]

def log(msg):
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > 300000:
            os.replace(LOG, LOG + ".1")
        with io.open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except Exception:
        pass

def procs():
    snap = k32.CreateToolhelp32Snapshot(0x00000002, 0)
    out = []
    if snap in (0, wintypes.HANDLE(-1).value):
        return out
    e = PE32(); e.dwSize = ctypes.sizeof(PE32)
    ok = k32.Process32FirstW(snap, ctypes.byref(e))
    while ok:
        out.append((int(e.th32ProcessID), e.szExeFile.lower()))
        ok = k32.Process32NextW(snap, ctypes.byref(e))
    k32.CloseHandle(snap)
    return out

def image(pid):
    h = k32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wintypes.DWORD(1024)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return buf.value
        return ""
    finally:
        k32.CloseHandle(h)

def kill(pid):
    h = k32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
    if not h:
        return False
    try:
        return bool(k32.TerminateProcess(h, 1))
    finally:
        k32.CloseHandle(h)

def heal():
    missing = [n for n in NAMES if not os.path.isfile(os.path.join(SKILLS, n, "SKILL.md"))]
    if not missing:
        return
    if not os.path.isdir(STASH):
        log("heal skip: stash missing")
        return
    copied = 0
    for root, _dirs, files in os.walk(STASH):
        rel = os.path.relpath(root, STASH)
        dst = SKILLS if rel == "." else os.path.join(SKILLS, rel)
        try:
            os.makedirs(dst, exist_ok=True)
        except Exception:
            continue
        for f in files:
            d = os.path.join(dst, f)
            if not os.path.exists(d):
                try:
                    shutil.copy2(os.path.join(root, f), d); copied += 1
                except Exception:
                    pass
    log("heal restored %d file(s), missing=%s" % (copied, ",".join(missing)))

def refresh_stash():
    try:
        if not os.path.isfile(ASAR):
            return
        st = "%d:%d" % (os.path.getsize(ASAR), int(os.path.getmtime(ASAR)))
        old = io.open(ASAR_STAMP, encoding="utf-8").read().strip() if os.path.exists(ASAR_STAMP) else ""
        if st == old:
            return
        f = io.open(ASAR, "rb")
        head = f.read(16)
        jlen = int.from_bytes(head[8:12], "little")
        buf = f.read(jlen).decode("utf-8")
        hdr, end = json.JSONDecoder().raw_decode(buf)
        base = 12 + end + 4
        node = hdr
        for part in "dsh/node_modules/@deepseek-ai/dsh-skill-office/assets".split("/"):
            node = node["files"][part]
        n = 0
        for name, meta in node["files"].items():
            if "files" not in meta:
                continue
            for fn, m in meta["files"].items():
                if "offset" not in m: continue
                f.seek(base + int(m["offset"]))
                dst_dir = os.path.join(STASH, name)
                os.makedirs(dst_dir, exist_ok=True)
                io.open(os.path.join(dst_dir, fn), "wb").write(f.read(int(m["size"])))
                n += 1
        io.open(ASAR_STAMP, "w", encoding="utf-8").write(st)
        log("stash refreshed from asar: %d file(s)" % n)
    except Exception as e:
        log("refresh failed: %r" % (e,))

def main():
    os.makedirs(BASE, exist_ok=True)
    refresh_stash()
    heal()
    idle = 0
    last_install = 0.0
    while True:
        try:
            ps = procs()
            app_running = any(n == APP_EXE for _p, n in ps)
            installer = any(n.endswith('installer.exe') or n.startswith('deepseek-harness-') for _p, n in ps)
            if installer and time.time() - last_install > 120:
                killed = []
                for pid, name in ps:
                    if pid in (0, 4):
                        continue
                    ip = image(pid)
                    if ip and ip.lower().startswith(APP_DIR.lower() + chr(92)):
                        if kill(pid):
                            killed.append(os.path.basename(ip))
                last_install = time.time()
                log('installer detected, killed %d: %s' % (len(killed), ','.join(killed)))
            elif app_running:
                idle = 0
            else:
                idle += 1
                if idle >= 2:
                    killed = []
                    for pid, name in ps:
                        if pid in (0, 4):
                            continue
                        p = image(pid)
                        if p and p.lower().startswith(APP_DIR.lower() + "\\"):
                            if kill(pid):
                                killed.append(os.path.basename(p))
                    if killed:
                        log("killed orphan: " + ",".join(killed))
            heal()
        except Exception as e:
            log("loop error: %r" % (e,))
        time.sleep(0.4)

if __name__ == "__main__":
    main()
