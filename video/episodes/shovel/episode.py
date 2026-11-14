"""note「スコップを渡された人たち」寸劇アニメ（試作版: 辞令 → 穴掘り → 碑 → 突き落とし）

使い方（リポジトリ直下で）:
    python3 video/episodes/shovel/episode.py            # MP4 を書き出す
    python3 video/episodes/shovel/episode.py --stills   # 確認用の静止画だけ出す
"""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from core import (H, W, INK, Timeline, Voicevox, caption, clamp, ease_back,  # noqa: E402
                  ease_out, fill_stroke, hexc, lerp, person, render, rrect, star, text,
                  vtext, wrap)
import cairo  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "out")
# 語り手の顔（本人の写真から生成AIで作ったイラストの顔部分）。リポジトリには入れていない。
# ファイルがなければ、コードで描いた顔アイコンを使う。
FACE = os.path.join(HERE, "..", "..", "assets", "images", "akihiro_face.png")
import core  # noqa: E402
core.NARRATOR_IMAGE = FACE

# ---------------------------------------------------------------- 配役（VOICEVOX 話者ID）
CAST = {
    "narr": {"id": 11, "speed": 1.08},   # 玄野武宏 ノーマル
    "boss": {"id": 13, "speed": 1.05},   # 青山龍星 ノーマル
    "a": {"id": 12, "speed": 1.1},       # 白上虎太郎 ふつう
    "b": {"id": 8, "speed": 1.1},        # 春日部つむぎ ノーマル
    "c": {"id": 10, "speed": 1.05},      # 雨晴はう ノーマル
}
NAMES = {"narr": "アキヒロ", "boss": "偉い人", "a": "行員A", "b": "行員B", "c": "行員C",
         "a+b+c": "行員たち"}
COLORS = {"narr": hexc("#3D5A80"), "boss": hexc("#24324F"), "a": hexc("#3E78C8"),
          "b": hexc("#4E9A55"), "c": hexc("#C0563F"), "a+b+c": hexc("#8A6A3A")}
CREDIT = ["音声：VOICEVOX:玄野武宏　VOICEVOX:青山龍星　VOICEVOX:白上虎太郎",
          "VOICEVOX:春日部つむぎ　VOICEVOX:雨晴はう",
          "語り手のイラスト：生成AI（Gemini）で作成"]

STAFF = [("a", "#4C83D1", "#7A4A2A"), ("b", "#5AA35F", "#4A3222"), ("c", "#C9654B", "#8B5A2B")]
DOCS = ["融資", "窓口", "稟議", "苦情", "為替", "相続", "年金", "口座", "審査", "規程"]


