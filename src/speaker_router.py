import re
from typing import Tuple, Dict, Optional
from dataclasses import dataclass

@dataclass
class SentenceItem:
    text: str              # 実際に発話するテキスト
    raw_text: str          # 元のテキスト
    speaker_id: int        # VOICEVOX 話者ID
    speaker_name: str      # 話者名（老人、若者、ナレーションなど）
    voice_character: str   # VOICEVOX キャラクター名（ちび式じい、ずんだもん等）

class DialogueSpeakerRouter:
    """対話形式のテキストから話者を自動判定し、VOICEVOXの音声IDを割り当てるルーター"""

    def __init__(self, speaker_map: Optional[Dict[str, Tuple[int, str]]] = None):
        """
        speaker_map: ロール名 -> (話者ID, VOICEVOXキャラ名)
        """
        if speaker_map:
            self.speaker_map = speaker_map
        else:
            # デフォルト設定: 麒ヶ島宗麟(53), 白上虎太郎(12), 四国めたん(2)
            self.speaker_map = {
                "老人": (53, "麒ヶ島宗麟"),
                "若者": (12, "白上虎太郎"),
                "default": (2, "四国めたん")
            }
        self.current_role = "default"

    @classmethod
    def from_config(cls, config: dict) -> "DialogueSpeakerRouter":
        """config.json の設定からルーターをインスタンス化"""
        roles_cfg = config.get("speaker_roles", {})
        mapping = {}
        for role, data in roles_cfg.items():
            spk_id = data.get("id", 2)
            spk_name = data.get("name", role)
            mapping[role] = (spk_id, spk_name)
        return cls(speaker_map=mapping)


    def reset(self):
        """ステートリセット"""
        self.current_role = "default"

    def route_sentence(self, sentence: str, strip_speaker_label: bool = True) -> SentenceItem:
        """
        1つのセンテンスから話者を判定し、発話テキストと話者IDを返す。
        strip_speaker_label=True の場合、冒頭の「老人」「若者」をスキップして台詞のみ読ませる。
        """
        s = sentence.strip()

        # 冒頭の話者タグ検出 (「老人」「若者」など)
        # 例: "老人 その通りだ。" / "老人キミを許すかって？" / "若者 出版するか否か..."
        matched_role = None
        cleaned_text = s

        for role in self.speaker_map.keys():
            if role == "default":
                continue
            # 正規表現: 冒頭の "老人" または "若者" + 任意の空白やコロン
            pattern = re.compile(rf'^{role}[\s:：　]*(.*)', re.DOTALL)
            m = pattern.match(s)
            if m:
                matched_role = role
                if strip_speaker_label:
                    # ラベルを除去した残りの発話テキスト
                    cleaned_text = m.group(1).strip()
                    # もしラベルだけだった場合はそのまま読む
                    if not cleaned_text:
                        cleaned_text = s
                break

        if matched_role:
            self.current_role = matched_role
        
        # 現在のロールの話者IDを取得
        spk_info = self.speaker_map.get(self.current_role, self.speaker_map["default"])
        speaker_id, char_name = spk_info

        return SentenceItem(
            text=cleaned_text if cleaned_text else s,
            raw_text=s,
            speaker_id=speaker_id,
            speaker_name=self.current_role,
            voice_character=char_name
        )

    def route_sentences(self, sentences: list[str], strip_speaker_label: bool = True) -> list[SentenceItem]:
        """センテンスリスト全体に対して順次話者を割り当て"""
        items = []
        for s in sentences:
            item = self.route_sentence(s, strip_speaker_label=strip_speaker_label)
            items.append(item)
        return items
