"""PreToolUse フック：SendUserFile で video/ の中のファイルを送るとき、番号付き（名前_v番号）でなければ止める。

ユーザーの手元で同じ名前のファイルが上書きされないようにするため（video/STYLE.md のファイル名のルール）。
止めたときは、video-handoff スキル（video/lib/handoff.py）で番号付きの写しを作ってから送るよう伝える。
"""
import json
import os
import re
import sys

data = json.load(sys.stdin)
files = (data.get("tool_input") or {}).get("files") or []
bad = []
for f in files:
    p = os.path.abspath(f)
    if f"{os.sep}video{os.sep}" not in p:
        continue  # 動画制作以外のファイルは対象外
    stem = os.path.splitext(os.path.basename(p))[0]
    if not re.search(r"_v\d+$", stem):
        bad.append(f)
prompts = [f for f in files if "image_prompts" in f and f"{os.sep}requests{os.sep}" not in os.path.abspath(f)]
if prompts:
    print("画像の指示書をそのまま送ることはできません: " + ", ".join(prompts)
          + "\n→ video-image-request スキル（python3 video/lib/image_request.py <エピソード> <依頼の名前> <番号…>）で、"
            "今回作る画像だけの依頼書（ZIP の依頼文つき）を作り、requests/ の依頼書を送ってください。", file=sys.stderr)
    sys.exit(2)
if bad:
    print("番号付きでないファイルは送れません（上書き防止のルール）: " + ", ".join(bad)
          + "\n→ video-handoff スキル（python3 video/lib/handoff.py <ファイル>）で番号付きの写しを作り、"
            "コミットしてから、写しのほうを送ってください。", file=sys.stderr)
    sys.exit(2)
sys.exit(0)