# ---------------------------------------------------------------- 台本
def build(vv):
    tl = Timeline(vv, CAST)

    # タイトル
    tl.scene("title")
    tl.mark("title_in", dur=0.6)
    tl.sfx("chime", at=0.2)
    tl.wait(3.2)

    # ① 辞令（オフィス）
    tl.scene("office")
    tl.wait(0.5)
    tl.say("narr", "ある大手銀行が、営業や事務の行員を、\n3か月でAIエンジニアにするそうです。")
    tl.mark("boss_enter", dur=1.0)
    tl.sfx("whoosh")
    tl.wait(1.1)
    tl.mark("banner", dur=0.5)
    tl.sfx("pop")
    tl.say("boss", "今日から君たちは、AIエンジニアだ！", ids=[81])
    tl.mark("sweat_a")
    tl.say("a", "え、私たち、営業と事務ですけど……", ids=[33])
    tl.say("b", "ふつう1年半かかるって、聞きましたけど……", voice="ふつう、いちねんはんかかるって、聞きましたけど")
    a, b = tl.say("boss", "心配いらん！ コードはAIが書く。\nほら、これを持ちたまえ！", ids=[81], gap=0.2)
    tl.mark("point", at=a + 1.0, dur=0.01)
    for i in range(3):
        tl.mark(f"shovel{i}", at=b + 0.05 + i * 0.18, dur=0.35)
        tl.sfx("pop", at=b + 0.05 + i * 0.18)
    tl.wait(0.7)
    tl.say("c", "……スコップ、ですね。", gap=0.4)
    tl.say("narr", "まず、スコップを持たせる。", gap=0.2)
    tl.mark("zoom_shovel", dur=0.8)
    tl.say("narr", "スコップは、AIです。", gap=0.8)

    # ② 穴を掘る（野原）
    tl.scene("field")
    tl.wait(0.5)
    a, _ = tl.say("narr", "次に、穴を掘らせる。", gap=0.2)
    tl.mark("dig", at=a + 0.6, dur=9.0)
    tl.mark("cheer")
    tl.say(["a", "b", "c"], "業務知識、ぜんぶ掘り出しまーす！", voice="ぎょうむちしき、ぜんぶ掘り出しまーす！",
           ids=[32, 8, 10])
    tl.say("boss", "いいぞいいぞ、どんどん掘れ！", ids=[81], gap=0.5)
    a, _ = tl.say("narr", "掘った穴に、碑を建てさせる。", voice="掘った穴に、ひを建てさせる。", gap=0.2)
    tl.mark("mon", at=a + 0.3, dur=5.0)
    _, b = tl.say("narr", "碑は、業務知識がぎっしり詰まった、\nAIエージェントです。",
                  voice="ひは、ぎょうむちしきがぎっしり詰まった、エーアイエージェントです。", gap=0.4)
    tl.marks["dig"] = (tl.marks["dig"][0], b - tl.marks["dig"][0] - 0.3)
    tl.marks["mon"] = (tl.marks["mon"][0], b - tl.marks["mon"][0] + 0.2)

    # ③ 完成 → 突き落とし
    tl.mark("climb", dur=0.9)
    tl.wait(0.9)
    tl.mark("done", dur=0.6)
    tl.sfx("chime")
    tl.say("a", "できました！", ids=[32], gap=0.5)
    tl.mark("boss_step", dur=0.8)
    tl.say("boss", "おつかれさま。", gap=0.6)
    tl.mark("evil", dur=0.6)
    tl.sfx("shock", vol=0.8)
    a, b = tl.say("boss", "おまえらは、もう用済みだ！", ids=[82], gap=0.1)
    tl.mark("push", dur=0.3)
    tl.sfx("whoosh")
    tl.mark("fall", at=tl.t + 0.12, dur=1.1)
    tl.say(["a", "b", "c"], "えっ", ids=[33, 8, 10], gap=0.0)
    tl.sfx("thud", at=tl.marks["fall"][0] + 1.05)
    tl.t = tl.marks["fall"][0] + 1.9
    tl.mark("evil_off", dur=0.8)
    tl.say("narr", "そして最後に、作った人を、\nその穴に突き落とす。", gap=0.9)
    tl.mark("calm", dur=1.5)
    tl.say("narr", "……おしまい。", voice="おしまい。", gap=1.2)

    # エンドカード
    tl.scene("end")
    tl.mark("end_in", dur=0.6)
    tl.wait(5.0)
    return tl


# ---------------------------------------------------------------- 背景
def bg_office(ctx, tl, t):
    ctx.set_source_rgba(*hexc("#F3EBDD"))
    ctx.paint()
    ctx.rectangle(0, 640, W, 160)
    ctx.set_source_rgba(*hexc("#E4D6BE"))
    ctx.fill()
    ctx.rectangle(0, 800, W, H - 800)
    ctx.set_source_rgba(*hexc("#BFA582"))
    ctx.fill()
    ctx.set_source_rgba(*INK)
    ctx.set_line_width(5)
    ctx.move_to(0, 800)
    ctx.line_to(W, 800)
    ctx.stroke()
    # 窓
    rrect(ctx, 110, 150, 420, 300, 10)
    fill_stroke(ctx, hexc("#BFE3F5"))
    ctx.set_line_width(8)
    ctx.move_to(320, 150)
    ctx.line_to(320, 450)
    ctx.move_to(110, 300)
    ctx.line_to(530, 300)
    ctx.stroke()
    # 観葉植物
    ctx.set_source_rgba(*hexc("#5AA35F"))
    for a in range(-3, 4):
        ctx.save()
        ctx.translate(1830, 690)
        ctx.rotate(a * 0.28)
        ctx.scale(0.35, 1)
        ctx.arc(0, -70, 70, 0, 2 * math.pi)
        ctx.restore()
        fill_stroke(ctx, hexc("#5AA35F"), lw=4)
    rrect(ctx, 1785, 690, 90, 110, 12)
    fill_stroke(ctx, hexc("#B5653F"))
    # 横断幕
    k = tl.prog("banner", t, ease_back)
    if k > 0:
        ctx.save()
        ctx.translate(1110, 175)
        ctx.scale(k, k)
        rrect(ctx, -380, -95, 760, 190, 18)
        fill_stroke(ctx, (1, 1, 1, 1), hexc("#D33A2C"), 10)
        text(ctx, "AIエンジニア育成プログラム", 0, -32, 56, hexc("#D33A2C"))
        text(ctx, "未経験から たった3か月！", 0, 40, 46, INK)
        ctx.restore()


