import asyncio
import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table

# WindowsコンソールのUTF-8化
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# プロジェクトルートをインポートパスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.text_cleaner import TextCleaner
from src.speaker_router import DialogueSpeakerRouter
from src.voicevox_client import VoicevoxClient
from src.audio_player import AudioPlayer
from src.reading_pipeline import ReadingPipeline

console = Console(force_terminal=True, legacy_windows=False)

async def main():
    console.rule("[bold cyan]対話形式（老人 vs 若者）自動配役 朗読テスト[/bold cyan]")

    # 1. 抽出テキストの読み込み
    text_path = Path("scripts/captures/extracted_text.txt")
    if not text_path.exists():
        console.print(f"[red]テスト用テキストファイルが見つかりません: {text_path}[/red]")
        return

    with open(text_path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    # 2. テキスト整形 & 文分割
    cleaner = TextCleaner()
    sentences = cleaner.split_into_sentences(raw_text)

    # 3. 話者ルーティング（老人: ちび式じい(42), 若者: ずんだもん(3), 地の文: 四国めたん(2)）
    # ※青山龍星(13)に変更することも可能
    speaker_map = {
        "老人": (42, "ちび式じい"),
        "若者": (3, "ずんだもん"),
        "default": (2, "四国めたん")
    }
    router = DialogueSpeakerRouter(speaker_map=speaker_map)
    routed_items = router.route_sentences(sentences, strip_speaker_label=True)

    # 配役結果のプレビュー表示（先頭8文）
    test_items = routed_items[:8]
    
    table = Table(title="自動配役結果プレビュー (先頭8文)")
    table.add_column("No", style="dim", width=4)
    table.add_column("役割", style="yellow", width=8)
    table.add_column("担当キャラ (ID)", style="cyan", width=18)
    table.add_column("発話テキスト", style="white")

    for i, it in enumerate(test_items):
        table.add_row(str(i+1), it.speaker_name, f"{it.voice_character} ({it.speaker_id})", it.text)

    console.print(table)

    # 4. VOICEVOXクライアント準備
    vv = VoicevoxClient()
    if not await vv.check_health():
        console.print("[red][X] VOICEVOX サーバーに接続できませんでした。[/red]")
        return

    player = AudioPlayer()
    pipeline = ReadingPipeline(vv, player, speed_scale=1.1)

    console.rule("[bold green]配役朗読スタート (先読みバッファリング中)[/bold green]")

    def on_start(idx: int, item):
        char_tag = f"[bold magenta]{item.speaker_name}[/bold magenta]（{item.voice_character}）"
        console.print(f"▶ [{idx+1}/{len(test_items)}] {char_tag}: {item.text}")

    def on_finish():
        console.print("\n[bold green]★ 全対話の朗読が完了しました！[/bold green]")

    await pipeline.read_sentences(
        test_items,
        on_sentence_start=on_start,
        on_page_finished=on_finish
    )

    await vv.close()

if __name__ == "__main__":
    asyncio.run(main())
