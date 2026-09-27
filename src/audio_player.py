import io
import threading
import time
from typing import Optional, Callable
import sounddevice as sd
import soundfile as sf
import numpy as np

class AudioPlayer:
    """WAVバイナリの再生・一時停止・停止および完了通知を管理するプレイヤー"""

    def __init__(self):
        self._current_stream: Optional[sd.OutputStream] = None
        self._is_playing = False
        self._is_paused = False
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # set() のときは再生中、clear() のときは一時停止
        self._lock = threading.Lock()
        self._play_thread: Optional[threading.Thread] = None

    @property
    def is_playing(self) -> bool:
        return self._is_playing and not self._is_paused

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    def play_wav(self, wav_bytes: bytes, on_finished: Optional[Callable[[], None]] = None, block: bool = False):
        """WAVバイナリを再生。block=Falseなら非同期でバックグラウンド再生"""
        self.stop()  # 前の再生があれば停止

        def _worker():
            with self._lock:
                self._is_playing = True
                self._is_paused = False
                self._stop_event.clear()
                self._pause_event.set()

            try:
                # メモリ上のWAVデータをロード
                with io.BytesIO(wav_bytes) as bio:
                    data, samplerate = sf.read(bio, dtype='float32')

                # チャンクサイズごとに再生し、一時停止・停止イベントを監視
                chunk_size = 2048
                stream = sd.OutputStream(
                    samplerate=samplerate,
                    channels=data.shape[1] if data.ndim > 1 else 1,
                    dtype='float32'
                )
                self._current_stream = stream

                with stream:
                    total_frames = len(data)
                    pos = 0

                    while pos < total_frames and not self._stop_event.is_set():
                        # 一時停止待機
                        self._pause_event.wait()
                        if self._stop_event.is_set():
                            break

                        end_pos = min(pos + chunk_size, total_frames)
                        chunk = data[pos:end_pos]
                        stream.write(chunk)
                        pos = end_pos

            except Exception as e:
                print(f"[AudioPlayer Error] {e}")
            finally:
                with self._lock:
                    self._is_playing = False
                    self._is_paused = False
                    self._current_stream = None

                if on_finished and not self._stop_event.is_set():
                    try:
                        on_finished()
                    except Exception as e:
                        print(f"[AudioPlayer Callback Error] {e}")

        self._play_thread = threading.Thread(target=_worker, daemon=True)
        self._play_thread.start()

        if block:
            self._play_thread.join()

    def pause(self):
        """一時停止"""
        if self._is_playing and not self._is_paused:
            self._is_paused = True
            self._pause_event.clear()

    def resume(self):
        """一時停止の解除"""
        if self._is_paused:
            self._is_paused = False
            self._pause_event.set()

    def stop(self):
        """完全停止"""
        self._stop_event.set()
        self._pause_event.set()  # pauseでブロックされている場合を解除
        if self._play_thread and self._play_thread.is_alive():
            self._play_thread.join(timeout=1.0)
        self._is_playing = False
        self._is_paused = False

    def wait_until_done(self, timeout: Optional[float] = None):
        """現在の再生が完了するまでブロック待機"""
        if self._play_thread and self._play_thread.is_alive():
            self._play_thread.join(timeout=timeout)