FG = 690          # 野原の地面の高さ
HX = 1330         # 穴の中心
MONX = 300        # 碑の位置


def hole_geom(tl, t):
    d = tl.prog("dig", t, lambda x: clamp(x))
    depth = 30 + 170 * d
    return depth, 250 * min(1, 0.4 + d), 190 * min(1, 0.4 + d)


def bg_field(ctx, tl, t):
    g = cairo.LinearGradient(0, 0, 0, FG)
    g.add_color_stop_rgb(0, *hexc("#9FD3F0")[:3])
    g.add_color_stop_rgb(1, *hexc("#FFF4DC")[:3])
    ctx.set_source(g)
    ctx.paint()
    # 雲
    for i, (cx, cy, s) in enumerate([(300, 160, 1.0), (980, 110, 0.8), (1600, 200, 1.2)]):
        x = (cx + t * 12 * (1 + i * 0.3)) % (W + 400) - 200
        ctx.set_source_rgba(1, 1, 1, 0.9)
        for dx, r in ((-50, 40), (0, 58), (55, 44)):
            ctx.arc(x + dx * s, cy, r * s, 0, 2 * math.pi)
            ctx.fill()
    # 遠くの丘
    ctx.new_path()
    ctx.move_to(0, FG)
    for x in range(0, W + 40, 40):
        ctx.line_to(x, FG - 70 - 40 * math.sin(x / 260) - 25 * math.sin(x / 97))
    ctx.line_to(W, FG)
    ctx.close_path()
    ctx.set_source_rgba(*hexc("#B9D79A"))
    ctx.fill()
    # 地面
    ctx.rectangle(0, FG, W, H - FG)
    ctx.set_source_rgba(*hexc("#CFAE7E"))
    ctx.fill()
    ctx.set_source_rgba(*hexc("#BE9B6B"))
    for y in (FG + 60, FG + 150, FG + 260):
        ctx.rectangle(0, y, W, 8)
        ctx.fill()
    ctx.set_source_rgba(*INK)
    ctx.set_line_width(5)
    ctx.move_to(0, FG)
    ctx.line_to(W, FG)
    ctx.stroke()
    # 掘った土の山
    d = tl.prog("dig", t, lambda x: clamp(x))
    if d > 0:
        ctx.save()
        ctx.translate(HX + 380, FG)
        ctx.scale(1, d)
        ctx.arc(0, 0, 150, math.pi, 2 * math.pi)
        ctx.restore()
        fill_stroke(ctx, hexc("#A57B4C"))
    # 穴
    depth, tw, bw = hole_geom(tl, t)
    hole_path(ctx, depth, tw, bw)
    fill_stroke(ctx, hexc("#5B3F28"))


def hole_path(ctx, depth, tw, bw, new=True):
    if new:
        ctx.new_path()
    ctx.move_to(HX - tw, FG)
    ctx.line_to(HX + tw, FG)
    ctx.line_to(HX + bw, FG + depth)
    ctx.line_to(HX - bw, FG + depth)
    ctx.close_path()


