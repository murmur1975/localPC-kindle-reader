import asyncio
import sys
import argparse
from pathlib import Path

# WindowsコンソールのUTF-8化
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    # default デスクトップへ切り替え（エージェント・バックグラウンド実行対策）
    try:
        import ctypes
        user32 = ctypes.windll.user32
        DESKTOP_ALL = 0x01FF
        hdesk = user32.OpenDesktopW("default", 0, False, DESKTOP_ALL)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception:
        pass

# プロジェクトルートをインポートパスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import load_config
from src.orchestrator import KindleReaderOrchestrator

def main():
    parser = argparse.ArgumentParser(description="Kindle for PC AI朗読・自動ページめくりプレイヤー")
    parser.add_argument("--pages", "-p", type=int, default=None, help="朗読する最大ページ数 (指定なしで無限)")
    parser.add_argument("--key", "-k", type=str, default=None, choices=["left", "right", "pagedown"], help="ページめくりキー (縦書きは left, 横書きは right または pagedown)")
    args = parser.parse_args()

    config = load_config()
    if args.key:
        config.setdefault("page_turn", {})["key"] = args.key

    orchestrator = KindleReaderOrchestrator(config=config)
    asyncio.run(orchestrator.run(max_pages=args.pages))

if __name__ == "__main__":
    main()
