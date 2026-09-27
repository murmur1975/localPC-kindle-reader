import asyncio
import ctypes
from ctypes import wintypes
import io
import sys
import time
from pathlib import Path
from PIL import Image, ImageGrab
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# WindowsコンソールのUTF-8化
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    # default デスクトップへ切り替え（エージェント分離セッション対策）
    try:
        user32 = ctypes.windll.user32
        DESKTOP_ALL = 0x01FF
        hdesk = user32.OpenDesktopW("default", 0, False, DESKTOP_ALL)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception:
        pass

# Windows RT OCR インポート
from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.globalization import Language
from winrt.windows.storage.streams import InMemoryRandomAccessStream, DataWriter

console = Console(force_terminal=True, legacy_windows=False)
user32 = ctypes.windll.user32


def find_kindle_hwnd():
    """Kindleのメイン読書ウィンドウハンドルを特定"""
    candidates = []
    
    WNDENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            b = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, b, 512)
            title = b.value.strip()
            
            cb = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cb, 256)
            cname = cb.value
            
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            
            # メイン読書画面: Microsoft.UI.Windowing.Window かつ タイトルが Kindle
            if cname == "Microsoft.UI.Windowing.Window" and "kindle" in title.lower() and w > 400 and h > 400:
                candidates.append((hwnd, title, cname, (rect.left, rect.top, rect.right, rect.bottom), w, h))
        return True

    user32.EnumWindows(WNDENUM(enum_cb), 0)
    if candidates:
        candidates.sort(key=lambda x: x[4] * x[5], reverse=True)
        return candidates[0]
    return None


def force_foreground_window(hwnd):

    """Windowsのフォアグラウンドロックを解除して確実にウィンドウを前面にする"""
    fore_hwnd = user32.GetForegroundWindow()
    if fore_hwnd == hwnd:
        return
    cur_thread = ctypes.windll.kernel32.GetCurrentThreadId()
    fore_thread = user32.GetWindowThreadProcessId(fore_hwnd, None)
    
    user32.AttachThreadInput(cur_thread, fore_thread, True)
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    user32.AttachThreadInput(cur_thread, fore_thread, False)
    time.sleep(0.5)


def capture_window_printwindow(hwnd):
    """PrintWindow API (PW_RENDERFULLCONTENT) を使ってウィンドウを直接キャプチャ"""
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top

    if w <= 0 or h <= 0:
        return None

    # デバイスコンテキスト作成
    hwnd_dc = user32.GetWindowDC(hwnd)
    mem_dc = ctypes.windll.gdi32.CreateCompatibleDC(hwnd_dc)
    bitmap = ctypes.windll.gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
    ctypes.windll.gdi32.SelectObject(mem_dc, bitmap)

    # PW_RENDERFULLCONTENT = 2
    res = user32.PrintWindow(hwnd, mem_dc, 2)
    
    # ビットマップデータをPIL Imageに変換
    import win32ui
    import win32gui
    # ctypesでビットマップの生データを取得
    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth = w
    bi.biHeight = -h  # top-down
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0  # BI_RGB

    buffer = ctypes.create_string_buffer(w * h * 4)
    ctypes.windll.gdi32.GetDIBits(
        mem_dc, bitmap, 0, h, buffer, ctypes.byref(bi), 0
    )

    # クリーンアップ
    ctypes.windll.gdi32.DeleteObject(bitmap)
    ctypes.windll.gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(hwnd, hwnd_dc)

    # PIL Imageとして生成
    img = Image.frombuffer("RGBA", (w, h), buffer, "raw", "BGRA", 0, 1)
    return img.convert("RGB")



async def run_ocr_on_image(pil_img: Image.Image, lang_tag="ja"):
    """PIL Imageに対してWindows.Media.Ocrを実行"""
    lang = Language(lang_tag)
    engine = OcrEngine.try_create_from_language(lang)
    if not engine:
        raise RuntimeError(f"OCRエンジン ({lang_tag}) の初期化に失敗しました。")

    # RGBAに変換してバイト列を取得
    rgba_img = pil_img.convert("RGBA")
    width, height = rgba_img.size
    raw_bytes = rgba_img.tobytes()

    # SoftwareBitmapの作成
    software_bitmap = SoftwareBitmap.create_copy_from_buffer(
        raw_bytes,
        BitmapPixelFormat.RGBA8,
        width,
        height
    )

    t0 = time.perf_counter()
    result = await engine.recognize_async(software_bitmap)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    lines = []
    full_text_lines = []
    for line in result.lines:
        line_text = line.text
        full_text_lines.append(line_text)
        words = [{"text": w.text, "rect": (w.bounding_rect.x, w.bounding_rect.y, w.bounding_rect.width, w.bounding_rect.height)} for w in line.words]
        lines.append({
            "text": line_text,
            "words": words
        })

    return {
        "text": "\n".join(full_text_lines),
        "lines": lines,
        "elapsed_ms": elapsed_ms,
        "angle": result.text_angle
    }