def monument(ctx, tl, t):
    k = tl.prog("mon", t)
    if k <= 0:
        return
    done = tl.prog("done", t, ease_back)
    if done > 0:
        g = cairo.RadialGradient(MONX, FG - 200, 20, MONX, FG - 200, 330)
        g.add_color_stop_rgba(0, 1, 0.92, 0.5, 0.85 * min(done, 1))
        g.add_color_stop_rgba(1, 1, 0.92, 0.5, 0)
        ctx.set_source(g)
        ctx.arc(MONX, FG - 200, 330, 0, 2 * math.pi)
        ctx.fill()
    ctx.save()
    ctx.rectangle(0, 0, W, FG)
    ctx.clip()
    ctx.translate(0, (1 - k) * 420)
    w, h = 210, 390
    ctx.new_path()
    ctx.move_to(MONX - w / 2, FG)
    ctx.line_to(MONX - w / 2, FG - h + 50)
    ctx.curve_to(MONX - w / 2, FG - h - 10, MONX + w / 2, FG - h - 10, MONX + w / 2, FG - h + 50)
    ctx.line_to(MONX + w / 2, FG)
    ctx.close_path()
    fill_stroke(ctx, hexc("#8E979F"), lw=6)
    rrect(ctx, MONX - w / 2 - 25, FG - 30, w + 50, 30, 4)
    fill_stroke(ctx, hexc("#737C84"), lw=5)
    vtext(ctx, "AIエージェント", MONX, FG - h + 52, 40, hexc("#2E3338"))
    ctx.restore()
    if done > 0:
        for i in range(6):
            a = t * 1.5 + i * math.pi / 3
            star(ctx, MONX + 170 * math.cos(a), FG - 220 + 190 * math.sin(a), 16 * done, t * 3)
            ctx.set_source_rgba(*hexc("#F5C542"))
            ctx.fill()
        ctx.save()
        ctx.translate(MONX, FG - 470)
        ctx.scale(done, done)
        text(ctx, "完成！", 0, 0, 72, hexc("#E39B12"), outline=(1, 1, 1, 1), ow=14)
        ctx.restore()


def flying_docs(ctx, tl, t):
    if "dig" not in tl.marks:
        return
    t_start = tl.marks["dig"][0] + 0.8
    t_end = tl.marks["mon"][0] + tl.marks["mon"][1] - 1.2
    rnd = random.Random(7)
    i = 0
    ts = t_start
    while ts < t_end:
        r1, r2, r3 = rnd.random(), rnd.random(), rnd.random()
        u = (t - ts) / 1.25
        if 0 <= u <= 1:
            depth, _, _ = hole_geom(tl, ts)
            x0, y0 = HX + (r1 - 0.5) * 220, FG + depth * 0.4
            x1, y1 = MONX + (r2 - 0.5) * 80, FG - 80 - r3 * 120
            x = lerp(x0, x1, u)
            y = lerp(y0, y1, u) - math.sin(math.pi * u) * (300 + r3 * 120)
            al = clamp((1 - u) / 0.2)
            ctx.save()
            ctx.translate(x, y)
            ctx.rotate(u * 6 * (r1 - 0.5))
            ctx.push_group()
            rrect(ctx, -52, -32, 104, 64, 6)
            fill_stroke(ctx, (1, 1, 1, 1), lw=4)
            text(ctx, DOCS[i % len(DOCS)], 0, 0, 30, INK)
            ctx.pop_group_to_source()
            ctx.paint_with_alpha(al)
            ctx.restore()
        ts += 0.32
        i += 1


# ---------------------------------------------------------------- 場面ごとの描画
def bob(tl, who, t):
    return 7 * abs(math.sin(t * 11)) if tl.speaking(who, t) else 0


def draw_office(ctx, tl, t):
    bg_office(ctx, tl, t)
    ent = tl.prog("boss_enter", t, ease_out)
    bx = lerp(-260, 600, ent)
    walk = 10 * abs(math.sin(t * 14)) if 0 < ent < 1 else 0
    arms = "point" if tl.since("point", t) > 0 else "down"
    person(ctx, bx, 800, 1.12, kind="boss", body="#24324F", mouth=tl.mouth("boss", t),
           eyes="smug", arms=arms, bob=walk + bob(tl, "boss", t))
    for i, (w, body, hair) in enumerate(STAFF):
        sv = tl.prog(f"shovel{i}", t, ease_back)
        sweat = (w == "a" and tl.since("sweat_a", t) > 0) or (sv > 0 and w != "a")
        person(ctx, 1150 + i * 250, 800, 1.0, body=body, hair=hair, mouth=tl.mouth(w, t),
               eyes="wide" if tl.since("sweat_a", t) > 0 and sv == 0 and w == "a" else "normal",
               sweat=sweat, shovel_s=sv, bob=bob(tl, w, t))


