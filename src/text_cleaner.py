import re
from typing import List

class TextCleaner:
    """OCRテキストの整形および音声合成用文分割を行うクラス"""

    # 日本語文字種判定用正規表現
    # 漢字・ひらがな・カタカナ・全角記号
    JP_CHAR = r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\u3000-\u303F\uFF00-\uFFEF]'

    @classmethod
    def clean_ocr_spaces(cls, text: str) -> str:
        """
        Windows OCR特有の単語間・文字間空白を除去する。
        日本語文字に挟まれた半角スペースを除去し、英単語間のスペースは保持する。
        """
        # 日本語文字間のスペースを繰り返し除去
        pattern = re.compile(f'({cls.JP_CHAR})\\s+({cls.JP_CHAR})')
        cleaned = text
        while pattern.search(cleaned):
            cleaned = pattern.sub(r'\1\2', cleaned)
            
        # 句読点の直前のスペースも除去
        cleaned = re.sub(r'\s+([、。，．！？!?）])', r'\1', cleaned)
        # 括弧の直後のスペースも除去
        cleaned = re.sub(r'([（「『])\s+', r'\1', cleaned)
        
        return cleaned

    @classmethod
    def normalize_symbols(cls, text: str) -> str:
        """VOICEVOXが自然に読み上げられるように特殊記号を正規化"""
        # 全角ダッシュや長音の連続
        t = re.sub(r'[ー―─－]{2,}', '――', text)
        # 三連リーダーの連続
        t = re.sub(r'[・…]{2,}', '…', t)
        # 半角の!?を全角に
        t = t.replace('?', '？').replace('!', '！')
        # 改行の連続を単一改行に
        t = re.sub(r'\n{2,}', '\n', t)
        return t

    @classmethod
    def split_into_sentences(cls, text: str, max_len: int = 70) -> List[str]:
        """
        文章を適切な長さのセンテンス単位に分割する。
        句点、感嘆符、疑問符、改行で分割し、長すぎる場合は読点でも分割。
        """
        cleaned = cls.clean_ocr_spaces(text)
        normalized = cls.normalize_symbols(cleaned)

        # まず行・句点・感嘆符・疑問符で大まかに分割
        # 括弧内の文が分断されないように配慮しつつ分割
        raw_chunks = re.split(r'([。\n！？])', normalized)
        
        sentences = []
        current = ""
        
        for piece in raw_chunks:
            if not piece:
                continue
            if piece in ('。', '\n', '！', '？'):
                current += piece
                if current.strip():
                    sentences.append(current.strip())
                current = ""
            else:
                current += piece

        if current.strip():
            sentences.append(current.strip())

        # 長すぎる文を読点などで再分割
        refined_sentences = []
        for s in sentences:
            s_clean = s.replace('\n', ' ').strip()
            if not s_clean:
                continue
                
            if len(s_clean) > max_len:
                # 読点（、）で再分割
                sub_parts = re.split(r'([、])', s_clean)
                sub_curr = ""
                for part in sub_parts:
                    if part == '、':
                        sub_curr += part
                        if len(sub_curr) >= max_len // 2:
                            refined_sentences.append(sub_curr.strip())
                            sub_curr = ""
                    else:
                        sub_curr += part
                if sub_curr.strip():
                    refined_sentences.append(sub_curr.strip())
            else:
                refined_sentences.append(s_clean)

        return [s for s in refined_sentences if s.strip()]


if __name__ == "__main__":
    sample = """ら の 中 で 考 え を 生 み 出 す 能 力 な ど な い か ら で す よ 。
老 人 そ の 通 り だ 。 続 き を 聞 こ う 。
若 者 出 版 す る か 否 か と い う 決 定 権 は 、 未 だ に 主 殿 の 手 中 に あ り ま す 。"""
    
    cleaner = TextCleaner()
    sentences = cleaner.split_into_sentences(sample)
    for idx, s in enumerate(sentences):
        print(f"[{idx+1}] {s}")
