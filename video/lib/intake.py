"""Gemini などで作った画像を受け取り、決まったファイル名（名前_v番号）で保存する。

Gemini からダウンロードした画像は名前がばらばら（例: Gemini_Generated_Image_xxxx.png）なので、
人に名前を付け直してもらわず、受け取る側で付ける。2段階で使う。

1. 一覧を作る（どの画像が何かを見て判断するため）
    python3 video/lib/intake.py list <ZIPかフォルダかファイル…>
   → video/out/intake/<日時>/ に展開し、番号付きの一覧画像 contact.png と、
     対応表のひな形 mapping.json（番号 → 保存名。保存名は空欄）を作る。

2. 対応表を埋めて保存する
    python3 video/lib/intake.py apply video/out/intake/<日時>/mapping.json
   mapping.json の各項目に "name"（番号なしの保存名。例 "shovel_boss_base.png"）と
   "dest"（保存先フォルダ）を書いておくと、既存の版の次の番号（_v1, _v2 …）で保存する。
   上書きはしない。保存した結果は同じフォルダの applied.txt に残る。
"""
import datetime
import json
import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from core import next_version  # noqa: E402

OUT = os.path.join(HERE, "..", "out", "intake")
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")


def collect(srcs, work):
    """ZIP・フォルダ・ファイルから画像を work/raw に集める。ZIP の中のパスは信用せず、名前だけ使う。"""
    raw = os.path.join(work, "raw")
    os.makedirs(raw, exist_ok=True)
    files = []

    def add(name, data):
        base = os.path.basename(name)
        if not base.lower().endswith(IMG_EXT) or base.startswith("."):
            return
        dst = os.path.join(raw, f"{len(files) + 1:02d}_{base}")
        with open(dst, "wb") as f:
            f.write(data)
        files.append(dst)

    for s in srcs:
        if zipfile.is_zipfile(s):
            with zipfile.ZipFile(s) as z:
                for info in sorted(z.infolist(), key=lambda i: i.filename):
                    if not info.is_dir():
                        add(info.filename, z.read(info))
        elif os.path.isdir(s):
            for root, _, names in os.walk(s):
                for n in sorted(names):
                    with open(os.path.join(root, n), "rb") as f:
                        add(n, f.read())
        else:
            with open(s, "rb") as f:
                add(s, f.read())
    return files


def contact_sheet(files, path, cell=360):
    from PIL import Image, ImageDraw, ImageFont
    cols = 4
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 40)), "white")
    d = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 26)
    for i, f in enumerate(files):
        im = Image.open(f).convert("RGB")
        w, h = im.size
        im.thumbnail((cell - 16, cell - 16))
        x, y = (i % cols) * cell, (i // cols) * (cell + 40)
        sheet.paste(im, (x + (cell - im.width) // 2, y + 40))
        d.text((x + 8, y + 6), f"{i + 1}  ({w}×{h})", fill="black", font=font)
    sheet.save(path)


def cmd_list(srcs):
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    work = os.path.join(OUT, stamp)
    files = collect(srcs, work)
    if not files:
        raise SystemExit("画像が見つかりません")
    contact_sheet(files, os.path.join(work, "contact.png"))
    mapping = [{"no": i + 1, "file": f, "original": os.path.basename(f)[3:], "name": "", "dest": ""}
               for i, f in enumerate(files)]
    mp = os.path.join(work, "mapping.json")
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=1)
    print(f"{len(files)} 枚 → 一覧 {os.path.join(work, 'contact.png')}")
    print(f"対応表のひな形 → {mp}（name と dest を埋めて apply）")


def cmd_apply(mp):
    with open(mp, encoding="utf-8") as f:
        mapping = json.load(f)
    log = []
    for m in mapping:
        if not m.get("name"):
            log.append(f"#{m['no']} 保存しない（name が空）: {m['original']}")
            continue
        dest_dir = m.get("dest") or "."
        os.makedirs(dest_dir, exist_ok=True)
        src = m["file"]
        name = m["name"]
        ext = os.path.splitext(src)[1].lower()
        convert = ext == ".webp"  # エンジン（cairo）は webp を読めないので PNG にする
        if convert:
            ext = ".png"
        if os.path.splitext(name)[1].lower() != ext:
            name = os.path.splitext(name)[0] + ext  # 拡張子は元の形式に合わせる
        dst = next_version(os.path.join(dest_dir, name))
        if convert:
            from PIL import Image
            Image.open(src).convert("RGBA").save(dst)
        else:
            shutil.copy2(src, dst)
        log.append(f"#{m['no']} {m['original']} → {dst}")
    out = os.path.join(os.path.dirname(mp), "applied.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(log) + "\n")
    print("\n".join(log))


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("list", "apply"):
        raise SystemExit(__doc__)
    cmd_list(sys.argv[2:]) if sys.argv[1] == "list" else cmd_apply(sys.argv[2])