def staff_state(tl, t, i):
    """野原での行員iの位置・姿勢。"""
    depth, _, _ = hole_geom(tl, t)
    xh, yh = HX - 130 + i * 130, FG + depth * 0.85
    xl, yl = 760 + i * 125, FG
    c = tl.prog("climb", t)
    x = lerp(xh, xl, c)
    y = lerp(yh, yl, c) - math.sin(math.pi * c) * 150
    st = dict(x=x, y=y, rot=0.0, alpha=1.0, arms="dig", eyes="normal")
    if tl.since("dig", t) < 0 or c > 0:
        st["arms"] = "down"
    if tl.since("cheer", t) > 0 and c == 0:
        st["eyes"] = "happy"
    if tl.since("done", t) > 0:
        st["arms"], st["eyes"] = "up", "happy"
    f = tl.prog("fall", t, lambda u: clamp(u))
    if tl.since("push", t) > 0:
        st["eyes"], st["arms"] = "wide", "flail"
    if f > 0:
        tx = HX - 110 + i * 110
        st["x"] = lerp(xl, tx, ease_out(f))
        st["y"] = FG - math.sin(math.pi * min(f * 1.6, 1)) * 90 + (f ** 2) * (depth + 260)
        st["rot"] = f * (1.6 + 0.3 * i)
        st["alpha"] = clamp((1 - f) / 0.35)
    return st


def draw_field(ctx, tl, t):
    bg_field(ctx, tl, t)
    monument(ctx, tl, t)
    # 偉い人
    step = tl.prog("boss_step", t)
    push = tl.prog("push", t, ease_out)
    bx = lerp(lerp(560, 600, step), 660, push)
    arms = "push" if tl.since("push", t) > 0 else ("cross" if tl.since("dig", t) > 0 and step == 0 else "down")
    evil = tl.since("evil", t) > 0
    person(ctx, bx, FG, 1.1, kind="boss", body="#24324F", mouth=tl.mouth("boss", t),
           eyes="evil" if evil else "smug", arms=arms, bob=bob(tl, "boss", t),
           sweat=False)
    # 行員（穴の外と穴の中だけ見えるようにクリップ）
    depth, tw, bw = hole_geom(tl, t)
    ctx.save()
    ctx.rectangle(0, 0, W, FG)
    hole_path(ctx, depth, tw, bw, new=False)
    ctx.clip()
    for i, (w, body, hair) in enumerate(STAFF):
        st = staff_state(tl, t, i)
        person(ctx, st["x"], st["y"], 0.92, body=body, hair=hair, mouth=tl.mouth(w, t),
               eyes=st["eyes"], arms=st["arms"], shovel_s=1.0,
               dig=(t * 1.4 + i * 0.33) % 1, rot=st["rot"], alpha=st["alpha"],
               bob=bob(tl, w, t))
    ctx.restore()
    flying_docs(ctx, tl, t)
    # 「えっ」
    k = tl.prog("push", t, ease_back)
    gone = clamp(1 - (tl.since("fall", t) - 0.9) / 0.4)
    if k > 0 and gone > 0:
        ctx.save()
        ctx.translate(1080, 330)
        ctx.rotate(-0.12)
        ctx.scale(k, k)
        ctx.push_group()
        text(ctx, "えっ", 0, 0, 110, hexc("#D33A2C"), outline=(1, 1, 1, 1), ow=16)
        ctx.pop_group_to_source()
        ctx.paint_with_alpha(gone)
        ctx.restore()


