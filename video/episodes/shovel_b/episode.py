"""見本B：「辞令」の場面を、いらすとやの素材で作る（絵柄の比較用）。

素材は video/assets/images/shovel_b/ に置く（リポジトリには入れない）。
使っている素材（いらすとや、1動画20点までの規定に対して6点）:
  boss_desk.png      社長のイラスト（男性）
  a_surprise.png     サラリーマンの表情のイラスト「驚いた顔・ひらめいた顔・悩んだ顔・焦った顔」
  b_worried.png      転勤の辞令を受け取った会社員のイラスト（女性）※吹き出しを消す加工
  c_worried.png      転勤の辞令を受け取った会社員のイラスト（男性）※吹き出しを消す加工
  office_desk.png    綺麗なオフィスのイラスト
  dig_salaryman.png  埋蔵金を探す人のイラスト（男性会社員）
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
import core  # noqa: E402
from core import (H, W, INK, Timeline, Voicevox, caption, ease_back, ease_out,  # noqa: E402
                  fill_stroke, hexc, lerp, load_image, render, rrect, text)

OUT = os.path.join(HERE, "..", "..", "out")
IMG = os.path.join(HERE, "..", "..", "assets", "images", "shovel_b")
core.NARRATOR_IMAGE = None  # アキヒロのやわらかい絵柄版ができるまでは、コードで描いた顔

CAST = {
    "narr": {"id": 11, "speed": 1.08},
    "boss": {"id": 13, "speed": 1.05},
    "a": {"id": 12, "speed": 1.1},
    "b": {"id": 8, "speed": 1.1},
    "c": {"id": 10, "speed": 1.05},
}
NAMES = {"narr": "アキヒロ", "boss": "偉い人", "a": "行員A", "b": "行員B", "c": "行員C"}
COLORS = {"narr": hexc("#3D5A80"), "boss": hexc("#24324F"), "a": hexc("#3E78C8"),
          "b": hexc("#4E9A55"), "c": hexc("#C0563F")}


def build(vv):
    tl = Timeline(vv, CAST)
    tl.scene("office")
    tl.wait(0.6)
    tl.say("narr", "ある大手銀行が、営業や事務の行員を、3か月でAIエンジニアにするそうです。")
    tl.mark("banner", dur=0.5)
    tl.sfx("pop")
    tl.say("boss", "今日から君たちは、AIエンジニアだ！", ids=[81])
    tl.say("a", "え、私たち、営業と事務ですけど……", ids=[33])
    tl.say("b", "ふつう1年半かかるって、聞きましたけど……", voice="ふつう、いちねんはんかかるって、聞きましたけど")
    tl.say("boss", "心配いらん！ コードはAIが書く。ほら、これを持ちたまえ！", ids=[81], gap=0.4)
    tl.say("c", "……スコップ、ですね。", gap=0.4)
    tl.mark("dig_in", dur=0.5)
    tl.sfx("pop")
    tl.say("narr", "まず、スコップを持たせる。", gap=0.2)
    tl.mark("ai_tag", dur=0.4)
    tl.say("narr", "スコップは、AIです。", gap=1.2)
    return tl


def img(ctx, name, x, y, h, anchor="bottom", alpha=1.0, scale=1.0, bob=0.0):
    """素材画像を高さ h で、足元（下端中央）を (x, y) に合わせて描く。"""
    s = load_image(os.path.join(IMG, name + ".png"))
    k = h / s.get_height() * scale
    if k <= 1e-3:
        return
    ctx.save()
    ctx.translate(x, y - bob)
    ctx.scale(k, k)
    ctx.set_source_surface(s, -s.get_width() / 2, -s.get_height())
    ctx.paint_with_alpha(alpha)
    ctx.restore()


def talk_bob(tl, who, t):
    return 8 * abs(math.sin(t * 9)) if tl.speaking(who, t) else 0.0


def draw(ctx, t, tl):
    # 背景：壁と床（素材の淡い色調に合わせる）
    ctx.set_source_rgba(*hexc("#FFF8EC"))
    ctx.paint()
    ctx.rectangle(0, 700, W, H - 700)
    ctx.set_source_rgba(*hexc("#E9D8BE"))
    ctx.fill()
    img(ctx, "office_desk", 1790, 715, 300, alpha=0.85)
    # 横断幕
    k = tl.prog("banner", t, ease_back)
    if k > 0.02:
        ctx.save()
        ctx.translate(960, 130)
        ctx.scale(k, k)
        rrect(ctx, -400, -80, 800, 160, 24)
        fill_stroke(ctx, (1, 1, 1, 1), hexc("#E86A5C"), 8)
        text(ctx, "AIエンジニア育成プログラム", 0, -25, 54, hexc("#E86A5C"))
        text(ctx, "未経験から たった3か月！", 0, 38, 40, hexc("#5A4A3A"))
        ctx.restore()
    # 偉い人（机ごと）
    img(ctx, "boss_desk", 420, 900, 560, bob=talk_bob(tl, "boss", t))
    # 行員3人（下端は字幕の枠に隠れる）
    img(ctx, "a_surprise", 900, 900, 440, bob=talk_bob(tl, "a", t))
    img(ctx, "b_worried", 1200, 900, 470, bob=talk_bob(tl, "b", t))
    img(ctx, "c_worried", 1520, 900, 480, bob=talk_bob(tl, "c", t))
    # スコップを持たせる（イメージのコマ）
    d = tl.prog("dig_in", t, ease_back)
    if d > 0.02:
        ctx.save()
        ctx.set_source_rgba(1, 1, 1, 0.75 * min(d, 1))
        ctx.paint()
        ctx.translate(960, 500)
        ctx.scale(d, d)
        rrect(ctx, -330, -330, 660, 620, 30)
        fill_stroke(ctx, (1, 1, 1, 1), hexc("#5A4A3A"), 6)
        ctx.restore()
        img(ctx, "dig_salaryman", 960, 800, 560 * d)
        a = tl.prog("ai_tag", t, ease_back)
        if a > 0.02:
            ctx.save()
            ctx.translate(1150, 690)
            ctx.scale(a, a)
            rrect(ctx, -70, -45, 140, 90, 20)
            fill_stroke(ctx, hexc("#E86A5C"), (1, 1, 1, 1), 6)
            text(ctx, "AI", 0, 0, 56, (1, 1, 1, 1))
            ctx.restore()
    # 見本の表示
    rrect(ctx, 24, 20, 330, 56, 16)
    fill_stroke(ctx, (1, 1, 1, 0.9), hexc("#999999"), 3)
    text(ctx, "見本B：いらすとや素材", 189, 48, 28, hexc("#555555"))
    caption(ctx, tl, t, NAMES, COLORS)


def main():
    os.makedirs(OUT, exist_ok=True)
    vv = Voicevox(cache_dir=os.path.join(OUT, "cache"))
    tl = build(vv)
    total = tl.t
    fn = lambda ctx, t: draw(ctx, t, tl)  # noqa: E731
    if "--stills" in sys.argv:
        ts = [ln.t0 + 0.6 for ln in tl.lines]
        render(fn, total, None, os.path.join(OUT, "shovel_b_still"), frames=ts)
        return
    out = os.path.join(OUT, "shovel_b.mp4")
    render(fn, total, tl.audio(total), out)
    print(f"wrote {out} ({total:.1f}s)")


if __name__ == "__main__":
    main()
