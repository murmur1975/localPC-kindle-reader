import asyncio
from typing import Dict, Any, Optional
import httpx

class VoicevoxClient:
    """VOICEVOX ローカルAPIと非同期通信を行うクライアント"""

    def __init__(self, base_url: str = "http://localhost:50021", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def check_health(self) -> bool:
        """VOICEVOXエンジンが起動しているか確認"""
        try:
            client = await self.get_client()
            res = await client.get("/version")
            return res.status_code == 200
        except Exception:
            return False

    async def get_speakers(self) -> list:
        """利用可能な話者一覧を取得"""
        client = await self.get_client()
        res = await client.get("/speakers")
        res.raise_for_status()
        return res.json()

    async def create_audio_query(
        self,
        text: str,
        speaker_id: int,
        speed_scale: float = 1.0,
        pitch_scale: float = 0.0,
        intonation_scale: float = 1.0
    ) -> Dict[str, Any]:
        """テキストからAudioQuery（音声合成用パラメータ辞書）を生成"""
        client = await self.get_client()
        params = {"text": text, "speaker": speaker_id}
        res = await client.post("/audio_query", params=params)
        res.raise_for_status()
        query = res.json()

        # パラメータ調整
        query["speedScale"] = speed_scale
        query["pitchScale"] = pitch_scale
        query["intonationScale"] = intonation_scale
        return query

    async def synthesize(self, query: Dict[str, Any], speaker_id: int) -> bytes:
        """AudioQueryを基に音声波形（WAV形式のバイナリ）を生成"""
        client = await self.get_client()
        params = {"speaker": speaker_id}
        res = await client.post("/synthesis", params=params, json=query)
        res.raise_for_status()
        return res.content

    async def text_to_wav(
        self,
        text: str,
        speaker_id: int = 3, # デフォルト: ずんだもん(ノーマル)
        speed_scale: float = 1.05
    ) -> bytes:
        """テキストから直接WAVバイナリを一括生成するショートカット"""
        query = await self.create_audio_query(text, speaker_id=speaker_id, speed_scale=speed_scale)
        return await self.synthesize(query, speaker_id=speaker_id)
