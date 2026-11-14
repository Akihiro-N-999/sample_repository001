"""公開準備・分析のための道具。

使い方:
    python3 video/lib/publish_tools.py lines    video/episodes/<slug>   台詞ごとの開始・終了時刻（分析用）
    python3 video/lib/publish_tools.py chapters video/episodes/<slug>   台本の場面見出しごとの開始時刻（チャプター用）
    python3 video/lib/publish_tools.py srt      video/episodes/<slug>   YouTube 用の字幕ファイル（video/out/<slug>_v番号.srt）
    python3 video/lib/publish_tools.py thumbnail <設定.json>             サムネイル画像を合成（video/out/<名前>_v番号.png）

時刻は episode.py の build() が作るタイムライン（実際の音声の長さ）から求めるので、
書き出した動画と同じ時刻になる。VOICEVOX が動いている必要がある（合成済みの台詞はキャッシュを使う）。

thumbnail の設定（JSON）の例:
{
  "name": "shovel_thumb_a",                  // 出力名（番号は自動）
  "image": "video/assets/images/shovel/shovel_scene_dig.png",   // 番号なしで指定すると最新版
  "focus": [0.5, 0.5],                       // 画像のどこを中心に切り抜くか（0〜1）
  "zoom": 1.0,
  "texts": [                                  // 重ねる文字（上から順に描く）
    {"text": "3か月でAIエンジニア", "x": 60, "y": 90, "size": 110, "color": "#FFFFFF", "outline": "#1F2A44", "align": "left"},
    {"text": "掘っていたのは自分の墓穴？", "x": 60, "y": 230, "size": 90, "color": "#FFE14D", "outline": "#1F2A44", "align": "left"}
  ],
  "band": {"y": 0, "h": 330, "color": "#00000066"}   // 文字の下に敷く半透明の帯（任意）
}
"""
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import core  # noqa: E402
from core import Voicevox, caption_pages, next_version  # noqa: E402

OUT = os.path.join(HERE, "..", "out")


def load_timeline(ep):
    spec = importlib.util.spec_from_file_location("episode", os.path.join(ep, "episode.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build(Voicevox(cache_dir=os.path.join(OUT, "cache")))


def ts(t, srt=False):
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    if srt:
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1) * 1000):03d}"
    return f"{int(h)}:{int(m):02d}:{int(s):02d}" if h else f"{int(m)}:{int(s):02d}"


def script_sections(ep):
    """script.md の場面見出し（## …）と、その場面の最初の台詞が台本の何行目か。"""
    path = os.path.join(ep, "script.md")
    secs, n, cur = [], 0, None
    for raw in open(path, encoding="utf-8"):
        line = raw.strip()
        if line.startswith("## "):
            cur = line[3:].strip()
            secs.append([cur, None])
        elif line.startswith("|") and cur is not None:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 3 and cells[0] not in ("#",) and not set(cells[0]) <= set("-: ") and cells[2]:
                if secs[-1][1] is None:
                    secs[-1][1] = n
                n += 1
    return [(name, idx) for name, idx in secs if idx is not None]


def cmd_lines(ep):
    tl = load_timeline(ep)
    for i, ln in enumerate(tl.lines, 1):
        print(f"{i}\t{ts(ln.t0)}\t{ts(ln.t1)}\t{'+'.join(ln.who)}\t{ln.text.replace(chr(10), '')}")


def cmd_chapters(ep):
    tl = load_timeline(ep)
    secs = script_sections(ep)
    if not secs:
        raise SystemExit("script.md に場面の見出し（## …）と台本の表が見つかりません")
    print("# 台本の場面ごとの開始時刻（チャプターはこれを5〜8個にまとめる。最初は 0:00、各10秒以上）")
    for k, (name, idx) in enumerate(secs):
        t = 0 if k == 0 else (tl.lines[idx].t0 if idx < len(tl.lines) else tl.t)
        print(f"{ts(t)} {name}")
    print(f"# 動画の長さ {ts(tl.t)}")


def cmd_srt(ep):
    import cairo
    slug = os.path.basename(ep.rstrip("/"))
    tl = load_timeline(ep)
    ctx = cairo.Context(cairo.ImageSurface(cairo.FORMAT_RGB24, 10, 10))
    cues = []
    for ln in tl.lines:
        # 画面の字幕と同じページ分けで、話している時間を文字数の割合で配分する
        pages, ratios = caption_pages(ctx, ln.text, 52, 1340)
        t = ln.t0
        for pg, r in zip(pages, ratios):
            d = (ln.t1 - ln.t0) * r
            cues.append((t, t + d, "\n".join(pg)))
            t += d
    path = next_version(os.path.join(OUT, f"{slug}.srt"))
    with open(path, "w", encoding="utf-8") as f:
        for i, (a, b, text) in enumerate(cues, 1):
            f.write(f"{i}\n{ts(a, True)} --> {ts(b, True)}\n{text}\n\n")
    print(f"{len(cues)} 件 → {path}")


def cmd_thumbnail(conf_path):
    import cairo
    conf = json.load(open(conf_path, encoding="utf-8"))
    W, H = 1280, 720
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
    ctx = cairo.Context(surf)
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()
    img = core.load_image(core.latest(conf["image"]))
    iw, ih = img.get_width(), img.get_height()
    z = conf.get("zoom", 1.0)
    k = max(W / iw, H / ih) * z
    fx, fy = conf.get("focus", [0.5, 0.5])
    ox = core.clamp(W / 2 - fx * iw * k, W - iw * k, 0)
    oy = core.clamp(H / 2 - fy * ih * k, H - ih * k, 0)
    ctx.save()
    ctx.translate(ox, oy)
    ctx.scale(k, k)
    ctx.set_source_surface(img, 0, 0)
    ctx.get_source().set_filter(cairo.FILTER_GOOD)
    ctx.paint()
    ctx.restore()
    band = conf.get("band")
    if band:
        h = band["color"].lstrip("#")
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 0.4
        ctx.rectangle(0, band.get("y", 0), W, band.get("h", 300))
        ctx.set_source_rgba(*core.hexc(h[:6])[:3], a)
        ctx.fill()
    for t in conf.get("texts", []):
        size = t.get("size", 100)
        core.text(ctx, t["text"], t.get("x", 60), t.get("y", 100), size,
                  core.hexc(t.get("color", "#FFFFFF")), align=t.get("align", "left"),
                  outline=core.hexc(t.get("outline", "#000000")), ow=max(8, size * 0.16))
    path = next_version(os.path.join(OUT, conf.get("name", "thumbnail") + ".png"))
    surf.write_to_png(path)
    print(path)


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("lines", "chapters", "srt", "thumbnail"):
        raise SystemExit(__doc__)
    {"lines": cmd_lines, "chapters": cmd_chapters, "srt": cmd_srt, "thumbnail": cmd_thumbnail}[sys.argv[1]](sys.argv[2])
