import asyncio
import threading
from typing import List, Optional, Callable
from rich.console import Console

from src.voicevox_client import VoicevoxClient
from src.audio_player import AudioPlayer

console = Console(force_terminal=True, legacy_windows=False)

class ReadingPipeline:
    """先読み合成（ダブルバッファリング）によるシームレス連続朗読パイプライン"""

    def __init__(self, voicevox_client: VoicevoxClient, audio_player: AudioPlayer, speaker_id: int = 3, speed_scale: float = 1.05):
        self.vv = voicevox_client
        self.player = audio_player
        self.speaker_id = speaker_id
        self.speed_scale = speed_scale
        
        self._is_running = False
        self._current_index = 0
        self._sentences: List[str] = []
        self._audio_cache = {}  # index -> wav_bytes
        self._stop_requested = False

    async def _prefetch_sentence(self, index: int):
        """指定インデックスの音声をバックグラウンドで事前生成"""
        if index in self._audio_cache or index >= len(self._sentences) or self._stop_requested:
            return

        item = self._sentences[index]
        if hasattr(item, "text"):
            text = item.text
            spk_id = item.speaker_id
        else:
            text = str(item)
            spk_id = self.speaker_id

        try:
            wav = await self.vv.text_to_wav(text, speaker_id=spk_id, speed_scale=self.speed_scale)
            self._audio_cache[index] = wav
        except Exception as e:
            console.print(f"[red]先読み生成失敗 (文 {index+1}): {e}[/red]")

    async def read_sentences(
        self,
        sentences: list,
        on_sentence_start: Optional[Callable[[int, any], None]] = None,
        on_page_finished: Optional[Callable[[], None]] = None
    ):

        """センテンス配列を先読みバッファリングしながら連続朗読"""
        self._sentences = sentences
        self._audio_cache.clear()
        self._current_index = 0
        self._is_running = True
        self._stop_requested = False

        if not sentences:
            if on_page_finished:
                on_page_finished()
            return

        # 1. 最初の1文目と2文目を事前生成
        t_pre = []
        t_pre.append(asyncio.create_task(self._prefetch_sentence(0)))
        if len(sentences) > 1:
            t_pre.append(asyncio.create_task(self._prefetch_sentence(1)))
        await asyncio.gather(*t_pre)

        # 2. 順次再生ループ
        for idx in range(len(sentences)):
            if self._stop_requested:
                break

            self._current_index = idx
            item = sentences[idx]
            text = item.text if hasattr(item, "text") else str(item)

            # 次の文（2つ先まで）の先読みタスクを非同期起動
            if idx + 1 < len(sentences):
                asyncio.create_task(self._prefetch_sentence(idx + 1))
            if idx + 2 < len(sentences):
                asyncio.create_task(self._prefetch_sentence(idx + 2))

            # 現在の文の音声が準備できているか確認（未完了なら待機）
            while idx not in self._audio_cache and not self._stop_requested:
                await asyncio.sleep(0.05)

            if self._stop_requested:
                break

            wav = self._audio_cache.pop(idx)

            if on_sentence_start:
                on_sentence_start(idx, item)


            # 再生完了を非同期で待機するためのイベント

            finished_event = asyncio.Event()
            loop = asyncio.get_running_loop()

            def _done():
                loop.call_soon_threadsafe(finished_event.set)

            # 音声再生
            self.player.play_wav(wav, on_finished=_done, block=False)
            
            # 再生終了まで非同期待機（この間に次の先読みが走る）
            while not finished_event.is_set():
                if self._stop_requested:
                    self.player.stop()
                    break
                await asyncio.sleep(0.05)

        self._is_running = False

        # 全文読了コールバック
        if not self._stop_requested and on_page_finished:
            on_page_finished()

    def stop(self):
        """朗読を中断・停止"""
        self._stop_requested = True
        self.player.stop()
        self._is_running = False

    def pause(self):
        """一時停止"""
        self.player.pause()

    def resume(self):
        """再開"""
        self.player.resume()
