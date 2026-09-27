import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import ctypes
from ctypes import wintypes
import psutil

user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

# default デスクトップへ切り替え
DESKTOP_ALL = 0x01FF
hdesk = user32.OpenDesktopW("default", 0, False, DESKTOP_ALL)
if hdesk:
    if user32.SetThreadDesktop(hdesk):
        print("[+] default デスクトップに切り替え成功")
    else:
        print("[-] SetThreadDesktop 失敗")
else:
    print("[-] OpenDesktopW 失敗")

print("=== 可視ウィンドウ一覧 (ctypes) ===")


total_count = 0
found_count = 0

def enum_cb(hwnd, lparam):
    global total_count, found_count
    total_count += 1
    
    # バッファを固定長で取得
    buff = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buff, 512)
    title = buff.value.strip()
    
    cls_buff = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls_buff, 256)
    cls_name = cls_buff.value
    
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    pid_val = pid.value
    
    visible = user32.IsWindowVisible(hwnd)
    
    if title:
        found_count += 1
        print(f"HWND={hwnd} | Visible={visible} | PID={pid_val} | Class={cls_name} | Title={title}")
        
    return True

user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
print(f"\n走査完了: 全ウィンドウ {total_count} 件中、タイトルあり {found_count} 件")


