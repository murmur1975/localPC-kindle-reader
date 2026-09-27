import asyncio
import ctypes
from ctypes import wintypes
import time
from typing import Optional, Dict, Any, List
from PIL import Image, ImageGrab

from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.globalization import Language

user32 = ctypes.windll.user32

class ScreenCaptureOcr:
    """Kindle読書領域の自動キャプチャおよびWindows.Media.Ocrによる高速テキスト抽出"""

    def __init__(self, hwnd: int, pad_top_ratio: float = 0.08, pad_bottom_ratio: float = 0.06, pad_side_ratio: float = 0.08):
        self.hwnd = hwnd
        self.pad_top_ratio = pad_top_ratio
        self.pad_bottom_ratio = pad_bottom_ratio
        self.pad_side_ratio = pad_side_ratio
        
        self.engine = OcrEngine.try_create_from_language(Language("ja"))
        if not self.engine:
            raise RuntimeError("Windows.Media.Ocr 日本語エンジンの作成に失敗しました。")

    def capture_reading_area(self) -> Image.Image:
        """Kindleウィンドウのクライアント領域から読書エリアのみをキャプチャ"""
        client_rect = wintypes.RECT()
        user32.GetClientRect(self.hwnd, ctypes.byref(client_rect))
        pt = wintypes.POINT(0, 0)
        user32.ClientToScreen(self.hwnd, ctypes.byref(pt))

        cl_left = max(0, pt.x)
        cl_top = max(0, pt.y)
        cl_right = pt.x + client_rect.right
        cl_bottom = pt.y + client_rect.bottom

        # ウィンドウ領域を撮影
        full_img = ImageGrab.grab(bbox=(cl_left, cl_top, cl_right, cl_bottom), all_screens=True)
        img_w, img_h = full_img.size

        # 上下左右のUIパーツ（ツールバー、フッター、ページ送りボタン）を除外
        pad_top = int(img_h * self.pad_top_ratio)
        pad_bottom = int(img_h * self.pad_bottom_ratio)
        pad_side = int(img_w * self.pad_side_ratio)

        crop_box = (
            pad_side,
            pad_top,
            img_w - pad_side,
            img_h - pad_bottom
        )
        return full_img.crop(crop_box)

    async def extract_text(self) -> Dict[str, Any]:
        """読書エリアをキャプチャしてOCRを実行"""
        img = self.capture_reading_area()
        
        rgba_img = img.convert("RGBA")
        width, height = rgba_img.size
        raw_bytes = rgba_img.tobytes()

        software_bitmap = SoftwareBitmap.create_copy_from_buffer(
            raw_bytes,
            BitmapPixelFormat.RGBA8,
            width,
            height
        )

        t0 = time.perf_counter()
        ocr_result = await self.engine.recognize_async(software_bitmap)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        lines = [line.text for line in ocr_result.lines]
        raw_text = "\n".join(lines)

        return {
            "text": raw_text,
            "lines": lines,
            "elapsed_ms": elapsed_ms,
            "image": img
        }