async def main():
    console.rule("[bold cyan]Kindle for PC 読書画面 OCR テスト[/bold cyan]")
    
    # 1. Kindleウィンドウの検索
    console.print("[yellow]Kindle読書ウィンドウを探索中...[/yellow]")
    info = find_kindle_hwnd()
    if not info:
        console.print("[red][X] Kindleの読書ウィンドウが見つかりませんでした。書籍が開かれているか確認してください。[/red]")
        return
        
    hwnd, title, cname, rect, w, h = info
    console.print(f"[green][OK] Kindleウィンドウを検出: HWND={hwnd}, Title='{title}', Size={w}x{h}[/green]")
    console.print(f"    座標: Left={rect[0]}, Top={rect[1]}, Right={rect[2]}, Bottom={rect[3]}")

    # 2. ウィンドウのアクティブ化
    console.print("[yellow]Kindleウィンドウを最前面にフォーカス中...[/yellow]")
    force_foreground_window(hwnd)

    # 3. 画面キャプチャ
    console.print("[yellow]読書エリアのキャプチャを実行中...[/yellow]")
    
    # 座標のクランプ（最大化時の負のオフセット補正）
    # クライアント領域の正確な座標を取得
    client_rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(client_rect))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    
    cl_left = pt.x
    cl_top = pt.y
    cl_right = pt.x + client_rect.right
    cl_bottom = pt.y + client_rect.bottom
    console.print(f"  クライアント領域座標: ({cl_left}, {cl_top})-({cl_right}, {cl_bottom})")

    # ImageGrabでクライアント領域を直接撮影
    full_img = ImageGrab.grab(bbox=(cl_left, cl_top, cl_right, cl_bottom), all_screens=True)
    
    # 保存用ディレクトリ
    artifact_dir = Path("scripts/captures")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    full_path = artifact_dir / "kindle_full.png"
    full_img.save(full_path)
    console.print(f"  ウィンドウ全体のキャプチャを保存: [dim]{full_path}[/dim]")


    # 4. 読書領域のクロッピング（上部ツールバー・下部フッター・左右のマージンを除外）
    img_w, img_h = full_img.size
    pad_top = int(img_h * 0.08)       # 約8%（ツールバー除外）
    pad_bottom = int(img_h * 0.06)    # 約6%（フッター・シークバー除外）
    pad_side = int(img_w * 0.08)      # 左右8%（左右のページ送りボタン等除外）

    crop_box = (
        pad_side,
        pad_top,
        img_w - pad_side,
        img_h - pad_bottom
    )

    
    reading_area_img = full_img.crop(crop_box)
    reading_path = artifact_dir / "kindle_reading_area.png"
    reading_area_img.save(reading_path)
    console.print(f"  クロップ後の読書エリアを保存: [dim]{reading_path}[/dim] (Size: {reading_area_img.size})")

    # 5. Windows.Media.Ocr によるテキスト抽出
    console.print(f"\n[cyan]Windows.Media.Ocr (日本語) によるテキスト認識を実行中...[/cyan]")
    ocr_result = await run_ocr_on_image(reading_area_img, lang_tag="ja")

    console.print(f"[green]✓ OCR処理完了: [bold]{ocr_result['elapsed_ms']:.1f} ms[/bold][/green]")
    console.print(f"検出行数: {len(ocr_result['lines'])} 行, テキスト傾き: {ocr_result['angle']} 度\n")

    # 認識されたテキストの表示
    table = Table(title="OCR 抽出行一覧 (先頭15行)")
    table.add_column("行", style="dim", width=4)
    table.add_column("テキスト", style="white")

    for i, line in enumerate(ocr_result["lines"][:15]):
        table.add_row(str(i + 1), line["text"])

    console.print(table)

    # 全文表示
    console.print(Panel(ocr_result["text"], title="[bold green]抽出された全文[/bold green]", expand=False))

    # テキストファイルとしても保存
    text_path = artifact_dir / "extracted_text.txt"
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(ocr_result["text"])
    console.print(f"\n[dim]抽出テキストを {text_path} に保存しました。[/dim]")

if __name__ == "__main__":
    asyncio.run(main())
