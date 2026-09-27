import json
from pathlib import Path
from typing import Dict, Any

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """config.jsonを読み込み、存在しない場合はデフォルト値を返す"""
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Warning] config.json の読み込み失敗: {e}")

    # フォールバック用デフォルト設定
    return {
        "speaker_roles": {
            "老人": {"id": 53, "name": "麒ヶ島宗麟 (ノーマル)"},
            "若者": {"id": 12, "name": "白上虎太郎 (ふつう)"},
            "default": {"id": 2, "name": "四国めたん (ノーマル)"}
        },
        "voicevox": {
            "base_url": "http://localhost:50021",
            "speed_scale": 1.1,
            "pitch_scale": 0.0,
            "intonation_scale": 1.0
        },
        "page_turn": {
            "key": "left",
            "post_turn_delay_sec": 0.5,
            "sync_timeout_sec": 3.0
        },
        "ocr": {
            "pad_top_ratio": 0.08,
            "pad_bottom_ratio": 0.06,
            "pad_side_ratio": 0.08
        }
    }
