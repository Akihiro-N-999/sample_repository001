"""見本A：「辞令」の場面を、Gemini で作った漫画風の立ち絵と場面イラストで作る（絵柄の比較用）。

素材は video/assets/images/shovel/ に置く（リポジトリには入れない）。指示書は
video/episodes/shovel/image_prompts_A.md。台詞と声は見本B（shovel_b）と同じ。

ショットの組み立て：
  場面イラストを大きく見せる「場面ショット」と、立ち絵が並んで口パクする「会話ショット」を
  台詞ごとに切り替える。話していない人物は少し薄くする。
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
import core  # noqa: E402
from core import (H, W, Tachie, Timeline, Voicevox, caption, clamp, ease_back,  # noqa: E402
                  ease_io, fill_stroke, hexc, lerp, render, rrect, text)
import cairo  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "out")
IMG = os.path.join(HERE, "..", "..", "assets", "images", "shovel")
core.NARRATOR_IMAGE = os.path.join(IMG, "akihiro_face_A.png")

CAST = {
    "narr": {"id": 11, "speed": 1.08},
    "boss": {"id": 13, "speed": 1.05},
    "a": {"id": 12, "speed": 1.1},
    "b": {"id": 8, "speed": 1.1},
    "c": {"id": 10, "speed": 1.05},
}
NAMES = {"narr": "アキヒロ", "boss": "偉い人", "a": "行員A", "b": "行員B", "c": "行員C"}
COLORS = {"narr": hexc("#3D5A80"), "boss": hexc("#5A2A2A"), "a": hexc("#3E78C8"),
          "b": hexc("#4A4F7A"), "c": hexc("#7A5A3A")}


def build(vv):
    tl = Timeline(vv, CAST)
    tl.scene("scene")
    tl.wait(0.6)
    tl.say("narr", "ある大手銀行が、営業や事務の行員を、3か月でAIエンジニアにするそうです。")
    tl.scene("talk")
    tl.mark("banner", dur=0.5)
    tl.sfx("pop")
    tl.say("boss", "今日から君たちは、AIエンジニアだ！", ids=[81])
    tl.say("a", "え、私たち、営業と事務ですけど……", ids=[33])
    tl.say("b", "ふつう1年半かかるって、聞きましたけど……", voice="ふつう、いちねんはんかかるって、聞きましたけど")
    tl.scene("scene2")
    tl.say("boss", "心配いらん！ コードはAIが書く。ほら、これを持ちたまえ！", ids=[81], gap=0.4)
    tl.scene("talk_c")
    tl.say("c", "……スコップ、ですね。", gap=0.4)
    tl.scene("shovel")
    tl.mark("zoom", dur=1.2)
    tl.say("narr", "まず、スコップを持たせる。", gap=0.2)
    tl.mark("ai_tag", dur=0.4)
    tl.sfx("pop")
    tl.say("narr", "スコップは、AIです。", gap=1.2)
    return tl


class Assets:
    def __init__(self):
        p = lambda n: os.path.join(IMG, n)  # noqa: E731
        self.boss = Tachie(p("shovel_boss_base.png"), p("shovel_boss_mouth_open.png"))
        self.a = Tachie(p("shovel_a_base.png"), p("shovel_a_mouth_open.png"))
        self.b = Tachie(p("shovel_b_base.png"))
        self.c = Tachie(p("shovel_c_base.png"))
        self.scene = core.load_image(self._png(p("shovel_scene_assign.png"), "scene"))
        self.scene_blur = core.load_image(self._png(p("shovel_scene_assign.png"), "scene_blur", blur=True))

    @staticmethod
    def _png(path, key, blur=False):
        from PIL import Image, ImageEnhance, ImageFilter
        path = core.latest(path)
        key = f"{key}_{os.path.splitext(os.path.basename(path))[0]}"  # 版が変わったら作り直す
        im = Image.open(path).convert("RGBA")
        if blur:
            im = im.filter(ImageFilter.GaussianBlur(40))
            im = ImageEnhance.Color(im).enhance(0.5)
            im = ImageEnhance.Brightness(im).enhance(1.25)
        return core._pil_to_surface(im, f"shovel_{key}").get_width() and os.path.join(
            core.CACHE_DIR, f"shovel_{key}.png")


def paint_cover(ctx, surf, z=1.0, cx=None, cy=None):
    """画面いっぱいに画像を敷く。z は拡大率、(cx, cy) は画面中央に来る画像上の点（画面座標）。"""
    iw, ih = surf.get_width(), surf.get_height()
    k = max(W / iw, H / ih)
    cx = W / 2 if cx is None else cx
    cy = H / 2 if cy is None else cy
    cx = clamp(cx, W / (2 * z), iw * k - W / (2 * z))
    cy = clamp(cy, H / (2 * z), ih * k - H / (2 * z))
    ctx.save()
    ctx.translate(W / 2, H / 2)
    ctx.scale(z, z)
    ctx.translate(-cx, -cy)
    ctx.scale(k, k)
    ctx.set_source_surface(surf, 0, 0)
    ctx.get_source().set_filter(cairo.FILTER_GOOD)
    ctx.paint()
    ctx.restore()


def bob(tl, who, t):
    return 6 * abs(math.sin(t * 9)) if tl.speaking(who, t) else 0.0


def dim(tl, who, t):
    """話していない人物を少し薄くする（話し手を目立たせる）。"""
    return 0.0 if tl.speaking(who, t) else 0.28


def draw_talk(ctx, tl, t, A, focus_c=False):
    paint_cover(ctx, A.scene_blur, z=1.05)
    ctx.set_source_rgba(*hexc("#FBF6EC", 0.55))
    ctx.paint()
    k = tl.prog("banner", t, ease_back)
    if k > 0.02:
        ctx.save()
        ctx.translate(960, 120)
        ctx.scale(k, k)
        rrect(ctx, -400, -78, 800, 156, 14)
        fill_stroke(ctx, (1, 1, 1, 0.95), hexc("#8A2A2A"), 6)
        text(ctx, "AIエンジニア育成プログラム", 0, -24, 52, hexc("#8A2A2A"))
        text(ctx, "未経験から たった3か月！", 0, 36, 38, hexc("#333333"))
        ctx.restore()
    if focus_c:
        A.b.draw(ctx, 560, 1080, 760, dim=0.28)
        A.a.draw(ctx, 880, 1080, 760, dim=0.28)
        A.c.draw(ctx, 1380, 1080, 1000, mouth=tl.mouth("c", t), bob=bob(tl, "c", t), dim=dim(tl, "c", t))
        return
    A.boss.draw(ctx, 470, 1080, 980, mouth=tl.mouth("boss", t), bob=bob(tl, "boss", t), dim=dim(tl, "boss", t))
    A.a.draw(ctx, 1080, 1080, 760, mouth=tl.mouth("a", t), bob=bob(tl, "a", t), dim=dim(tl, "a", t))
    A.b.draw(ctx, 1400, 1080, 740, bob=bob(tl, "b", t), dim=dim(tl, "b", t))
    A.c.draw(ctx, 1710, 1080, 780, bob=bob(tl, "c", t), dim=dim(tl, "c", t))


def draw(ctx, t, tl, A):
    sc = tl.scene_at(t)
    t0 = max(ts for ts, n in tl.scenes if ts <= t + 1e-9)
    u = t - t0
    if sc == "scene":
        paint_cover(ctx, A.scene, z=1.0 + 0.012 * u, cx=W / 2, cy=H / 2)
    elif sc == "scene2":
        paint_cover(ctx, A.scene, z=1.08 + 0.01 * u, cx=820, cy=520)
    elif sc == "talk":
        draw_talk(ctx, tl, t, A)
    elif sc == "talk_c":
        draw_talk(ctx, tl, t, A, focus_c=True)
    elif sc == "shovel":
        z = lerp(1.08, 1.45, tl.prog("zoom", t, ease_io))
        cx, cy = lerp(820, 860, tl.prog("zoom", t)), lerp(520, 680, tl.prog("zoom", t))
        ctx.save()
        paint_cover(ctx, A.scene, z=z, cx=cx, cy=cy)
        ctx.restore()
        a = tl.prog("ai_tag", t, ease_back)
        if a > 0.02:
            # スコップの刃の上（画面座標に変換して置く）
            wx, wy = 820, 860
            sx, sy = (wx - cx) * z + W / 2, (wy - cy) * z + H / 2
            ctx.save()
            ctx.translate(sx + 170, sy - 120)
            ctx.scale(a, a)
            rrect(ctx, -80, -50, 160, 100, 22)
            fill_stroke(ctx, hexc("#C0392B"), (1, 1, 1, 1), 7)
            text(ctx, "AI", 0, 0, 62, (1, 1, 1, 1))
            ctx.restore()
    f = tl.fade(t, d=0.18)
    if f > 0:
        ctx.set_source_rgba(1, 1, 1, f * 0.6)
        ctx.paint()
    rrect(ctx, 24, 20, 360, 56, 16)
    fill_stroke(ctx, (1, 1, 1, 0.9), hexc("#999999"), 3)
    text(ctx, "見本A：漫画動画（Gemini）", 204, 48, 28, hexc("#555555"))
    caption(ctx, tl, t, NAMES, COLORS)


def main():
    os.makedirs(OUT, exist_ok=True)
    vv = Voicevox(cache_dir=os.path.join(OUT, "cache"))
    tl = build(vv)
    A = Assets()
    total = tl.t
    fn = lambda ctx, t: draw(ctx, t, tl, A)  # noqa: E731
    if "--stills" in sys.argv:
        ts = [ln.t0 + 0.6 for ln in tl.lines]
        render(fn, total, None, os.path.join(OUT, "shovel_a_still"), frames=ts)
        return
    out = os.path.join(OUT, "shovel_a.mp4")
    out = render(fn, total, tl.audio(total), out)
    print(f"wrote {out} ({total:.1f}s)")


if __name__ == "__main__":
    main()
