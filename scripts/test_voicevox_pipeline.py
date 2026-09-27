import asyncio
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

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
from src.voicevox_client import VoicevoxClient
from src.audio_player import AudioPlayer
from src.reading_pipeline import ReadingPipeline


console = Console(force_terminal=True, legacy_windows=False)

async def main():
    console.rule("[bold cyan]Phase 2: VOICEVOX 連続朗読パイプライン テスト[/bold cyan]")

    # 1. 抽出済みテキストの読み込み
    text_path = Path("scripts/captures/extracted_text.txt")
    if not text_path.exists():
        console.print(f"[red]テスト用テキストファイルが見つかりません: {text_path}[/red]")
        return

    with open(text_path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    console.print(f"[green]✓ キャプチャテキスト読み込み完了 ({len(raw_text)} 文字)[/green]")

    # 2. テキスト前処理・文分割
    cleaner = TextCleaner()
    sentences = cleaner.split_into_sentences(raw_text)
    
    console.print(f"[green]✓ 整形・文分割完了: 合計 {len(sentences)} 文[/green]")
    console.print("[dim]※ テストのため、先頭の 4 文を連続朗読します。[/dim]\n")

    test_sentences = sentences[:4]
    for i, s in enumerate(test_sentences):
        console.print(f"  [{i+1}] {s}")

    # 3. VOICEVOXクライアント・再生パイプラインの準備
    vv = VoicevoxClient()
    is_healthy = await vv.check_health()
    if not is_healthy:
        console.print("[bold red][X] VOICEVOX サーバー (http://localhost:50021) に接続できません。起動しているか確認してください。[/bold red]")
        return
    console.print("\n[green]✓ VOICEVOX サーバー接続確認 OK[/green]")

    # 話者: ずんだもん(ノーマル: id=3), 速度: 1.1倍
    speaker_id = 3
    player = AudioPlayer()
    pipeline = ReadingPipeline(vv, player, speaker_id=speaker_id, speed_scale=1.1)

    console.rule("[bold green]連続朗読スタート (先読みバッファリング稼働中)[/bold green]")

    def on_start(idx: int, text: str):
        console.print(f"[bold cyan]▶ 再生中 [{idx+1}/{len(test_sentences)}]:[/bold cyan] {text}")

    def on_finish():
        console.print("\n[bold green]★ 全文の朗読が完了しました！（次ページめくりトリガー到達）[/bold green]")

    await pipeline.read_sentences(
        test_sentences,
        on_sentence_start=on_start,
        on_page_finished=on_finish
    )

    await vv.close()

if __name__ == "__main__":
    asyncio.run(main())
