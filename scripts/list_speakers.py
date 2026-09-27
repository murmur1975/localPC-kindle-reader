import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import requests
from rich.console import Console
from rich.table import Table

console = Console(force_terminal=True, legacy_windows=False)

def main():
    r = requests.get("http://localhost:50021/speakers")
    speakers = r.json()
    
    table = Table(title="VOICEVOX 利用可能話者一覧")
    table.add_column("話者名", style="cyan")
    table.add_column("スタイル・ID一覧", style="green")
    
    for s in speakers:
        styles = ", ".join([f"{st['name']}:{st['id']}" for st in s["styles"]])
        table.add_row(s["name"], styles)
        
    console.print(table)

if __name__ == "__main__":
    main()
