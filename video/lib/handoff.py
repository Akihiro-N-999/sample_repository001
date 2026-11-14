"""ユーザーにファイルを渡す前の準備。番号付きの写しを作り、送るべきパスを表示する。

    python3 video/lib/handoff.py <ファイル> [<ファイル> ...]

- md（plan.md、script.md など、エピソードのフォルダにある作業用のファイル）
  → 同じフォルダの versions/<名前>_v<番号>.md に写しを作る。最新の写しと中身が同じなら作らずに、それを使う。
- 番号付きでない成果物（video/out/ の画像・動画・音声など）
  → 次の番号の名前で写しを作る（元のファイルは残す）。
- すでに番号付きのファイル → そのまま。

最後に「送るファイル」の一覧を表示する。Claude は表示されたパスを SendUserFile で送り、
md の写しは git add・commit・push してから送る（スキル video-handoff）。
"""
import filecmp
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from core import _versions, latest, next_version  # noqa: E402

VER = re.compile(r"_v\d+$")


def handoff(path):
    path = os.path.normpath(path)
    stem, ext = os.path.splitext(os.path.basename(path))
    if VER.search(stem):
        return path, "番号付き（そのまま）"
    if ext == ".md":
        vdir = os.path.join(os.path.dirname(path), "versions")
        os.makedirs(vdir, exist_ok=True)
        target = os.path.join(vdir, stem + ext)
        vs = _versions(target)
        if vs and filecmp.cmp(vs[-1][1], path, shallow=False):
            return vs[-1][1], "最新の写しと同じ（新しく作らない）"
        dst = next_version(target)
        shutil.copy2(path, dst)
        return dst, "写しを作成"
    dst = next_version(path)
    shutil.copy2(path, dst)
    return dst, "番号付きの写しを作成"


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    out = []
    for p in sys.argv[1:]:
        if not os.path.exists(p):
            print(f"[NG] ない: {p}")
            continue
        dst, note = handoff(p)
        out.append(dst)
        print(f"[OK] {p} → {dst}（{note}）")
    print("\n送るファイル:")
    for d in out:
        print(os.path.abspath(d))


if __name__ == "__main__":
    main()
