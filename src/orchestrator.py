import asyncio
import ctypes
from ctypes import wintypes
import time
from typing import Optional, Dict, Any
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.config import load_config
from src.text_cleaner import TextCleaner
from src.speaker_router import DialogueSpeakerRouter
from src.voicevox_client import VoicevoxClient
from src.audio_player import AudioPlayer
from src.reading_pipeline import ReadingPipeline
from src.page_turner import KindleController
from src.screen_capture_ocr import ScreenCaptureOcr

console = Console(force_terminal=True, legacy_windows=False)
user32 = ctypes.windll.user32

def find_kindle_reading_window() -> Optional[int]:
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
                candidates.append((hwnd, w * h))
        return True

    user32.EnumWindows(WNDENUM(enum_cb), 0)
    if candidates:
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]
    return None


class KindleReaderOrchestrator:
    """自動テキスト抽出、配役、先読み朗読、ページめくりを統括するメインエンジン"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or load_config()
        self.stop_requested = False
        self.current_page = 0
        self.last_page_text = ""

    async def run(self, max_pages: Optional[int] = None):
        console.rule("[bold cyan]Kindle for PC AI 朗読 & 自動ページめくりプレイヤー[/bold cyan]")

        # 1. Kindleウィンドウの検索
        hwnd = find_kindle_reading_window()
        if not hwnd:
            console.print("[bold red][X] Kindle読書ウィンドウが見つかりませんでした。書籍を開いた状態で再実行してください。[/bold red]")
            return

        controller = KindleController(hwnd)
        controller.force_foreground()

        # 2. VOICEVOX クライアントの初期化
        vv_cfg = self.config.get("voicevox", {})
        vv = VoicevoxClient(base_url=vv_cfg.get("base_url", "http://localhost:50021"))
        if not await vv.check_health():
            console.print("[bold red][X] VOICEVOX サーバーに接続できません。起動を確認してください。[/bold red]")
            return

        console.print("[green]✓ VOICEVOX サーバー接続確認 OK[/green]")

        # 3. 各種モジュールの初期化
        ocr_cfg = self.config.get("ocr", {})
        ocr = ScreenCaptureOcr(
            hwnd,
            pad_top_ratio=ocr_cfg.get("pad_top_ratio", 0.08),
            pad_bottom_ratio=ocr_cfg.get("pad_bottom_ratio", 0.06),
            pad_side_ratio=ocr_cfg.get("pad_side_ratio", 0.08)
        )

        cleaner = TextCleaner()
        router = DialogueSpeakerRouter.from_config(self.config)
        player = AudioPlayer()
        pipeline = ReadingPipeline(
            vv,
            player,
            speed_scale=vv_cfg.get("speed_scale", 1.1)
        )

        page_turn_cfg = self.config.get("page_turn", {})
        turn_key = page_turn_cfg.get("key", "left")

        # 配役設定のサマリー表示
        table = Table(title="現在の配役設定")
        table.add_column("役割", style="yellow")
        table.add_column("担当キャラクター名", style="cyan")
        table.add_column("話者ID", style="green")
        for role, (sid, sname) in router.speaker_map.items():
            table.add_row(role, sname, str(sid))
        console.print(table)

        console.print("\n[bold green]=== 自動読書ループを開始します ===[/bold green]")
        console.print("[dim]※ 中断したい場合は Ctrl+C を押してください。[/dim]\n")

        page_count = 0

        try:
            while not self.stop_requested:
                if max_pages and page_count >= max_pages:
                    console.print(f"[cyan]指定ページ数 ({max_pages} ページ) の朗読が完了しました。[/cyan]")
                    break

                page_count += 1
                footer_info = controller.get_footer_info() or f"Page {page_count}"
                console.rule(f"[bold yellow]📖 読書中: {footer_info}[/bold yellow]")

                # A. 画面キャプチャ & OCR抽出
                controller.force_foreground()
                ocr_result = await ocr.extract_text()
                raw_text = ocr_result["text"]
                console.print(f"[dim]OCR抽出完了: {ocr_result['elapsed_ms']:.1f}ms / {len(raw_text)} 文字[/dim]")

                # B. テキスト整形・文分割
                sentences = cleaner.split_into_sentences(raw_text)
                if not sentences:
                    console.print("[yellow]本文テキストが検出されませんでした（図版や空白ページの可能性があります）。ページを進めます。[/yellow]")
                    controller.turn_page_and_wait(direction=turn_key)
                    continue

                # 重複判定（前ページと同じテキストなら停止）
                if raw_text == self.last_page_text:
                    console.print("[yellow]前のページと同一のテキストです。書籍末尾に到達した可能性があります。[/yellow]")
                    break
                self.last_page_text = raw_text

                # C. 話者配役
                routed_items = router.route_sentences(sentences, strip_speaker_label=True)
                console.print(f"[cyan]本文文数: {len(routed_items)} 文[/cyan]")

                # D. 先読み連続朗読の実行
                def on_sentence(idx: int, item):
                    char_tag = f"[bold magenta]{item.speaker_name}[/bold magenta]（{item.voice_character}）"
                    console.print(f"  ▶ [{idx+1}/{len(routed_items)}] {char_tag}: {item.text}")

                page_finished_event = asyncio.Event()
                def on_finish():
                    page_finished_event.set()

                # 朗読開始
                read_task = asyncio.create_task(
                    pipeline.read_sentences(
                        routed_items,
                        on_sentence_start=on_sentence,
                        on_page_finished=on_finish
                    )
                )

                await page_finished_event.wait()
                await read_task

                if self.stop_requested:
                    break

                # E. 自動ページめくり
                console.print(f"[bold cyan]⏩ ページ内の朗読完了。Kindleを自動で次ページへめくります...[/bold cyan]")
                turned = controller.turn_page_and_wait(
                    direction=turn_key,
                    timeout=page_turn_cfg.get("sync_timeout_sec", 3.0)
                )
                if turned:
                    console.print("[green]✓ ページめくり同期完了[/green]")
                else:
                    console.print("[dim]ページめくり完了（待機終了）[/dim]")

                await asyncio.sleep(page_turn_cfg.get("post_turn_delay_sec", 0.5))

        except (asyncio.CancelledError, KeyboardInterrupt):
            console.print("\n[yellow]朗読を中断しました。[/yellow]")
        finally:
            pipeline.stop()
            await vv.close()
            console.print("[bold green]プレイヤーを終了しました。[/bold green]")

    def stop(self):
        self.stop_requested = True
