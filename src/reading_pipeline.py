import asyncio
from typing import List, Optional, Callable, Any
from dataclasses import dataclass
from rich.console import Console

from src.voicevox_client import VoicevoxClient
from src.audio_player import AudioPlayer

console = Console(force_terminal=True, legacy_windows=False)

@dataclass
class QueuedSentence:
    item: Any             # SentenceItem または str
    page_num: int         # ページ番号
    index_in_page: int    # ページ内インデックス (1-indexed)
    total_in_page: int    # ページ内総文数
    global_index: int     # 全体インデックス

class ReadingPipeline:
    """ストリーミングフィード対応・先読み合成（ダブルバッファリング）連続朗読パイプライン"""

    def __init__(
        self,
        voicevox_client: VoicevoxClient,
        audio_player: AudioPlayer,
        speaker_id: int = 3,
        speed_scale: float = 1.1,
        lead_sentences_count: int = 2
    ):
        self.vv = voicevox_client
        self.player = audio_player
        self.speaker_id = speaker_id
        self.speed_scale = speed_scale
        self.lead_sentences_count = lead_sentences_count

        self._queue: List[QueuedSentence] = []
        self._audio_cache = {}  # global_index -> wav_bytes
        self._current_global_index = 0
        self._is_running = False
        self._stop_requested = False
        self._no_more_pages = False
        
        # 先行めくりトリガー管理
        self._triggered_pages = set()
        self._need_next_page_callback: Optional[Callable[[], None]] = None

    def feed_page_sentences(
        self,
        sentences: List[Any],
        page_num: int
    ):
        """新しいページの文リストをキューに追記"""
        total = len(sentences)
        start_idx = len(self._queue)
        for i, s in enumerate(sentences):
            g_idx = start_idx + i
            q_item = QueuedSentence(
                item=s,
                page_num=page_num,
                index_in_page=i + 1,
                total_in_page=total,
                global_index=g_idx
            )
            self._queue.append(q_item)

        # 追加投入されたら即座に先読みタスクを起動
        self._trigger_prefetch()

    def mark_no_more_pages(self):
        """これ以上のページ追加がないことを通知（末尾到達）"""
        self._no_more_pages = True

    def _trigger_prefetch(self):
        """先読み生成タスクをトリガー（現在位置から最大2つ先まで）"""
        if self._stop_requested:
            return
        curr = self._current_global_index
        for offset in range(3):
            target_idx = curr + offset
            if target_idx < len(self._queue) and target_idx not in self._audio_cache:
                asyncio.create_task(self._prefetch_sentence(target_idx))

    async def _prefetch_sentence(self, global_idx: int):
        """指定グローバルインデックスの音声をバックグラウンド事前生成"""
        if global_idx in self._audio_cache or global_idx >= len(self._queue) or self._stop_requested:
            return

        q_item = self._queue[global_idx]
        item = q_item.item
        if hasattr(item, "text"):
            text = item.text
            spk_id = item.speaker_id
        else:
            text = str(item)
            spk_id = self.speaker_id

        # 最大2回リトライ
        for attempt in range(2):
            try:
                wav = await self.vv.text_to_wav(text, speaker_id=spk_id, speed_scale=self.speed_scale)
                self._audio_cache[global_idx] = wav
                return
            except Exception as e:
                if attempt == 0:
                    await asyncio.sleep(0.2)
                else:
                    console.print(f"[red]先読み生成失敗 (文 {global_idx+1}): {e}[/red]")


    async def start_streaming(
        self,
        on_sentence_start: Optional[Callable[[QueuedSentence], None]] = None,
        on_need_next_page: Optional[Callable[[], None]] = None,
        on_all_finished: Optional[Callable[[], None]] = None
    ):
        """キューから連続して音声を取り出し、シームレスに再生し続けるメインループ"""
        self._is_running = True
        self._stop_requested = False
        self._current_global_index = 0
        self._need_next_page_callback = on_need_next_page

        while not self._stop_requested:
            # キューが空、または現在インデックスに追いついた場合
            if self._current_global_index >= len(self._queue):
                if self._no_more_pages:
                    # 全ページの全文章を読み終えた
                    break
                # 次のページが投入されるのを少し待機
                await asyncio.sleep(0.05)
                continue

            q_item = self._queue[self._current_global_index]
            g_idx = q_item.global_index

            # 先行ページめくりトリガーの判定
            # 「現ページの残り文数」が lead_sentences_count 以下になったら先行めくりを発火！
            rem_in_page = q_item.total_in_page - q_item.index_in_page
            if rem_in_page <= self.lead_sentences_count:
                if q_item.page_num not in self._triggered_pages:
                    self._triggered_pages.add(q_item.page_num)
                    if self._need_next_page_callback:
                        self._need_next_page_callback()

            # 先読みタスクを起動
            self._trigger_prefetch()

            # 音声の準備を待機
            while g_idx not in self._audio_cache and not self._stop_requested:
                await asyncio.sleep(0.03)

            if self._stop_requested:
                break

            wav = self._audio_cache.pop(g_idx)

            if on_sentence_start:
                on_sentence_start(q_item)

            # 再生完了待機イベント
            finished_event = asyncio.Event()
            loop = asyncio.get_running_loop()

            def _done():
                loop.call_soon_threadsafe(finished_event.set)

            # 音声再生開始（非同期）
            self.player.play_wav(wav, on_finished=_done, block=False)

            # 再生終了まで非同期待機（この間に次の文・次ページの先読みが裏で走る）
            while not finished_event.is_set():
                if self._stop_requested:
                    self.player.stop()
                    break
                await asyncio.sleep(0.03)

            self._current_global_index += 1

        self._is_running = False
        if not self._stop_requested and on_all_finished:
            on_all_finished()

    def stop(self):
        """朗読を停止"""
        self._stop_requested = True
        self.player.stop()
        self._is_running = False

    def pause(self):
        self.player.pause()

    def resume(self):
        self.player.resume()
