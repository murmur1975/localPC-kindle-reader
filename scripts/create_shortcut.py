import os
import sys
from pathlib import Path

# WindowsコンソールのUTF-8化
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def create_shortcut():
    try:
        import win32com.client
    except ImportError:
        print("[ERROR] pywin32 がインストールされていません。")
        return False

    project_root = Path(__file__).resolve().parent.parent
    target_bat = project_root / "run.bat"
    
    if not target_bat.exists():
        print(f"[ERROR] 起動バッチが見つかりません: {target_bat}")
        return False

    try:
        ws = win32com.client.Dispatch("WScript.Shell")
        desktop = ws.SpecialFolders("Desktop")
        shortcut_path = os.path.join(desktop, "Kindle AI朗読プレイヤー.lnk")

        shortcut = ws.CreateShortcut(shortcut_path)
        shortcut.TargetPath = str(target_bat)
        shortcut.WorkingDirectory = str(project_root)
        shortcut.Description = "Kindle for PC AI朗読・自動ページめくりプレイヤー"
        # 本のアイコン (shell32.dll, 278) または音声アイコン
        shortcut.IconLocation = "shell32.dll,278"
        shortcut.Save()

        print("=========================================================")
        print("  デスクトップにショートカットを作成しました！")
        print(f"  場所: {shortcut_path}")
        print("=========================================================")
        return True
    except Exception as e:
        print(f"[ERROR] ショートカット作成中にエラーが発生しました: {e}")
        return False

if __name__ == "__main__":
    create_shortcut()
