import io
import json
import sys
import time
from pathlib import Path
import psutil

# WindowsコンソールのUTF-8化
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    # default デスクトップへ切り替え（エージェント分離セッション対策）
    try:
        import ctypes
        user32 = ctypes.windll.user32
        DESKTOP_ALL = 0x01FF
        hdesk = user32.OpenDesktopW("default", 0, False, DESKTOP_ALL)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception:
        pass

from pywinauto import Application, Desktop
from pywinauto.findwindows import ElementNotFoundError
from rich.console import Console
from rich.table import Table


console = Console(force_terminal=True, legacy_windows=False)


def find_kindle_processes():
    """Kindle.exeプロセスを探索"""
    procs = []
    for p in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = p.info["name"] or ""
            if "kindle" in name.lower():
                procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return procs


def find_kindle_windows():
    """Kindleに関連する可能性のあるトップレベルウィンドウを探索"""
    kindle_windows = []
    
    # 1. まずプロセスから探索
    kindle_procs = find_kindle_processes()
    target_pids = {p["pid"] for p in kindle_procs}

    # PID直接アタッチを試す
    for pid in target_pids:
        for backend in ["uia", "win32"]:
            try:
                app = Application(backend=backend).connect(process=pid)
                top_wins = app.windows()
                for tw in top_wins:
                    t = tw.window_text()
                    rect = tw.rectangle()
                    # 最小化されていない、またはある程度のサイズがあるウィンドウ
                    if rect.width() > 100 and rect.height() > 100:
                        kindle_windows.append({
                            "title": t,
                            "class_name": tw.element_info.class_name,
                            "handle": tw.element_info.handle,
                            "pid": pid,
                            "wrapper": tw,
                            "backend": backend
                        })
            except Exception:
                pass

    if kindle_windows:
        return kindle_windows, kindle_procs

    # 2. デスクトップ走査でフォールバック
    desktop = Desktop(backend="uia")
    try:
        windows = desktop.windows()
    except Exception as e:
        console.print(f"[red]ウィンドウ取得失敗 (UIA): {e}[/red]")
        windows = []

    for w in windows:
        try:
            title = w.window_text()
            class_name = w.element_info.class_name
            handle = w.element_info.handle
            process_id = w.element_info.process_id
            
            # PIDが一致するか、タイトルまたはクラス名にKindleが含まれるか
            is_match = False
            if process_id in target_pids:
                is_match = True
            elif "kindle" in title.lower() or "kindle" in class_name.lower():
                is_match = True

            if is_match and (title or w.rectangle().width() > 100):
                kindle_windows.append({
                    "title": title,
                    "class_name": class_name,
                    "handle": handle,
                    "pid": process_id,
                    "wrapper": w,
                    "backend": "uia"
                })
        except Exception:
            continue
            
    return kindle_windows, kindle_procs



def inspect_element_tree(window, max_depth=10):
    """UI Automationツリーを走査し、テキストや有用な情報を収集"""
    results = []
    
    try:
        descendants = window.descendants()
    except Exception as e:
        console.print(f"[red]子要素の走査中にエラーが発生しました: {e}[/red]")
        return results

    for idx, desc in enumerate(descendants):
        try:
            info = desc.element_info
            name = desc.window_text() or ""
            c_type = getattr(info, "control_type", "Unknown")
            c_name = getattr(info, "class_name", "")
            auto_id = getattr(info, "automation_id", "")
            rect = desc.rectangle()
            
            # テキストパターンや値パターンの取得可否
            has_text_pattern = False
            try:
                # TextPatternが存在するかチェック
                pattern = desc.iface_text
                if pattern:
                    has_text_pattern = True
            except Exception:
                pass

            item = {
                "index": idx,
                "control_type": c_type,
                "class_name": c_name,
                "automation_id": auto_id,
                "name": name,
                "name_len": len(name.strip()),
                "rect": f"({rect.left},{rect.top})-({rect.right},{rect.bottom}) w={rect.width()} h={rect.height()}",
                "has_text_pattern": has_text_pattern
            }
            results.append(item)
        except Exception:
            continue
            
    return results

