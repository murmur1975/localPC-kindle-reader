# localPC-kindle-reader

Windows版「Kindle for PC」上の電子書籍を画面OCRで自動抽出し、**VOICEVOX** を用いて自然な音声（対話キャラクター配役付き）で連続朗読しながら、読了時に **自動でページめくり** を行うローカル常駐型プレイヤーです。

---

## 🌟 特徴

- **超高速 OCR (Windows.Media.Ocr)**:
  - 外部の巨大モデルやTesseractのインストール不要。
  - Windows 10/11 標準の日本語OCRエンジンにより、わずか **約80ミリ秒** で縦書き・横書きを高精度抽出。
- **ダブルバッファリング（先読み合成）**:
  - 1文目を再生中に、バックグラウンド非同期タスクで次文・次々文の音声を事前生成。
  - 文間のブランク（待ち時間）が完全にゼロで、極めて滑らかな朗読を実現。
- **対話形式の自動配役・キャラクター掛け合い**:
  - 本文中の「老人」「若者」などの話者を自動判定。
  - 「老人」＝ **麒ヶ島宗麟**、「若者」＝ **白上虎太郎** など、キャラクターの声を自動で切り替えて掛け合い朗読。
- **自動ページめくり & 画面同期**:
  - ページ内の全文章の読了を検知した瞬間、Kindleウィンドウへ安全にページ送りキー（`[←]` 等）を送信。
  - 次のページを即座に再キャプチャしてエンドレスに読書を継続。

---

## 🚀 クイックスタート

### 1. 事前準備
1. **VOICEVOX** を起動しておきます（デフォルト: `http://localhost:50021`）。
2. **Kindle for PC** を起動し、読みたい書籍を開いておきます。

### 2. 起動方法

#### 通常起動（全ページ連続読書）
```powershell
uv run python main.py
```

#### ページ数を指定して読書（例: 5ページだけ読む）
```powershell
uv run python main.py --pages 5
```

#### 横書き書籍の場合（めくりキーを右矢印またはPageDownにする）
```powershell
uv run python main.py --key right
# または
uv run python main.py --key pagedown
```

---

## ⚙️ 設定のカスタマイズ (`config.json`)

配役や話速、キーバインドは [`config.json`](./config.json) からいつでも変更できます。

```json
{
  "speaker_roles": {
    "老人": {
      "id": 53,
      "name": "麒ヶ島宗麟 (ノーマル)"
    },
    "若者": {
      "id": 12,
      "name": "白上虎太郎 (ふつう)"
    },
    "default": {
      "id": 2,
      "name": "四国めたん (ノーマル)"
    }
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
  }
}
```

※ VOICEVOX で利用可能な全話者と ID は、以下のコマンドで一覧確認できます：
```powershell
uv run python scripts/list_speakers.py
```
