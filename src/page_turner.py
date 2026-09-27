import ctypes
from ctypes import wintypes
import time
from typing import Optional, Tuple
from pywinauto import Desktop
from rich.console import Console

console = Console(force_terminal=True, legacy_windows=False)
user32 = ctypes.windll.user32

# 仮想キーコード
VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_NEXT = 0x22  # PageDown
KEYEVENTF_KEYUP = 0x0002

class KindleController:
    """Kindleウィンドウのフォーカス制御、ページめくりキー送信、UIAページ同期を担うクラス"""

    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        self._uia_window = None

    def _ensure_uia_window(self):
        """UIAラッパーを取得（初回のみ）"""
        if self._uia_window is None:
            desktop = Desktop(backend="uia")
            # HWNDからUIA要素を取得
            for w in desktop.windows():
                if w.element_info.handle == self.hwnd:
                    self._uia_window = w
                    break
        return self._uia_window

    def force_foreground(self):
        """フォアグラウンドロックを解除して確実にウィンドウを前面にする"""
        fore_hwnd = user32.GetForegroundWindow()
        if fore_hwnd == self.hwnd:
            return
        cur_thread = ctypes.windll.kernel32.GetCurrentThreadId()
        fore_thread = user32.GetWindowThreadProcessId(fore_hwnd, None)
        
        user32.AttachThreadInput(cur_thread, fore_thread, True)
        user32.ShowWindow(self.hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(self.hwnd)
        user32.AttachThreadInput(cur_thread, fore_thread, False)
        time.sleep(0.3)

    def get_footer_info(self) -> str:
        """UIAツリーから現在のページ番号・進捗情報 (FooterLabelText) を取得"""
        w = self._ensure_uia_window()
        if not w:
            return ""

        try:
            # FooterLabelText を高速検索
            footers = w.descendants(auto_id="FooterLabelText")
            if footers:
                return footers[0].window_text().strip()
        except Exception:
            pass
        return ""

    def send_page_turn_key(self, direction: str = "left"):
        """
        Kindleウィンドウにページ送りキー入力を送信。
        縦書き日本語書籍: 'left' (VK_LEFT) が次ページ
        横書き書籍: 'right' (VK_RIGHT) または 'pagedown' (VK_NEXT)
        """
        self.force_foreground()
        
        vk = VK_LEFT
        if direction == "right":
            vk = VK_RIGHT
        elif direction in ("pagedown", "next"):
            vk = VK_NEXT

        # KeyDown -> KeyUp
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

    def turn_page_and_wait(self, direction: str = "left", timeout: float = 3.0) -> bool:
        """
        ページをめくり、UIAのページ番号が変わるまで待機して同期する。
        同期が完了したら True を返す。
        """
        old_footer = self.get_footer_info()
        
        # キー送信
        self.send_page_turn_key(direction=direction)

        # UIAページ番号の更新監視
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < timeout:
            time.sleep(0.08)
            new_footer = self.get_footer_info()
            if new_footer and new_footer != old_footer:
                # ページめくりアニメーションの描画安定待ち
                time.sleep(0.2)
                return True

        # タイムアウトした場合（ページ番号表示がない書籍など）も描画待ちを入れて完了とみなす
        time.sleep(0.3)
        return False