def draw_title(ctx, tl, t):
    ctx.set_source_rgba(*hexc("#1F2A44"))
    ctx.paint()
    k = tl.prog("title_in", t, ease_back)
    from core import shovel
    shovel(ctx, W / 2, 170, 0.25 * math.sin(t * 2.5), 1.6 * k)
    ctx.save()
    ctx.translate(W / 2, 560)
    ctx.scale(k, k)
    text(ctx, "スコップを渡された人たち", 0, 0, 110, (1, 1, 1, 1))
    text(ctx, "―非エンジニアを3か月でAIエンジニアに―", 0, 120, 46, hexc("#F5C542"))
    ctx.restore()
    rrect(ctx, W / 2 - 190, 820, 380, 70, 35)
    fill_stroke(ctx, hexc("#F5C542", k), (1, 1, 1, k), 0.1)
    text(ctx, "寸劇アニメ（試作版）", W / 2, 855, 36, hexc("#1F2A44", k))
    narrator_badge(ctx, 1640, 880, k)


def draw_end(ctx, tl, t):
    ctx.set_source_rgba(*hexc("#1F2A44"))
    ctx.paint()
    k = tl.prog("end_in", t, ease_out)
    text(ctx, "この続きは、noteの本編で。", W / 2, 400, 80, (1, 1, 1, k))
    text(ctx, "「スコップを渡された人たち」", W / 2, 530, 56, hexc("#F5C542", k))
    narrator_badge(ctx, W / 2, 720, k)
    for i, s in enumerate(CREDIT):
        text(ctx, s, W / 2, 890 + i * 46, 30, (0.85, 0.87, 0.92, k), bold=False)


def narrator_badge(ctx, x, y, k):
    """「語り：アキヒロ」の顔つき表示（顔画像がなければ描いた顔）。"""
    if k <= 0.01:
        return
    from core import portrait_narrator, portrait_image
    ctx.push_group()
    if os.path.exists(core.latest(FACE)):
        portrait_image(ctx, x - 80, y, 70, core.latest(FACE))
    else:
        portrait_narrator(ctx, x - 80, y, 70, 0.0)
    text(ctx, "語り", x + 10, y - 22, 26, (0.85, 0.87, 0.92, 1), align="left", bold=False)
    text(ctx, "アキヒロ", x + 10, y + 18, 40, (1, 1, 1, 1), align="left")
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(k)


def make_draw(tl):
    def draw(ctx, t):
        sc = tl.scene_at(t)
        ctx.save()
        # カメラ
        z, cx, cy = 1.0, W / 2, H / 2
        if sc == "office":
            u = tl.prog("zoom_shovel", t)
            z, cx, cy = lerp(1, 2.3, u), lerp(W / 2, 1250, u), lerp(H / 2, 610, u)
        elif sc == "field":
            u = tl.prog("evil", t) * (1 - tl.prog("push", t))
            z, cx, cy = lerp(1, 1.45, u), lerp(W / 2, 640, u), lerp(H / 2, 470, u)
            c = tl.prog("calm", t)
            z *= lerp(1, 1.06, c)
        ctx.translate(W / 2, H / 2)
        ctx.scale(z, z)
        ctx.translate(-cx, -cy)
        {"title": draw_title, "office": draw_office, "field": draw_field,
         "end": draw_end}[sc](ctx, tl, t)
        ctx.restore()
        if sc == "field":
            dark = tl.prog("evil", t) * (1 - tl.prog("evil_off", t))
            if dark > 0:
                ctx.set_source_rgba(0.12, 0.0, 0.2, 0.38 * dark)
                ctx.paint()
        if sc in ("office", "field"):
            caption(ctx, tl, t, NAMES, COLORS)
        f = tl.fade(t)
        if f > 0:
            ctx.set_source_rgba(0, 0, 0, f)
            ctx.paint()
    return draw


def main():
    os.makedirs(OUT, exist_ok=True)
    vv = Voicevox(cache_dir=os.path.join(OUT, "cache"))
    tl = build(vv)
    total = tl.t
    draw = make_draw(tl)
    print(f"total {total:.1f}s, lines {len(tl.lines)}")
    if "--stills" in sys.argv:
        ts = [1.5] + [ln.t0 + 0.4 for ln in tl.lines] + [tl.marks["fall"][0] + 0.5, total - 2]
        render(draw, total, None, os.path.join(OUT, "still"), frames=ts)
        return
    out = os.path.join(OUT, "shovel_pilot.mp4")
    out = render(draw, total, tl.audio(total), out)
    print("wrote", out)


if __name__ == "__main__":
    main()
