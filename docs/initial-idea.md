Kindle for PC AI朗読・自動ページめくりプレイヤー 仕様書 (Phase 1: 調査・PoCフェーズ)
1. 概要

本プロジェクトの目的は、Windows版「Kindle for PC」の画面表示およびテキスト要素を自動で抽出し、ローカルで稼働する VOICEVOX API を用いて自然な音声で連続朗読させつつ、読了時に 自動でページめくり（キーボードイベント等） を行うデスクトップアプリケーション（Python製）を開発することである。

本仕様書は、最初に行う 「Phase 1: Kindle for PCのアクセシビリティAPI（UI Automation）によるテキスト抽出の検証・調査」 の実装・検証タスクを定義する。
2. ゴール（Phase 1の成果物）

    Windows上の「Kindle for PC」ウィンドウをPythonスクリプトから検知する。

    Microsoft UI Automation（または pywinauto 等）を用いて、Kindleのビューポート内にあるテキスト要素（テキストブロック）を直接取得できるか検証する。

    直接取得が困難な場合（カスタム描画されている等の理由）、OCR（pytesseract / EasyOCR）フォールバックの必要性を判断するための検証レポートを出力する。

3. 技術スタック（予定）

    言語: Python 3.10+

    Windows操作・UI自動化: pywinauto, comtypes, または標準の pywin32 (UI Automation API wrapper)

    音声合成: VOICEVOX ローカルAPI (http://localhost:50021)

    音声再生: pyaudio または pygame

    OCR（代替・フォールバック用）: pytesseract または EasyOCR

4. Phase 1 実装タスク：アクセシビリティAPI調査スクリプト

AIエージェント（Antigravity）は、以下の手順およびスクリプトを実行し、Kindle for PCからテキストが取得可能か検証する。
タスク 1-1: ウィンドウハンドルの取得とプロセス確認

    「Kindle for PC」のプロセス名（例: Kindle.exe またはウィンドウタイトル）を検出し、そのウィンドウハンドル（HWND）およびUI Automationの要素ツリー（Root Element）にアクセスできるか確認する。

タスク 1-2: UI Automationによるテキスト探索

    UI Automationのツリーを走査し、テキストコントロール（Text Pattern または Value Pattern）を持つ要素が存在するか、あるいは単一のカスタム描画ウィンドウ（Canvas/Document等）として扱われているかを調査する。

実装予定コード（検証用ポータブルスクリプト: investigate_kindle.py）

AIは以下のスクリプトを生成・配置し、実行結果を検証・報告すること。
Python

import time
from pywinauto import Application
from pywinauto.findwindows import ElementNotFoundError


def investigate_kindle_uia():
  print('=== Kindle for PC UI Automation Investigation ===')

  try:
    # Kindle for PCのプロセスにアタッチを試みる（起動している前提）
    # ウィンドウタイトルやプロセス名で特定
    app = Application(backend='uia').connect(
        title_re='.*Kindle.*', timeout=5
    )
    window = app.window(title_re='.*Kindle.*')
    window.set_focus()

    print(f'[+] Found Window: {window.window_text()}')
    print(f'[+] Control Type: {window.element_info.control_type}')

    # UI Automationを使って子要素のテキストを再帰的、あるいはセレクタで探す
    print('[*] Scanning text elements in Kindle window...')
    descendants = window.descendants()

    text_found_count = 0
    for idx, desc in enumerate(descendants):
      try:
        # テキストを持つ、あるいはValueを持つコントロールを探索
        name = desc.window_text()
        if name and len(name.strip()) > 0:
          # メニューやUIパーツ以外の長文・本文になり得る要素をフィルタリング
          if len(name.strip()) > 5:
            print(f'  [{idx}] Type: {desc.element_info.control_type}')
            print(f'       Text: {name[:50]}...')
            text_found_count += 1
      except Exception:
        continue

    print(f'\n[+] Scan completed. Found {text_found_count} potential text blocks.')

    if text_found_count == 0:
      print(
          '[-] WARNING: No text elements found via UIA. Kindle for PC might'
          ' be using hardware-accelerated custom rendering (requires OCR'
          ' fallback).'
      )
    else:
      print(
          '[+] SUCCESS: Text elements are accessible via UIA! Direct text'
          ' extraction is feasible.'
      )

  except ElementNotFoundError:
    print(
        '[-] ERROR: Kindle for PC window not found. Please make sure the app'
        ' is running.'
    )
  except Exception as e:
    print(f'[-] ERROR: An unexpected error occurred: {e}')


if __name__ == '__main__':
  investigate_kindle_uia()

5. 次のステップ（Phase 2へ向けた条件分岐）

    パターンA（UIAでテキストが取れた場合）：

        テキスト要素の変更を監視し、リアルタイムで次ページのテキストを配列・キューに格納するモジュールの実装へ進む。

    パターンB（UIAでテキストが取れなかった・描画領域だけの場合）：

        指定した読書エリアのスクリーンショットを定期撮影し、EasyOCR でテキスト化するパイプラインの実装へ切り替える。

この仕様書をAntigravityに渡し、まずは調査スクリプトの実行と結果の分析から指示してみてください。進め方で調整したい点があればいつでもおっしゃってください！