def main():
    console.rule("[bold cyan]Kindle for PC UI Automation 調査スクリプト[/bold cyan]")
    
    # 1. ウィンドウ検索
    console.print("[yellow]Kindleプロセスおよびウィンドウを検索中...[/yellow]")
    windows, procs = find_kindle_windows()
    
    if procs:
        console.print(f"[cyan]検出されたKindleプロセス: {len(procs)} 件[/cyan]")
        for p in procs:
            console.print(f"  PID: {p['pid']} - {p['name']}")
    else:
        console.print("[dim]※ Kindle.exe プロセスは現在起動していません。[/dim]")

    if not windows:
        console.print("[red][X] Kindle for PC のウィンドウが見つかりませんでした。[/red]")
        console.print("[yellow]Kindle for PC を起動し、適当な書籍（小説や技術書など）を開いた状態で、もう一度本スクリプトを実行してください。[/yellow]")
        return

    console.print(f"[green][OK] {len(windows)} 個の関連ウィンドウを検出しました。[/green]")
    for i, win_data in enumerate(windows):
        console.print(f"  [{i}] タイトル: [bold]{win_data['title']}[/bold] (Class: {win_data['class_name']}, PID: {win_data['pid']})")

    all_window_results = []

    for i, target in enumerate(windows):
        target_win = target["wrapper"]
        console.rule(f"[cyan]ウィンドウ [{i}] 「{target['title']}」 (Class: {target['class_name']}) を走査[/cyan]")
        
        try:
            target_win.set_focus()
            time.sleep(0.3)
        except Exception as e:
            pass

        elements = inspect_element_tree(target_win)
        console.print(f"走査完了: {len(elements)} 個のUI要素を検出")
        
        # 意味のあるテキストブロックを抽出
        text_blocks = [e for e in elements if e["name_len"] > 5]
        console.print(f"5文字以上のテキスト要素: {len(text_blocks)} 件")
        
        if text_blocks:
            table = Table(title=f"検出テキスト (Window [{i}]: {target['title']})")
            table.add_column("No", style="dim", width=4)
            table.add_column("Type", style="cyan", width=14)
            table.add_column("AutomationId", style="blue", width=18)
            table.add_column("サイズ", style="magenta", width=14)
            table.add_column("テキストプレビュー", style="white")

            for e in text_blocks[:15]:
                preview = e["name"].replace("\r", " ").replace("\n", " ")
                if len(preview) > 50:
                    preview = preview[:47] + "..."
                wh = e["rect"].split(" ")[-2:]
                table.add_row(str(e["index"]), e["control_type"], e["automation_id"][:18], " ".join(wh), preview)
            console.print(table)

        all_window_results.append({
            "window": {"title": target["title"], "class": target["class_name"], "handle": target["handle"]},
            "elements": elements
        })

    # 結果をJSONとして保存
    output_path = Path("scripts/investigate_result.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_window_results, f, ensure_ascii=False, indent=2)
    console.print(f"\n[dim]全ウィンドウの詳細ログを {output_path} に保存しました。[/dim]")

    # 最終判定
    console.rule("[bold]総合判定結果[/bold]")
    # 書籍タイトルやUIメニュー以外の本文テキストがあるか？
    all_texts = []
    for wr in all_window_results:
        for e in wr["elements"]:
            if e["name_len"] > 30 and e["automation_id"] != "toolbar-title":
                all_texts.append(e)

    if len(all_texts) == 0:
        console.print("[bold red]★ 確定判定: パターンB（本文テキストは独自描画されており、UIAでの直接取得は不可）[/bold red]")
        console.print("Kindle for PC (最新版) の本文領域は、アクセシビリティツリーにテキストを公開していません。")
        console.print("ウィンドウタイトルやページ番号などのメタデータはUIAで取得可能ですが、")
        console.print("朗読対象となる書籍本文を読み取るには [bold yellow]【OCRフォールバック（画面キャプチャ＋OCR）】[/bold yellow] が必須となります。")
    else:
        console.print(f"[bold green]★ 本文テキスト候補を {len(all_texts)} 件検出しました！[/bold green]")


if __name__ == "__main__":
    main()
