"""制作環境の確認。足りないものと、直し方を表示する。

    python3 video/lib/env_check.py

終了コード 0 = すべてそろっている、1 = 足りないものがある。
Docker デーモンは、このスクリプトからは起動しない（コマンドの終了と一緒に止まるため）。
止まっていたら、Claude は Bash の run_in_background で `dockerd` を起動し、そのあと
`docker start vv`（初回は docker run）で VOICEVOX を起動する。
"""
import json
import os
import shutil
import subprocess
import sys
import urllib.request

OK, NG = "OK", "NG"
results = []


def check(name, ok, fix=""):
    results.append((name, ok, fix))


def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except Exception as e:  # noqa: BLE001
        return None


# VOICEVOX
try:
    v = urllib.request.urlopen("http://127.0.0.1:50021/version", timeout=5).read().decode()
    check(f"VOICEVOX エンジン（{v.strip()}）", True)
except Exception:  # noqa: BLE001
    r = run(["docker", "info"])
    if r is None or r.returncode != 0:
        check("Docker デーモン", False,
              "Bash の run_in_background で `dockerd` を起動する（通常の Bash では止まってしまう）")
    check("VOICEVOX エンジン", False,
          "`docker start vv`。コンテナがなければ `docker run -d --name vv --restart unless-stopped "
          "-p 50021:50021 voicevox/voicevox_engine:cpu-latest`")

# Python のライブラリ
for mod, pip in (("cairo", "pycairo"), ("numpy", "numpy"), ("PIL", "pillow")):
    try:
        __import__(mod)
        check(f"Python: {mod}", True)
    except ImportError:
        check(f"Python: {mod}", False, f"pip install {pip}")

# コマンド
for cmd in ("ffmpeg", "ffprobe", "node"):
    check(f"コマンド: {cmd}", shutil.which(cmd) is not None, f"apt-get install -y {cmd}")

# 日本語フォント
r = run(["fc-list", ":lang=ja", "family"])
has_noto = r is not None and "Noto Sans CJK JP" in (r.stdout or "")
check("フォント: Noto Sans CJK JP", has_noto, "apt-get install -y fonts-noto-cjk")

# 素材（リポジトリ外）
root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
base = os.path.join(root, "characters", "akihiro", "images", "akihiro_base_v2.png")
check("素材: アキヒロのコミカル版の基準画像", os.path.exists(base),
      "リポジトリ外の素材。ユーザーに akihiro_base_v2.png（画風の見本①のアキヒロ）をアップロードしてもらい、"
      "video/characters/akihiro/images/ に置く")

width = max(len(n) for n, _, _ in results)
bad = 0
for name, ok, fix in results:
    print(f"[{OK if ok else NG}] {name}")
    if not ok:
        bad += 1
        print(f"      → {fix}")
print(f"\n足りないもの: {bad} 件")
sys.exit(1 if bad else 0)
