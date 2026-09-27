import asyncio
import ctypes
from ctypes import wintypes
import time
from typing import Optional, Dict, Any, List
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.config import load_config
from src.text_cleaner import TextCleaner
from src.speaker_router import DialogueSpeakerRouter
from src.voicevox_client import VoicevoxClient
from src.audio_player import AudioPlayer
from src.reading_pipeline import ReadingPipeline, QueuedSentence
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
            
            if cname == "Microsoft.UI.Windowing.Window" and "kindle" in title.lower() and w > 400 and h > 400:
                candidates.append((hwnd, w * h))
        return True

    user32.EnumWindows(WNDENUM(enum_cb), 0)
    if candidates:
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]
    return None


class KindleReaderOrchestrator:
    """先行ページめくり＆シームレス連続朗読を統括するメインエンジン"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or load_config()
        self.stop_requested = False
        self.last_page_text = ""

    async def run(self, max_pages: Optional[int] = None):
        console.rule("[bold cyan]Kindle for PC AI 朗読 & 先行ページめくりシームレスプレイヤー[/bold cyan]")

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

        page_turn_cfg = self.config.get("page_turn", {})
        turn_key = page_turn_cfg.get("key", "left")
        lead_sentences = page_turn_cfg.get("lead_sentences_count", 2)

        pipeline = ReadingPipeline(
            vv,
            player,
            speed_scale=vv_cfg.get("speed_scale", 1.1),
            lead_sentences_count=lead_sentences
        )

        # 配役設定サマリー表示
        table = Table(title="現在の配役設定")
        table.add_column("役割", style="yellow")
        table.add_column("担当キャラクター名", style="cyan")
        table.add_column("話者ID", style="green")
        for role, (sid, sname) in router.speaker_map.items():
            table.add_row(role, sname, str(sid))
        console.print(table)
        console.print(f"[dim]先行ページめくり設定: 残り {lead_sentences} 文の時点で次ページを取得[/dim]")

        console.print("\n[bold green]=== シームレス連続読書ループを開始します ===[/bold green]")
        console.print("[dim]※ 中断したい場合は Ctrl+C を押してください。[/dim]\n")

        # 4. 初回ページ (Page 1) のキャプチャ & OCR
        current_page_idx = 1
        footer_info = controller.get_footer_info() or f"Page {current_page_idx}"
        console.rule(f"[bold yellow]📖 読書開始: {footer_info}[/bold yellow]")

        controller.force_foreground()
        ocr_result = await ocr.extract_text()
        raw_text = ocr_result["text"]
        self.last_page_text = raw_text

        sentences = cleaner.split_into_sentences(raw_text)
        if not sentences:
            console.print("[yellow]初期ページに本文テキストが検出されませんでした。[/yellow]")
            return

        routed_items = router.route_sentences(sentences, strip_speaker_label=True)
        console.print(f"[dim]Page {current_page_idx}: {len(routed_items)} 文をキューに投入 (OCR: {ocr_result['elapsed_ms']:.1f}ms)[/dim]")
        pipeline.feed_page_sentences(routed_items, page_num=current_page_idx)

        # 先行めくりトリガーイベント
        need_next_page_event = asyncio.Event()

        def on_need_next_page():
            need_next_page_event.set()

        def on_sentence(q_item: QueuedSentence):
            it = q_item.item
            char_tag = f"[bold magenta]{it.speaker_name}[/bold magenta]（{it.voice_character}）"
            console.print(f"  ▶ [Page {q_item.page_num} | {q_item.index_in_page}/{q_item.total_in_page}] {char_tag}: {it.text}")

        # 再生タスクをバックグラウンド起動
        playback_task = asyncio.create_task(
            pipeline.start_streaming(
                on_sentence_start=on_sentence,
                on_need_next_page=on_need_next_page
            )
        )

        try:
            # ページ供給ループ (Producer)
            while not self.stop_requested:
                if max_pages and current_page_idx >= max_pages:
                    console.print(f"\n[cyan]指定ページ数 ({max_pages} ページ) の供給を完了しました。残りの文を再生して終了します...[/cyan]")
                    pipeline.mark_no_more_pages()
                    break

                # 再生キューから「先行めくりが必要」の通知を待つ
                await need_next_page_event.wait()
                need_next_page_event.clear()

                if self.stop_requested or (max_pages and current_page_idx >= max_pages):
                    pipeline.mark_no_more_pages()
                    break

                # 先行ページめくり発火！
                current_page_idx += 1
                console.print(f"\n[bold cyan]⏩ [先行めくり発火] 現在の文を再生中に、Kindleを次ページへ先行送りします...[/bold cyan]")

                # キー送信＆同期
                controller.force_foreground()
                turned = controller.turn_page_and_wait(
                    direction=turn_key,
                    timeout=page_turn_cfg.get("sync_timeout_sec", 3.0)
                )

                await asyncio.sleep(page_turn_cfg.get("post_turn_delay_sec", 0.4))

                # 新ページのキャプチャ & 高速OCR
                ocr_result = await ocr.extract_text()
                new_text = ocr_result["text"]

                # 重複判定（前ページと同じテキストなら末尾）
                if new_text == self.last_page_text:
                    console.print("[yellow]前ページと同じテキストです。書籍末尾に到達しました。[/yellow]")
                    pipeline.mark_no_more_pages()
                    break

                self.last_page_text = new_text
                new_sentences = cleaner.split_into_sentences(new_text)

                if not new_sentences:
                    console.print("[yellow]新ページにテキストがありませんでした（図版または空白）。[/yellow]")
                    pipeline.mark_no_more_pages()
                    break

                new_routed = router.route_sentences(new_sentences, strip_speaker_label=True)
                console.print(f"[bold green]✓ Page {current_page_idx} の事前OCR完了: {len(new_routed)} 文をシームレス追加！ (OCR: {ocr_result['elapsed_ms']:.1f}ms)[/bold green]")
                
                # キューにシームレス追記（この瞬間に新ページの先読み合成が裏で走り始める！）
                pipeline.feed_page_sentences(new_routed, page_num=current_page_idx)

            # 全再生の完了を待機
            await playback_task
            console.print("\n[bold green]★ すべての朗読がシームレスに完了しました！[/bold green]")

        except (asyncio.CancelledError, KeyboardInterrupt):
            console.print("\n[yellow]朗読を中断しました。[/yellow]")
        finally:
            pipeline.stop()
            if not playback_task.done():
                playback_task.cancel()
            await vv.close()
            console.print("[bold green]プレイヤーを終了しました。[/bold green]")

    def stop(self):
        self.stop_requested = True
