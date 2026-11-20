"""note「スコップを渡された人たち」寸劇アニメ（漫画動画方式。台本 script.md に従う）

全体段階（その1：寸劇）：つかみ H0 と寸劇 K0〜K14（台詞 #1〜#89）を実装している。
解説（X・E1〜E10）は素材待ちのため未実装（scene_x など場面の関数を足して build() から呼ぶ）。
前の試作は versions/episode_prototype_v1.py。

使い方（リポジトリ直下で）:
    python3 video/episodes/shovel/episode.py --stills   # 確認用の静止画と一覧画像
    python3 video/episodes/shovel/episode.py --sample   # 見本（H0〜K1 まで）ではなく K0〜K1 だけの MP4（互換）
    python3 video/episodes/shovel/episode.py            # 寸劇（H0＋K0〜K14）の MP4 → video/out/shovel_skit_vN.mp4
"""
import glob
import math
import os
import random
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "..", "lib")
sys.path.insert(0, LIB)
import core  # noqa: E402
from core import (H, SR, W, INK, Tachie, Timeline, Voicevox, caption, clamp, ease_back,  # noqa: E402
                  ease_io, ease_out, fill_stroke, hexc, latest, lerp, render, rrect, text)
from voice_preview import load_lines, load_tuning, load_voices  # noqa: E402
import cairo  # noqa: E402
from PIL import Image, ImageFilter  # noqa: E402

ROOT = os.path.join(HERE, "..", "..")
OUT = os.path.join(ROOT, "out")
IMG = os.path.join(ROOT, "assets", "images", "shovel")
BGM_SKIT = os.path.join(ROOT, "assets", "bgm", "bgm_skit_light.mp3")
SE_DIR = os.path.join(ROOT, "assets", "se")

# ---------------------------------------------------------------- 配役（characters.md の「声の割り当て」）
CAST = {
    "narr": {"id": 11, "speed": 1.08},    # アキヒロ：玄野武宏
    "boss": {"id": 13, "speed": 1.05},    # 偉い人：青山龍星（熱血=81, 焦り=81, 不機嫌=82, 喜び=83, 困り=85）
    "a": {"id": 67, "speed": 1.1},        # 行員A：栗田まろん
    "b": {"id": 8, "speed": 1.1},         # 行員B：春日部つむぎ
    "c": {"id": 52, "speed": 1.0},        # 行員C：雀松朱司
    "senpai": {"id": 21, "speed": 1.12},  # 窓口の先輩：剣崎雌雄
}
NAMES = {"narr": "アキヒロ", "boss": "偉い人", "a": "行員A", "b": "行員B", "c": "行員C",
         "senpai": "窓口の先輩", "a+b+c": "行員たち"}
COLORS = {"narr": hexc("#3D5A80"), "boss": hexc("#24324F"), "a": hexc("#3E78C8"),
          "b": hexc("#4E9A55"), "c": hexc("#C0563F"), "senpai": hexc("#8A6A3A"),
          "a+b+c": hexc("#7A5A8A")}
CREDIT = ["VOICEVOX:玄野武宏", "VOICEVOX:青山龍星", "VOICEVOX:栗田まろん",
          "VOICEVOX:春日部つむぎ", "VOICEVOX:雀松朱司", "VOICEVOX:剣崎雌雄"]

# 台本・声の表は md から読む（voice_preview.py と同じ読み方）
VOICES = load_voices(os.path.join(HERE, "characters.md"))
SCRIPT = {ln["no"]: ln for ln in load_lines(os.path.join(HERE, "script.md"))}
TUNING = load_tuning(os.path.join(HERE, "sound.md"))

CAP_BY = 866  # 字幕枠の上端（右下の注記と接しないよう、既定の 880 から少し上げる）


def say_no(tl, no, **kw):
    """台本の #no を tl.say() 1回で合成する。字幕は「台詞」、合成は「読み」（あれば）、
    声ID・話速・高さ・抑揚・間は sound.md の「台詞の調整」、調子別IDは characters.md。"""
    ln, tu = SCRIPT[str(no)], TUNING.get(str(no), {})
    whos = ln["who"].replace(" ", "").split("+")
    ids = []
    for w in whos:
        v = VOICES[w]
        ids.append(tu.get("id") or next((i for k, i in v["styles"].items() if k in ln["tone"]), v["id"]))
    args = dict(voice=ln["yomi"] or None, ids=ids, speed=tu.get("speed"), pitch=tu.get("pitch"),
                intonation=tu.get("intonation"), pause=tu.get("pause") or 1.0,
                pre=tu.get("pre") or 0.0, gap=tu.get("gap") if tu.get("gap") is not None else 0.6)
    args.update(kw)
    return tl.say(whos if len(whos) > 1 else whos[0], ln["text"], **args)


# ---------------------------------------------------------------- 効果音（素材ファイルの切り出し）
def sfx_file(tl, name, at, vol, dur=None, speed=1.0, fade=0.06):
    """assets/se の素材を読み、speed 倍速にして先頭から dur 秒に切って tl に置く（末尾は fade 秒で消す）。"""
    a = core.load_audio(latest(os.path.join(SE_DIR, f"se_{name}.mp3")))
    if speed != 1.0:
        n = int(len(a) / speed)
        a = np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)
    if dur is not None:
        a = a[:int(dur * SR)].copy()
    k = min(len(a), int(fade * SR))
    if k > 0:
        a[-k:] *= np.linspace(1, 0, k).astype(np.float32)
    tl.clips.append((at, a * vol))


# ---------------------------------------------------------------- 画像
def _img(name):
    return os.path.join(IMG, name + ".png")


def _faces(who, spec):
    """spec: {表情名: (基準, 口開き or None, 半開き or None)}（ファイル名の「shovel_<who>_」以降）。"""
    out = {}
    for fname, (b, o, h) in spec.items():
        d = dict(base=_img(f"shovel_{who}_{b}"))
        if o:
            d["open"] = _img(f"shovel_{who}_{o}")
        if h:
            d["half"] = _img(f"shovel_{who}_{h}")
        out[fname] = d
    return out


def load_tachie():
    return {
        "boss": Tachie(_faces("boss", {"base": ("base", "mouth_open", "mouth_half"),
                                       "trouble": ("trouble", "trouble_open", None),
                                       "proud": ("proud", "proud_open", None),
                                       "aged": ("aged", None, None)})),
        "a": Tachie(_faces("a", {"base": ("base", "mouth_open", "mouth_half"),
                                 "grin": ("grin", "grin_open", None),
                                 "surprise": ("surprise", "surprise_open", None),
                                 "sad": ("sad", "sad_open", None),
                                 "aged": ("aged", None, None)})),
        "b": Tachie(_faces("b", {"base": ("base", "mouth_open", "mouth_half"),
                                 "trouble": ("trouble", "trouble_open", None),
                                 "aged": ("aged", None, None)})),
        "c": Tachie(_faces("c", {"base": ("base", "mouth_open", "mouth_half"),
                                 "trouble": ("trouble", "trouble_open", None),
                                 "aged": ("aged", None, None)})),
        "senpai": Tachie(_faces("senpai", {"base": ("base", "mouth_open", "mouth_half"),
                                           "smile": ("smile", "smile_open", None),
                                           "trouble": ("trouble", "trouble_open", None),
                                           "aged": ("aged", None, None)})),
    }


BG_FILES = {
    "office": "shovel_bg_branch_office", "project": "shovel_bg_hq_project", "full": "shovel_bg_hq_project_full",
    "busy": "shovel_bg_counter_busy", "day": "shovel_bg_counter_day", "later": "shovel_bg_counter_later",
    "night": "shovel_bg_counter_night", "desk": "shovel_bg_hq_desk", "big": "shovel_bg_hq_bigscreen",
    "stage": "shovel_bg_award_stage",
}
_bg_cache = {}


def cover_bg(path, blur):
    """背景を 1920×1080 に合わせて拡大・切り出し、blur（半径）でぼかして cairo の面にする。"""
    path = latest(path)
    key = f"{os.path.splitext(os.path.basename(path))[0]}_{int(os.path.getmtime(path))}_cover_b{blur}"
    cache = os.path.join(core.CACHE_DIR, key + ".png")
    if not os.path.exists(cache):
        im = Image.open(path).convert("RGB")
        s = max(W / im.width, H / im.height)
        im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
        x0, y0 = (im.width - W) // 2, (im.height - H) // 2
        im = im.crop((x0, y0, x0 + W, y0 + H))
        if blur:
            im = im.filter(ImageFilter.GaussianBlur(blur))
        os.makedirs(core.CACHE_DIR, exist_ok=True)
        im.save(cache)
    return core.load_image(cache)


def get_bg(name, blur=0):
    k = (name, blur)
    if k not in _bg_cache:
        _bg_cache[k] = cover_bg(os.path.join(IMG, BG_FILES[name] + ".png"), blur)
    return _bg_cache[k]


# ---------------------------------------------------------------- 描画部品
def note_fiction(ctx, small=True, alpha=1.0, center=False):
    """「※この物語はフィクションです」。K0 は下に大きめ、それ以外は小さく（右下。H0 の頭だけ下の中央）。"""
    s = "※この物語はフィクションです"
    if small:
        # 字幕枠の下端（CAP_BY+170）から十分離す
        if center:
            text(ctx, s, W / 2, H - 14, 22, (0.25, 0.25, 0.28, 0.9 * alpha), bold=False,
                 outline=(1, 1, 1, 0.8 * alpha), ow=5)
        else:
            text(ctx, s, W - 24, H - 14, 21, (0.25, 0.25, 0.28, 0.9 * alpha), align="right", bold=False,
                 outline=(1, 1, 1, 0.8 * alpha), ow=5)
    else:
        text(ctx, s, W / 2, H - 56, 32, (0.2, 0.2, 0.24, alpha), bold=False, outline=(1, 1, 1, 0.85 * alpha), ow=7)


def years_later(ctx, alpha=1.0):
    """左上の小さな「数年後（作者の想像）」。"""
    if alpha <= 0:
        return
    rrect(ctx, 24, 22, 372, 52, 12)
    fill_stroke(ctx, (1, 1, 1, 0.86 * alpha), (0.35, 0.35, 0.4, 0.8 * alpha), 3)
    text(ctx, "数年後（作者の想像）", 210, 48, 27, (0.22, 0.22, 0.27, alpha))


def paper(ctx, x, y, rot, s=1.0):
    """無地の辞令（白い紙。文字は描かない）。"""
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(rot)
    ctx.scale(s, s)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    rrect(ctx, -105, -140, 210, 280, 6)
    fill_stroke(ctx, (1, 1, 1, 1), INK, 6)
    ctx.restore()


def hand_arm(ctx, x0, y0, x1, y1, sleeve, lw=64):
    """肩側 (x0,y0) から手 (x1,y1) までの腕と手（袖と肌）。"""
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_width(lw)
    ctx.set_source_rgba(*INK)
    ctx.move_to(x0, y0)
    ctx.line_to(x1, y1)
    ctx.stroke()
    ctx.set_line_width(lw - 14)
    ctx.set_source_rgba(*sleeve)
    ctx.move_to(x0, y0)
    ctx.line_to(x1, y1)
    ctx.stroke()
    ctx.arc(x1, y1, lw * 0.47, 0, 2 * math.pi)
    fill_stroke(ctx, core.SKIN, INK, 5)


def bubble(ctx, cx, cy, w, h, s, al=1.0, size=34, tail=None, glow=0.0):
    """落ち着いた返答の吹き出し（白地に灰色の枠。赤い警告にしない）。s の改行で複数行。
    tail=(x, y) はしっぽの先。"""
    if al <= 0:
        return
    ctx.save()
    gray = (0.5, 0.53, 0.58, al)
    if tail is not None:
        tx, ty = tail
        if ty > cy:  # 下向き
            bx = clamp(tx, cx - w / 2 + 36, cx + w / 2 - 36)
            ctx.move_to(bx - 20, cy + h / 2 - 4)
            ctx.line_to(tx, ty)
            ctx.line_to(bx + 20, cy + h / 2 - 4)
        else:  # 横向き（左）
            by = clamp(ty, cy - h / 2 + 30, cy + h / 2 - 30)
            ctx.move_to(cx - w / 2 + 4, by - 18)
            ctx.line_to(tx, ty)
            ctx.line_to(cx - w / 2 + 4, by + 18)
        ctx.close_path()
        fill_stroke(ctx, (1, 1, 1, al), gray, 5)
    if glow > 0:
        rrect(ctx, cx - w / 2 - 10, cy - h / 2 - 10, w + 20, h + 20, 28)
        ctx.set_source_rgba(1, 0.95, 0.7, 0.35 * glow * al)
        ctx.fill()
    rrect(ctx, cx - w / 2, cy - h / 2, w, h, 20)
    fill_stroke(ctx, (1, 1, 1, al), gray, 5)
    lines = s.split("\n")
    lh = size * 1.28
    y0 = cy - (len(lines) - 1) * lh / 2
    for i, ln in enumerate(lines):
        text(ctx, ln, cx, y0 + i * lh, size, (0.27, 0.29, 0.34, al))
    ctx.restore()


NOTE_COLORS = [hexc("#FFE680"), hexc("#FFB4C6"), hexc("#FFC68A"), hexc("#FFF2A0"), hexc("#F7A8BE")]


def sticky(ctx, cx, cy, w, h, lines=None, size=24, color=None, rot=0.0, sc=1.0, al=1.0):
    color = color or NOTE_COLORS[0]
    ctx.save()
    ctx.translate(cx, cy)
    ctx.rotate(rot)
    ctx.scale(sc, sc)
    rrect(ctx, -w / 2 + 3, -h / 2 + 4, w, h, 4)
    ctx.set_source_rgba(0, 0, 0, 0.16 * al)
    ctx.fill()
    rrect(ctx, -w / 2, -h / 2, w, h, 4)
    fill_stroke(ctx, color[:3] + (al,), (0.55, 0.45, 0.2, 0.9 * al), 2)
    if lines:
        lh = size * 1.25
        y0 = -(len(lines) - 1) * lh / 2
        for i, ln in enumerate(lines):
            text(ctx, ln, 0, y0 + i * lh, size, (0.27, 0.2, 0.1, al))
    ctx.restore()


def laptop(ctx, x, y, rows_u=None, t=0.0, screen_fn=None, s=0.8):
    """ノートパソコン（画面はこちら向き。中身は動画側）。(x, y) は画面の中心。"""
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(s, s)
    rrect(ctx, -132, -82, 264, 164, 10)
    fill_stroke(ctx, hexc("#58606E"), INK, 5)
    ctx.save()
    rrect(ctx, -118, -68, 236, 136, 4)
    ctx.clip_preserve()
    ctx.set_source_rgba(*hexc("#1E2433"))
    ctx.fill()
    if screen_fn:
        screen_fn(ctx)
    elif rows_u is not None:
        rnd = random.Random(7)
        pal = [hexc("#6FB1FF"), hexc("#7EE0A0"), hexc("#FFC46B"), hexc("#FF8FB1"), hexc("#D8DEE9")]
        n = int(rows_u * 7)
        off = max(0.0, rows_u * 7 - 9) * 13
        for i in range(n + 1):
            wv = rnd.uniform(0.25, 0.9) * 200
            ind = rnd.choice([0, 0, 18, 36])
            yy = -58 + i * 13 - off
            rrect(ctx, -106 + ind, yy, wv, 7, 3)
            ctx.set_source_rgba(*rnd.choice(pal)[:3], 0.95)
            ctx.fill()
    ctx.restore()
    rrect(ctx, -158, 84, 316, 16, 6)
    fill_stroke(ctx, hexc("#C9CFD8"), INK, 4)
    ctx.restore()


def burst(ctx, x, y, r, al=1.0, n=7, col=INK):
    """驚きの漫符（放射状の短い線）。"""
    ctx.save()
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_width(7)
    ctx.set_source_rgba(*col[:3], al)
    for i in range(n):
        a = -math.pi / 2 + (i - (n - 1) / 2) * 0.42
        ctx.move_to(x + math.cos(a) * r, y + math.sin(a) * r)
        ctx.line_to(x + math.cos(a) * (r + 34), y + math.sin(a) * (r + 34))
        ctx.stroke()
    ctx.restore()


def blue_lines(ctx, x, y, w, h, al=1.0):
    """青ざめた縦線。"""
    ctx.save()
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_width(6)
    n = 9
    for i in range(n):
        xx = x - w / 2 + w * (i + 0.5) / n
        ln = h * (0.7 + 0.3 * ((i * 5) % 3) / 2)
        ctx.set_source_rgba(0.28, 0.38, 0.72, 0.75 * al)
        ctx.move_to(xx, y)
        ctx.line_to(xx, y + ln)
        ctx.stroke()
    ctx.restore()


def silhouette(ctx, x, y, s=1.0, al=1.0):
    """席に座る別の人のシルエット（顔なしの単純な人影）。(x, y) は肩の下端中央。"""
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(s, s)
    ctx.set_source_rgba(0.33, 0.35, 0.4, 0.92 * al)
    ctx.arc(0, -95, 34, 0, 2 * math.pi)
    ctx.fill()
    ctx.move_to(-62, 0)
    ctx.curve_to(-62, -48, -38, -62, 0, -62)
    ctx.curve_to(38, -62, 62, -48, 62, 0)
    ctx.close_path()
    ctx.fill()
    ctx.restore()


def calendar(ctx, cx, cy, s=1.0, flip=0.0, circle=0.0, stamp=0.0, al=1.0):
    """日めくり（日付・数字は出さない）。flip 0→1 で1枚めくれて新しい面（赤丸と「締め切り」）が出る。
    stamp 0→1 で赤丸に「完了」の判子。"""
    ctx.save()
    ctx.translate(cx, cy)
    ctx.scale(s, s)
    rrect(ctx, -92, -122, 184, 244, 10)
    fill_stroke(ctx, (0.93, 0.9, 0.82, al), INK[:3] + (al,), 5)
    # 新しい面
    rrect(ctx, -84, -96, 168, 210, 6)
    fill_stroke(ctx, (1, 1, 1, al), INK[:3] + (al,), 3)
    if flip > 0.55 or flip >= 1:
        ctx.set_line_width(9)
        ctx.set_source_rgba(0.85, 0.2, 0.18, al * clamp((flip - 0.55) / 0.2))
        ctx.arc(0, -10, 50 * clamp(circle), 0, 2 * math.pi)
        ctx.stroke()
        text(ctx, "締め切り", 0, 76, 30, (0.15, 0.15, 0.2, al * clamp((flip - 0.55) / 0.2)))
    # 上の綴じ
    rrect(ctx, -92, -122, 184, 28, 10)
    fill_stroke(ctx, (0.82, 0.22, 0.2, al), INK[:3] + (al,), 4)
    # めくれる1枚
    if flip < 1:
        k = ease_io(flip)
        ctx.save()
        ctx.translate(0, -96)
        ctx.scale(1, max(0.02, 1 - k))
        ctx.translate(0, 96)
        rrect(ctx, -84, -96, 168, 210, 6)
        fill_stroke(ctx, (1, 1, 1, al * (1 - k)), INK[:3] + (al * (1 - k),), 3)
        ctx.restore()
    if stamp > 0:
        k = ease_out(stamp)
        ctx.save()
        ctx.translate(0, -10)
        ctx.rotate(-0.2)
        ctx.scale(1 + 0.8 * (1 - k), 1 + 0.8 * (1 - k))
        ctx.set_source_rgba(0.82, 0.15, 0.15, 0.92 * clamp(stamp * 4))
        ctx.set_line_width(7)
        rrect(ctx, -64, -40, 128, 80, 14)
        ctx.stroke()
        text(ctx, "完了", 0, 0, 52, (0.82, 0.15, 0.15, 0.92 * clamp(stamp * 4)))
        ctx.restore()
    ctx.restore()


def phone_handset(ctx, x, y, al=1.0):
    """受話器（ear の位置 (x, y) が受話器の中心）。"""
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(0.2)
    rrect(ctx, -20, -88, 40, 176, 18)
    fill_stroke(ctx, (0.25, 0.27, 0.34, al), INK[:3] + (al,), 5)
    for yy in (-80, 80):
        rrect(ctx, -29, yy - 17, 58, 34, 12)
        fill_stroke(ctx, (0.18, 0.2, 0.26, al), INK[:3] + (al,), 5)
    ctx.restore()


# ---------------------------------------------------------------- 画面の状態（キーフレーム）
# 各キーフレーム：(開始時刻, 所要秒, 状態)。状態の人物は [x, 高さ, 不透明度, 薄め, 下げ(dy), 傾き(rad)]。
# blur は 0=ぼかしなし、1=ふつうのぼかし（会話ショットの背景）、2=強いぼかし（K0）。zoom はカメラの寄り。
GROUND_Y = H  # 立ち絵（胸から上）の下端は画面の下端にそろえる
X_BOSS = 360
PRESETS = {
    "all4": {"boss": (360, 770), "a": (900, 630), "b": (1280, 630), "c": (1660, 630)},
    "staff3": {"a": (480, 630), "b": (960, 630), "c": (1440, 630)},
    "k13": {"senpai": (290, 690), "boss": (870, 740), "a": (1290, 480), "b": (1540, 480), "c": (1770, 480)},
}
TALK_C = {  # 行員C を右に大きく。ほかの薄い像は C と重ならない位置・大きさ
    "all4": {"boss": (290, 700), "a": (650, 560), "b": (960, 560), "c": (1520, 900)},
    "staff3": {"a": (470, 540), "b": (880, 540), "c": (1470, 900)},
}


def layout(kind, who=None, preset="all4"):
    """配置の型。scene=場面ショット、conv=会話ショット（who が話者。リストも可）、talk_c=C を右に大きく、
    boss_push=偉い人を少し前へ。"""
    base = PRESETS[preset]
    st = {n: [x, h, 1.0, 0.0, 0.0, 0.0] for n, (x, h) in base.items()}
    if kind == "scene":
        return st
    for v in st.values():
        v[3] = 0.42  # 話していない人は透かさず、白っぽく淡くする（透かすと背景が顔に透けて幽霊のように見え、暗くすると肌の色が変わって見える）
    if kind == "talk_c":
        for n, (x, h) in TALK_C[preset].items():
            st[n][0], st[n][1] = x, h
        st["c"][3] = 0.0
        return st
    if kind == "boss_push":
        st["boss"][0], st["boss"][1] = 470, 880
        return st
    whos = who if isinstance(who, (list, tuple)) else [who]
    for w in whos:
        if w in st:
            st[w][3] = 0.0
            st[w][1] = st[w][1] * 1.1
    return st


class Stage:
    def __init__(self):
        self.kf = []

    def add(self, t, dur, chars, blur=1.0, zoom=1.0, pivot=(960, 540), bg="office", faces=None):
        chars = {n: (list(v) + [0.0] * 6)[:6] for n, v in chars.items()}
        self.kf.append(dict(t=t, dur=dur, chars=chars, blur=blur, zoom=zoom, pivot=pivot, bg=bg,
                            faces=dict(faces or {})))

    def at(self, t):
        cur = [k for k in self.kf if k["t"] <= t]
        i = len(cur) - 1
        k = cur[-1]
        p = self.kf[i - 1] if i > 0 else k
        cut = p["bg"] != k["bg"]
        u = 1.0 if cut else (ease_io((t - k["t"]) / k["dur"]) if k["dur"] > 0 else 1.0)
        chars = {}
        for n, v in k["chars"].items():
            if n in p["chars"] and not cut:
                chars[n] = [lerp(p["chars"][n][j], v[j], u) for j in range(6)]
            else:
                w = list(v)
                w[2] = v[2] * (1.0 if cut else u)
                chars[n] = w
        return dict(chars=chars, blur=lerp(p["blur"], k["blur"], u) if not cut else k["blur"],
                    zoom=lerp(p["zoom"], k["zoom"], u) if not cut else k["zoom"],
                    pivot=(lerp(p["pivot"][0], k["pivot"][0], u), lerp(p["pivot"][1], k["pivot"][1], u))
                    if not cut else k["pivot"], bg=k["bg"], faces=k["faces"])


def props_add(ev, t0, t1, fn, layer="world"):
    """演出の部品を登録する。fn(ctx, t) を t0〜t1 のあいだ呼ぶ。layer は world（カメラの寄りがかかる）か screen。"""
    ev.setdefault("props", []).append((t0, t1, fn, layer))


def conv(tl, stage, no, bg, preset, who, faces=None, kind="conv", dur=0.3, blur=1.0, zoom=1.0,
         pivot=(960, 540), chars=None, **kw):
    """会話ショット（または、立ち絵を自分で指定した場面ショット）を1つ置いて、台詞 #no を合成する。"""
    kt = tl.t
    st = chars if chars is not None else layout(kind, who, preset)
    stage.add(kt, dur, st, blur, zoom, pivot, bg, faces)
    return say_no(tl, no, **kw)


def lift(ch, dy):
    """立ち絵を dy だけ上げた指定（寄りのとき、顔を字幕枠より上に出す）。"""
    return {n: [v[0], v[1], v[2], v[3], dy, v[5]] for n, v in ch.items()}


def sc(ch, **over):
    """場面ショット用の立ち絵の指定（既定の配置に上書き）。over: 名前=(x, h) など。"""
    return {n: ([*v] if isinstance(v, list) else [v[0], v[1], 1.0, 0.0, 0.0, 0.0]) for n, v in {**ch, **over}.items()}


# ---------------------------------------------------------------- 台本（場面ごと）
H0_BOSS_SHOT = dict(zoom=1.2, pivot=(1000, 480))


def h0_boss_chars():
    return {"boss": [610, 780, 1.0, 0.0, 0.0, 0.0]}


def h0_three_chars():
    return {"a": [820, 600, 1.0, 0.0, 0.0, 0.0], "b": [1220, 600, 1.0, 0.0, 0.0, 0.0],
            "c": [1620, 600, 1.0, 0.0, 0.0, 0.0]}


def screen_bubble_prop(ev, t0, t1, appear=0.3):
    """H0 #1 と K12 の大画面の横の吹き出し「ルール改正に対応できません」（同じ見た目）。"""
    def fn(ctx, t):
        k = clamp((t - t0) / 0.2)
        if k <= 0:
            return
        ctx.save()
        ctx.translate(0, (1 - ease_out(k)) * 14)
        bubble(ctx, 1540, 250, 370, 150, "ルール改正に\n対応できません", al=k, size=36, tail=(1370, 300))
        ctx.restore()
    props_add(ev, t0, t1, fn)


def scene_h0(tl, stage, ev):
    """場面H0：つかみ（#1〜#4、数年後の先出し → 巻き戻して R3 の引き）。"""
    t0 = tl.t
    ev["h0"] = t0
    tl.scene("h0")
    # #1 偉い人（動画の最初のフレームから R10 の寄り）。0.3秒で吹き出し、続けて台詞
    stage.add(t0, 0.01, h0_boss_chars(), 0.0, H0_BOSS_SHOT["zoom"], H0_BOSS_SHOT["pivot"], "big", {"boss": "trouble"})
    sfx_file(tl, "notify_piron", t0 + 0.3, 0.35)
    a1, b1 = say_no(tl, 1)
    screen_bubble_prop(ev, t0 + 0.3, b1 + 1.0)
    ev.setdefault("shakes", []).append(("boss", a1, b1, 5))
    ev["h0_label"] = (t0, None)
    # #2 R10 の別の寄り（困り顔の少し老けた3人）
    kt = tl.t
    stage.add(kt, 0.01, h0_three_chars(), 0.0, 1.15, (1100, 540), "big", {"a": "aged", "b": "aged", "c": "aged"})
    a2, b2 = say_no(tl, 2)
    # #3 R3 の引き（巻き戻しの効果音。付せんに書き出しては貼る）
    kt = tl.t
    ev["a3"] = kt
    ev["h0_label"] = (t0, kt + 0.25)
    sfx_file(tl, "rewind", kt, 0.5, dur=0.45, fade=0.1)
    stage.add(kt, 0.01, {"a": [420, 520, 1, 0, 0, 0], "b": [760, 520, 1, 0, 0, 0], "c": [1100, 520, 1, 0, 0, 0]},
              0.0, 1.0, (1100, 330), "full", {"a": "grin", "b": "base", "c": "base"})
    a3, b3 = say_no(tl, 3)
    # 付せんを書き出しては貼る（ボードへ飛ぶ付せん）
    rnd = random.Random(3)
    flights = []
    for i in range(10):
        src = [(420, 600), (760, 600), (1100, 600)][i % 3]
        dst = (rnd.uniform(800, 1450), rnd.uniform(180, 430))
        flights.append((a3 + 0.5 + i * 0.5, src, dst, rnd.choice(NOTE_COLORS), rnd.uniform(-0.15, 0.15)))

    def fly(ctx, t):
        for ts, src, dst, col, rot in flights:
            u = (t - ts) / 0.55
            if u < 0:
                continue
            u = min(u, 1.0)
            e = ease_out(u)
            x, y = lerp(src[0], dst[0], e), lerp(src[1], dst[1], e) - 90 * math.sin(math.pi * e)
            sticky(ctx, x, y, 58, 50, None, color=col, rot=rot, sc=lerp(1.5, 1.0, e))
    props_add(ev, a3, tl.t + 1.0, fly)
    # #4 付せんで埋まったホワイトボードへゆっくり寄る
    kt = tl.t
    a4 = kt
    a, b = say_no(tl, 4)
    stage.add(a, b - a + 0.5, {"a": [420, 520, 1, 0, 0, 0], "b": [760, 520, 1, 0, 0, 0], "c": [1100, 520, 1, 0, 0, 0]},
              0.0, 1.3, (900, 330), "full", {"a": "grin", "b": "base", "c": "base"})
    tl.sfx("pop", at=b, vol=0.5)
    ev["black"] = (b + 0.05, tl.t)  # 後の間 0.5 秒で暗転
    ev["h0_end"] = tl.t


def scene_k0(tl, stage, ev):
    """場面K0：タイトル（R1 を強くぼかした上にタイトルだけ。台詞なし、5秒）。"""
    t0 = tl.t
    tl.scene("k0")
    ch = layout("scene")
    for v in ch.values():
        v[2] = 0.0
    stage.add(t0, 0.01, ch, 2.0, 1.0, (X_BOSS, 700), "office")
    ev["k0"] = t0
    ev["title_at"] = t0 + 0.4
    tl.sfx("pop", at=ev["title_at"], vol=0.5)
    tl.wait(5.0)


def scene_k1(tl, stage, ev):
    """場面K1：辞令（#5〜#13）。"""
    t0 = tl.t
    tl.scene("k1")
    PV = (X_BOSS, 700)
    # #5 場面ショット：看板の文字を1.5秒、そのあと台詞（偉い人へゆっくり寄る）
    stage.add(t0, 0.7, layout("scene"), 0.0, 1.0, PV, "office", {"boss": "base"})
    ev["k1"] = t0
    ev["sign"] = (t0 + 0.1, t0 + 1.6)
    tl.wait(1.5)
    a, b = say_no(tl, 5)
    stage.add(a, b - a, layout("scene"), 0.0, 1.1, PV, "office")

    def sign(ctx, t):
        s0, s1 = ev["sign"]
        al = clamp((t - s0) / 0.2) * clamp((s1 - t) / 0.2)
        if al <= 0:
            return
        # 壁の円形マークの右横の余白（背景を 1920×1080 に合わせた座標で、マークの中心はおよそ (375, 255)）
        cx, cy, w, h = 700, 255, 380, 74
        ctx.save()
        ctx.translate(0, (1 - ease_out(al)) * -10)
        rrect(ctx, cx - w / 2, cy - h / 2, w, h, 10)
        fill_stroke(ctx, (0.3, 0.3, 0.32, al), (0.13, 0.13, 0.16, al), 5)
        text(ctx, "サクラダ銀行", cx, cy, 44, (1, 1, 1, al))
        ctx.restore()
    props_add(ev, t0, t0 + 1.8, sign)

    # 辞令（無地の紙）：偉い人の胸の前から3人のほうへ。手は描かず、紙だけ（字幕枠にかからない高さ）
    def jirei(ctx, t, a=a, b=b):
        a0 = a - 0.2
        if not (a0 <= t <= b + 0.2):
            return
        u = ease_out((t - a0) / 1.2)
        al = clamp((t - a0) / 0.15) * clamp((b + 0.2 - t) / 0.2)
        ctx.push_group()
        paper(ctx, lerp(520, 640, u), lerp(690, 650, u), 0.12, 0.85)
        ctx.pop_group_to_source()
        ctx.paint_with_alpha(al)
    props_add(ev, a - 0.3, b + 0.3, jirei)
    fc = {"boss": "base", "a": "base", "b": "base", "c": "base"}
    for no, who in ((6, "a"), (7, "b")):
        conv(tl, stage, no, "office", "all4", who, fc, pivot=PV)
    # #8 偉い人：立ち絵を1回小さく跳ねさせる
    a8, b8 = conv(tl, stage, 8, "office", "all4", "boss", fc, pivot=PV)
    ev.setdefault("hops", []).append(("boss", a8))
    # #9 行員Cを右に大きく（台詞の前に0.3秒の間）
    conv(tl, stage, 9, "office", "all4", "c", fc, kind="talk_c", pivot=PV)
    # #10〜#12 K1 の並びに戻す
    for no, who in ((10, "boss"), (11, "a"), (12, "boss")):
        conv(tl, stage, no, "office", "all4", who, fc, pivot=PV)
    # #13 偉い人が少し前へ寄って3人を指さす。言い終わりで pop
    kt = tl.t
    stage.add(kt, 0.3, layout("conv", "boss"), 1.0, 1.0, PV, "office", fc)
    a, b = say_no(tl, 13)
    stage.add(a, 0.5, layout("boss_push"), 1.0, 1.0, PV, "office", fc)
    tl.sfx("pop", at=b, vol=0.5)
    ev["k1_end"] = b


def scene_k2(tl, stage, ev):
    """場面K2：研修（R2 研修室。ノートパソコンの画面にコードの線が流れる）。"""
    fc = {"a": "base", "b": "base", "c": "base"}
    ch = sc(layout("scene", preset="staff3"))
    for n in ch:
        ch[n][1] = 620
    kt = tl.t
    stage.add(kt, 0.01, ch, 0.0, 1.0, (960, 540), "project", {**fc, "a": "surprise"})
    a, b = say_no(tl, 14)
    sfx_file(tl, "typing", a, 0.3, dur=b - a + 0.2, fade=0.2)
    tl.sfx("whoosh", at=a + 0.3, vol=0.15)
    tl.sfx("whoosh", at=a + 1.8, vol=0.15)
    ev["k2"] = a

    def laptops(ctx, t, a=a):
        for n, x in (("a", 480), ("b", 960), ("c", 1440)):
            laptop(ctx, x, 815, rows_u=max(0.0, (t - a - 0.15) * 1.3), s=0.75)
    props_add(ev, a - 0.2, b + 0.35, laptops)
    ev.setdefault("shakes", []).append(("a", a, b, 3))
    for no, who in ((15, "b"),):
        conv(tl, stage, no, "project", "staff3", who, fc)
    conv(tl, stage, 16, "project", "staff3", "c", fc, kind="talk_c")
    # #17 パソコンの画面に寄る（人の役目の文字）
    kt = tl.t
    stage.add(kt, 0.4, ch, 0.0, 2.0, (0, 1060), "project", fc)
    a, b = say_no(tl, 17)

    def screen17(ctx, a=a):
        al = clamp((ctx_t[0] - a - 0.1) / 0.3)
        lines = ["人の役目：", "業務に合っているか、", "安全かを確かめる"]
        for i, ln in enumerate(lines):
            text(ctx, ln, 0, -36 + i * 34, 19, (0.93, 0.95, 1.0, al))
    ctx_t = [0.0]

    def laptop17(ctx, t):
        ctx_t[0] = t
        laptop(ctx, 480, 815, screen_fn=screen17, s=0.75)
    props_add(ev, kt, b + 0.4, laptop17)
    conv(tl, stage, 18, "project", "staff3", "b", fc)
    conv(tl, stage, 19, "project", "staff3", "c", fc, kind="talk_c")
    a, b = conv(tl, stage, 20, "project", "staff3", "a", {**fc, "a": "grin"})
    ev["shakes"].append(("a", a, b, 9))


def sticky_texts():
    return {
        "n1": ((880, 255), 200, 130, ["名義変更：", "奥の棚の、青い", "ファイルの", "3ページ目"], 22, 0),
        "n2": ((880, 392), 200, 96, ["窓口の段取り"], 26, 1),
        "n3": ((1125, 255), 200, 130, ["月末の締めの", "順番"], 26, 3),
        "n4": ((1125, 392), 200, 96, ["例外の手続き"], 26, 2),
        "n5": ((1370, 255), 200, 130, ["お客さんごとの", "事情"], 24, 0),
        "n6": ((1370, 392), 200, 96, ["営業の勘"], 28, 1),
    }


def scene_k3(tl, stage, ev):
    """場面K3：本番の案件（R3 本部のプロジェクト室。付せんを貼る）。"""
    fc = {"boss": "proud", "a": "base", "b": "base", "c": "base"}
    ch = sc({"a": (330, 520), "b": (680, 520), "c": (1030, 520), "boss": (1640, 640)})
    kt = tl.t
    stage.add(kt, 0.01, ch, 0.0, 1.0, (960, 540), "project", fc)
    a, b = say_no(tl, 21)
    ev["k3"] = a
    ST = sticky_texts()
    stuck = {}

    def monitor_text(ctx, t):
        text(ctx, "AIエージェント", 474, 245, 44, (0.2, 0.25, 0.36, 1))
        text(ctx, "（作成中）", 474, 305, 36, (0.3, 0.35, 0.45, 1))
    ev["k3_end_ref"] = [0.0]

    def notes(ctx, t):
        for key, ts in stuck.items():
            if t < ts:
                continue
            (cx, cy), w, h, lines, size, ci = ST[key]
            u = (t - ts) / 0.18
            s = lerp(1.5, 1.0, ease_out(u)) if u < 1 else 1.0
            sticky(ctx, cx, cy, w, h, lines, size, NOTE_COLORS[ci], rot=(ci - 1) * 0.03, sc=s, al=clamp(u * 3))
    ev["notes_stuck"] = stuck

    def peta(ts, vol):
        sfx_file(tl, "stickynote", ts, vol, dur=0.6, fade=0.1)
    # #22〜#24：行員の寄り（付せんの言葉は読める大きさ）
    cams = {"a": (560, 600), "b": (760, 600), "c": (960, 600)}
    a22, b22 = conv(tl, stage, 22, "project", "x", "a", fc, chars=sc(ch), blur=0.0, zoom=1.25, pivot=cams["a"], dur=0.5)
    stuck["n1"], stuck["n2"] = b22, b22 + 0.2
    peta(b22, 0.5)
    peta(b22 + 0.2, 0.3)
    a23, b23 = conv(tl, stage, 23, "project", "x", "b", fc, chars=sc(ch), blur=0.0, zoom=1.25, pivot=cams["b"], dur=0.5)
    stuck["n3"], stuck["n4"] = b23, b23 + 0.2
    peta(b23, 0.3)
    peta(b23 + 0.2, 0.3)
    a24, b24 = conv(tl, stage, 24, "project", "x", "c", fc, chars=sc(ch), blur=0.0, zoom=1.25, pivot=cams["c"], dur=0.5)
    stuck["n5"], stuck["n6"] = b24, b24 + 0.2
    peta(b24, 0.3)
    peta(b24 + 0.2, 0.3)
    # #25 引き：付せんが一気に増えてボードを埋める（0.1秒ずつ）
    kt = tl.t
    stage.add(kt, 0.5, ch, 0.0, 1.0, (960, 540), "project", fc)
    a25, b25 = say_no(tl, 25)
    fills = []
    rnd = random.Random(11)
    for r in range(4):
        for c in range(9):
            cx, cy = 790 + c * 80 + rnd.uniform(-6, 6), 180 + r * 68 + rnd.uniform(-5, 5)
            if True:
                fills.append((cx, cy, rnd.choice(NOTE_COLORS), rnd.uniform(-0.12, 0.12)))
    rnd.shuffle(fills)
    t_fill = a25 + 0.05

    def fill_notes(ctx, t):
        for i, (cx, cy, col, rot) in enumerate(fills):
            u = (t - (t_fill + i * 0.1)) / 0.15
            if u < 0:
                continue
            sticky(ctx, cx, cy, 70, 60, None, color=col, rot=rot, sc=lerp(1.6, 1.0, ease_out(min(u, 1))), al=clamp(u * 3))
    for i in range(8):
        sfx_file(tl, "stickynote", t_fill + i * 0.1, 0.3 + 0.03 * i, dur=0.25, fade=0.05)
    props_add(ev, a - 1, b25 + 0.3, lambda ctx, t: (fill_notes(ctx, t), notes(ctx, t)))
    props_add(ev, a - 1, b25 + 0.3, monitor_text)
    conv(tl, stage, 26, "full", "all4", "a", {**fc, "a": "grin"})


def handset_prop(ev, stage, tachie_ref, who, t0, t1, side=-1, sleeve=(0.72, 0.84, 0.93, 1)):
    """who の耳もとに受話器と手（その時刻の立ち絵の位置・大きさに合わせる）。"""
    def fn(ctx, t):
        st = stage.at(t)
        if who not in st["chars"]:
            return
        x, h, al, dim, dy, rot = st["chars"][who]
        tc = tachie_ref[who]
        w = h * tc.w / tc.h
        ex = x + side * 0.29 * w
        ey = GROUND_Y + 6 + dy - h + 0.36 * h
        k = clamp((t - t0) / 0.15) * clamp((t1 - t) / 0.15) * al
        if k <= 0:
            return
        ctx.push_group()
        phone_handset(ctx, ex, ey)
        # 肩 → ひじ（外へ張る）→ 手、の2本の腕（まっすぐな棒に見えないよう、ひじを曲げる）
        hx, hy = ex + side * 6, ey + 92
        sx, sy = x + side * 0.30 * w, GROUND_Y + 80
        mx, my = x + side * 0.56 * w, GROUND_Y - 200
        for lw_, col in ((84, INK), (70, sleeve)):
            ctx.set_line_cap(cairo.LINE_CAP_ROUND)
            ctx.set_line_join(cairo.LINE_JOIN_ROUND)
            ctx.set_line_width(lw_)
            ctx.set_source_rgba(*col)
            ctx.move_to(sx, sy)
            ctx.line_to(mx, my)
            ctx.line_to(hx, hy)
            ctx.stroke()
        ctx.arc(hx, hy, 40, 0, 2 * math.pi)
        fill_stroke(ctx, core.SKIN, INK, 5)
        ctx.pop_group_to_source()
        ctx.paint_with_alpha(k)
    props_add(ev, t0, t1, fn)


def inset_prop(ev, stage, tachie_ref, tl, t0, t1, who, face, bg, wx, wy, who_x, who_h, rect, scale=0.55):
    """電話の枠：先方の様子を小さく見せる（背景＋立ち絵）。rect=(x, y, w, h)。"""
    x, y, w, h = rect

    def fn(ctx, t):
        k = clamp((t - t0) / 0.2) * clamp((t1 - t) / 0.2)
        if k <= 0:
            return
        ctx.save()
        rrect(ctx, x, y, w, h, 24)
        ctx.clip_preserve()
        ctx.set_source_rgba(1, 1, 1, 1)
        ctx.fill_preserve()
        ctx.save()
        ctx.translate(x, y)
        ctx.scale(scale, scale)
        ctx.translate(-wx, -wy)
        ctx.set_source_surface(get_bg(bg, 0), 0, 0)
        ctx.paint()
        tachie_ref[who].draw(ctx, who_x, GROUND_Y + 6, who_h, mouth=tl.mouth(who, t), face=face)
        ctx.restore()
        ctx.restore()
        rrect(ctx, x, y, w, h, 24)
        ctx.set_source_rgba(0.2, 0.2, 0.25, k)
        ctx.set_line_width(9)
        ctx.stroke()
        # 電話のしるし（小さな受話器）
        ctx.save()
        ctx.translate(x + w - 34, y + 32)
        ctx.scale(0.28, 0.28)
        phone_handset(ctx, 0, 0)
        ctx.restore()
    props_add(ev, t0, t1, fn, layer="screen")


def memo_prop(ev, t0, t1, strike_at=None):
    """「奥の棚・青いファイル・3ページ目」のメモ（K4 の #30 と K11 の #72 で同じ見た目）。"""
    def fn(ctx, t):
        k = clamp((t - t0) / 0.2) * clamp((t1 - t) / 0.2)
        if k <= 0:
            return
        ctx.save()
        ctx.translate(40 + 235, 130)
        ctx.rotate(-0.03)
        rrect(ctx, -235, -38, 470, 76, 6)
        fill_stroke(ctx, (1, 0.93, 0.55, k), (0.55, 0.45, 0.2, k), 3)
        text(ctx, "奥の棚・青いファイル・3ページ目", 0, 0, 28, (0.27, 0.2, 0.1, k))
        if strike_at is not None and t >= strike_at:
            u = clamp((t - strike_at) / 0.35)
            ctx.set_source_rgba(0.82, 0.15, 0.15, k)
            ctx.set_line_width(7)
            ctx.move_to(-222, 0)
            ctx.line_to(-222 + 444 * ease_out(u), 0)
            ctx.stroke()
        ctx.restore()
    props_add(ev, t0, t1, fn, layer="screen")


def scene_k4(tl, stage, ev, tachie):
    """場面K4：抜けた窓口（R4。電話。先輩の声は動画側でこもらせる）。"""
    ring = tl.t
    sfx_file(tl, "phone_ring", ring, 0.5, dur=2.0, fade=0.12)
    fa = {"a": "base"}
    PH = dict(phone=True)
    kt = tl.t
    stage.add(kt, 0.01, {"senpai": [1450, 760, 1, 0, 0, 0]}, 0.0, 1.0, (1450, 520), "busy", {"senpai": "base"})
    a, b = say_no(tl, 27, **PH)
    stage.add(a, b - a, {"senpai": [1450, 760, 1, 0, 0, 0]}, 0.0, 1.1, (1450, 520), "busy", {"senpai": "base"})
    handset_prop(ev, stage, tachie, "senpai", ring + 0.9, b + 0.6, side=-1, sleeve=hexc("#6E4F3C"))
    # #28 行員A（本部 R3 のぼかし背景）、右に先輩を電話の枠で
    ch = {"a": [700, 780, 1, 0, 0, 0]}
    a28, b28 = conv(tl, stage, 28, "full", None, None, {"a": "base"}, chars=ch)
    inset_prop(ev, stage, tachie, tl, a28 - 0.3, b28 + 0.3, "senpai", "base", "busy", 1068, 270, 1450, 760,
               (1440, 100, 420, 360))
    handset_prop(ev, stage, tachie, "a", a28 - 0.3, b28 + 0.3, side=-1)
    # #29 先輩（汗だく）を大きく、行員A は枠の中に
    ch = {"senpai": [1150, 880, 1, 0, 0, 0]}
    a29, b29 = conv(tl, stage, 29, "busy", None, None, {"senpai": "base"}, chars=ch, **PH)
    inset_prop(ev, stage, tachie, tl, a29 - 0.3, b29 + 0.3, "a", "base", "full", 340, 340, 640, 640,
               (90, 100, 400, 360))
    handset_prop(ev, stage, tachie, "senpai", a29 - 0.3, b29 + 0.3, side=-1, sleeve=hexc("#6E4F3C"))
    # #30 行員A 張り切った笑顔。メモ
    ch = {"a": [700, 780, 1, 0, 0, 0]}
    a30, b30 = conv(tl, stage, 30, "full", None, None, {"a": "grin"}, chars=ch)
    inset_prop(ev, stage, tachie, tl, a30 - 0.3, b30 + 0.3, "senpai", "base", "busy", 1068, 270, 1450, 760,
               (1440, 100, 420, 360))
    handset_prop(ev, stage, tachie, "a", a30 - 0.3, b30 + 0.3, side=-1)
    memo_prop(ev, a30, b30 + 1.8)
    # #31 先輩 ほっとした笑顔（汗は消える）
    ch = {"senpai": [1150, 880, 1, 0, 0, 0]}
    a31, b31 = conv(tl, stage, 31, "busy", None, None, {"senpai": "smile"}, chars=ch, **PH)
    inset_prop(ev, stage, tachie, tl, a31 - 0.3, b31 + 0.3, "a", "grin", "full", 340, 340, 640, 640,
               (90, 100, 400, 360))
    handset_prop(ev, stage, tachie, "senpai", a31 - 0.3, b31 + 0.3, side=-1, sleeve=hexc("#6E4F3C"))
    # #32 行員A：後半で少しうつむく。受話器アイコンは消える
    ch = {"a": [700, 780, 1, 0, 0, 0]}
    kt = tl.t
    stage.add(kt, 0.3, ch, 1.0, 1.0, (960, 540), "full", {"a": "base"})
    a32, b32 = say_no(tl, 32)
    stage.add(a32 + (b32 - a32) * 0.45, 0.8, {"a": [700, 780, 1, 0, 40, -0.05]}, 1.0, 1.0, (960, 540), "full",
              {"a": "sad"})
    inset_prop(ev, stage, tachie, tl, a32 - 0.3, a32 + (b32 - a32) * 0.55, "senpai", "smile", "busy", 1068, 270,
               1450, 760, (1440, 100, 420, 360))
    handset_prop(ev, stage, tachie, "a", a32 - 0.3, a32 + (b32 - a32) * 0.55, side=-1)


def scene_k5(tl, stage, ev):
    """場面K5：締め切り（R3 の寄り。日めくり）。"""
    fc = {"boss": "proud", "a": "base", "b": "base", "c": "base"}
    kt = tl.t
    a, b = None, None
    stage.add(kt, 0.01, {"b": [1150, 640, 1, 0, -110, 0]}, 0.0, 1.4, (1650, 480), "full", {"b": "base"})
    a, b = say_no(tl, 33)
    cal = dict(flip_at=a + 0.5)

    def cal_world(ctx, t):
        u = clamp((t - cal["flip_at"]) / 0.7)
        calendar(ctx, 1720, 330, 1.0, flip=u, circle=ease_out(clamp((t - cal["flip_at"] - 0.6) / 0.4)))
    props_add(ev, kt - 0.1, b + 0.3, cal_world)
    # #34〜#36：会話ショット（日めくりは右上の隅に小さく）
    a34 = None
    ch2 = {"boss": [520, 770, 1, 0, 0, 0], "b": [1260, 630, 1, 0.42, 0, 0]}
    a34, b34 = conv(tl, stage, 34, "full", None, None, fc, chars=ch2)
    ch3 = layout("conv", "a")
    a35, b35 = conv(tl, stage, 35, "full", "all4", "a", {**fc, "a": "sad"})
    a36, b36 = conv(tl, stage, 36, "full", "all4", "boss", fc)
    st_at = b36

    def cal_corner(ctx, t):
        calendar(ctx, 1760, 190, 0.8, flip=1.0, circle=1.0, stamp=clamp((t - st_at) / 0.25))
    props_add(ev, a34 - 0.3, b36 + 1.2, cal_corner, layer="screen")
    tl.sfx("thud", at=b36, vol=0.4)


def scene_k6(tl, stage, ev):
    """場面K6：本部の新しい席（R5。窓の外に遠い支店）。"""
    fc = {"a": "base", "b": "base", "c": "base"}
    ch = sc({"a": (480, 560), "b": (960, 560), "c": (1440, 560)})
    kt = tl.t
    stage.add(kt, 0.01, ch, 0.0, 1.12, (700, 560), "desk", {**fc, "a": "grin"})
    a, b = say_no(tl, 37)
    stage.add(a, b - a, ch, 0.0, 1.12, (1250, 560), "desk", {**fc, "a": "grin"})
    a38, b38 = conv(tl, stage, 38, "desk", "staff3", "a", {**fc, "a": "grin"})

    def card(ctx, t):
        k = ease_back(clamp((t - a38) / 0.35))
        if k <= 0:
            return
        x, y = 480 + 250, 760
        ctx.save()
        ctx.push_group()
        hand_arm(ctx, x + 60, 1180, x + 20, y + 56, hexc("#BFD9EE"), lw=52)
        ctx.translate(x, y)
        ctx.rotate(-0.07)
        ctx.scale(k, k)
        rrect(ctx, -115, -66, 230, 132, 6)
        fill_stroke(ctx, (1, 1, 1, 1), INK, 4)
        text(ctx, "エンジニア", 0, 0, 38, (0.18, 0.18, 0.22, 1))
        ctx.pop_group_to_source()
        ctx.paint_with_alpha(clamp((b38 + 0.4 - t) / 0.3))
        ctx.restore()
    props_add(ev, a38, b38 + 0.5, card)
    conv(tl, stage, 39, "desk", "staff3", "b", fc)
    conv(tl, stage, 40, "desk", "staff3", "c", fc, kind="talk_c")
    window_look(tl, stage, ev, 41, fc)
    conv(tl, stage, 42, "desk", "staff3", "b", fc)
    conv(tl, stage, 43, "desk", "staff3", "a", {**fc, "a": "sad"})


def window_look(tl, stage, ev, no, fc, face="base"):
    """行員A が窓の外の遠い支店のほうを見る寄り（K6 #41、K9 #61）。"""
    ch = {"a": [800, 640, 1, 0, -130, 0]}
    return conv(tl, stage, no, "desk", None, None, {"a": face}, chars=ch, blur=0.0, zoom=1.5, pivot=(600, 440),
                dur=0.4)


def scene_k7(tl, stage, ev):
    """場面K7：完成と表彰式（R6 → R7）。"""
    fc = {"boss": "proud", "a": "base", "b": "base", "c": "base"}
    ch = sc({"a": (560, 520), "b": (900, 520), "c": (1240, 520), "boss": (1640, 640)})
    kt = tl.t
    stage.add(kt, 0.01, ch, 0.0, 1.0, (960, 540), "stage", fc)
    a, b = say_no(tl, 44)
    sfx_file(tl, "fanfare", a, 0.3, dur=1.9, fade=0.2)
    ev["k7"] = a
    ev.setdefault("hops", []).append(("boss", a + 0.3))

    def bigscreen(ctx, t):
        text(ctx, "AIエージェント", 958, 250, 76, (0.2, 0.23, 0.32, clamp((t - kt) / 0.3)))
    props_add(ev, kt, tl.t + 6, bigscreen)
    # #45 大画面に寄る。言い終わりの0.3秒後に吹き出し
    kt2 = tl.t
    stage.add(kt2, 0.5, ch, 0.0, 1.7, (958, 400), "stage", fc)
    a45, b45 = say_no(tl, 45)
    tb = b45 + 0.3

    def ans(ctx, t):
        k = clamp((t - tb) / 0.12)
        if k > 0:
            bubble(ctx, 958, 440, 640, 96, "奥の棚の、青いファイルの3ページ目です", al=k, size=34)
    props_add(ev, tb, tb + 3, ans)
    ev["k7_ans"] = tb
    sfx_file(tl, "notify_piron", tb, 0.4)
    sfx_file(tl, "applause", tb + 0.4, 0.35, dur=1.1 + 0.4, fade=0.5)

    conv(tl, stage, 46, "stage", "all4", "a", {**fc, "a": "sad"})
    # #47 壇上に寄る。表彰状
    kt3 = tl.t
    stage.add(kt3, 0.4, lift(ch, -90), 0.0, 1.2, (900, 700), "stage", fc)
    a47, b47 = say_no(tl, 47)
    sfx_file(tl, "applause", a47 + 0.3, 0.3, dur=2.5, fade=0.4)

    def awards(ctx, t):
        for x in (560, 900, 1240):
            k = ease_back(clamp((t - a47 - 0.2) / 0.4))
            if k <= 0:
                continue
            ctx.save()
            ctx.translate(x, 800)
            ctx.rotate(0.04)
            ctx.scale(k, k)
            rrect(ctx, -100, -62, 200, 124, 6)
            fill_stroke(ctx, (1, 0.98, 0.9, 1), hexc("#C9A227"), 8)
            text(ctx, "表彰状", 0, 0, 40, (0.25, 0.2, 0.1, 1))
            ctx.restore()
    props_add(ev, a47, b47 + 0.7, awards)
    a48, b48 = conv(tl, stage, 48, "stage", "all4", "boss", {**fc, "boss": "proud"})
    # #49 R7：支店の窓口の端末（行列は消えている）
    kt4 = tl.t
    stage.add(kt4, 0.01, {"senpai": [1150, 740, 1, 0, 0, 0]}, 0.0, 1.0, (960, 540), "day", {"senpai": "smile"})
    a49, b49 = say_no(tl, 49, phone=False)

    def term(ctx, t):
        k = clamp((t - kt4 - 0.2) / 0.15)
        bubble(ctx, 1590, 300, 540, 96, "奥の棚の、青いファイルの3ページ目です", al=k, size=26, tail=(1700, 410))
    props_add(ev, kt4, b49 + 0.6, term)
    conv(tl, stage, 50, "stage", "all4", "b", fc)
    conv(tl, stage, 51, "stage", "all4", "c", fc, kind="talk_c")


def scene_k8(tl, stage, ev):
    """場面K8：保守の担当（R5）。"""
    fc = {"boss": "proud", "a": "base", "b": "base", "c": "base"}
    ch = sc({"a": (480, 560), "b": (960, 560), "c": (1440, 560)})
    kt = tl.t
    stage.add(kt, 0.01, lift(ch, -100), 0.0, 1.7, (990, 520), "desk", fc)
    a, b = say_no(tl, 52)

    def mon(ctx, t):
        k = clamp((t - kt - 0.3) / 0.2)
        bubble(ctx, 994, 480, 140, 66, "奥の棚の、青い\nファイルの3\nページ目です", al=k, size=12.5)
    props_add(ev, kt, b + 0.4, mon)
    a53, b53 = conv(tl, stage, 53, "desk", "all4", "boss", fc)

    def tags(ctx, t):
        k = ease_back(clamp((t - b53) / 0.35))
        if k <= 0:
            return
        for x in (900, 1280, 1660):
            ctx.save()
            ctx.translate(x, 345)
            ctx.scale(k, k)
            rrect(ctx, -105, -30, 210, 60, 10)
            fill_stroke(ctx, hexc("#7B5B3A"), INK, 5)
            text(ctx, "保守の担当", 0, 0, 32, (1, 1, 1, 1))
            ctx.restore()
    tl.sfx("pop", at=b53, vol=0.5)
    ev["k8_tags"] = b53
    kk = tl.t
    conv_after = []
    a54, b54 = conv(tl, stage, 54, "desk", "all4", "a", {**fc, "a": "grin"})
    a55, b55 = conv(tl, stage, 55, "desk", "all4", "a", {**fc, "a": "surprise"})
    a56, b56 = conv(tl, stage, 56, "desk", "all4", "boss", fc)
    ev.setdefault("hops", []).append(("boss", a56 + 0.1))
    a57, b57 = conv(tl, stage, 57, "desk", "all4", "c", {**fc, "c": "trouble"}, kind="talk_c")
    a58, b58 = conv(tl, stage, 58, "desk", "all4", "b", fc)
    props_add(ev, b53, b58 + 0.4, tags)


def notif(ctx, cx, cy, s, al=1.0, w=290):
    rrect(ctx, cx - w / 2, cy - 27, w, 54, 14)
    fill_stroke(ctx, (1, 1, 1, 0.97 * al), (0.5, 0.53, 0.58, al), 3)
    ctx.arc(cx - w / 2 + 28, cy, 12, 0, 2 * math.pi)
    ctx.set_source_rgba(0.45, 0.6, 0.85, al)
    ctx.fill()
    text(ctx, s, cx - w / 2 + 52, cy, 22, (0.27, 0.29, 0.34, al), align="left")


def scene_k9(tl, stage, ev):
    """場面K9：届くだけの知らせ（R8。通知がたまるモニター）。"""
    fc = {"a": "base", "b": "base", "c": "base"}
    ch = sc({"a": (480, 560), "b": (960, 560), "c": (1440, 560)})
    kt = tl.t
    stage.add(kt, 0.01, ch, 0.0, 1.0, (960, 540), "desk", {**fc, "a": "surprise"})
    a, b = say_no(tl, 59)
    mx = (584, 994, 1488)
    names = ("新商品のお知らせ", "ルール改正のお知らせ", "手続き変更のお知らせ")
    spawns = []
    for i in range(9):
        ts = a + 0.6 + 0.4 * i * (1 if i < 3 else 0.55)
        spawns.append((ts, i % 3, i // 3))
    for ts in (a + 0.6, a + 1.0, a + 1.4):
        sfx_file(tl, "notify_pikon", ts, 0.35, dur=0.5, fade=0.08)

    def pile(ctx, t):
        for ts, m, lvl in spawns:
            u = (t - ts) / 0.2
            if u < 0:
                continue
            k = ease_out(min(u, 1))
            ctx.save()
            ctx.translate(0, (1 - k) * 18)
            notif(ctx, mx[m], 395 - lvl * 62, names[m] if lvl == 0 else "お知らせ", al=clamp(u * 3))
            ctx.restore()
    props_add(ev, a, b + 0.4, pile)
    conv(tl, stage, 60, "desk", "staff3", "b", {**fc, "b": "trouble"})
    window_look(tl, stage, ev, 61, fc)
    conv(tl, stage, 62, "desk", "staff3", "b", fc)
    # #63 行員C の手元の手引き
    ch63 = {"c": [900, 560, 1, 0, 0, 0.06]}
    kt = tl.t
    stage.add(kt, 0.4, ch63, 0.0, 1.45, (1050, 720), "desk", {"c": "trouble"})
    a63, b63 = say_no(tl, 63)

    def booklet(ctx, t):
        k = ease_back(clamp((t - a63 + 0.2) / 0.35))
        ctx.save()
        ctx.translate(1180, 700)
        ctx.rotate(0.06)
        ctx.scale(k, k)
        ctx.push_group()
        hand_arm(ctx, 70, 380, 40, 150, hexc("#8A6A52"), lw=56)
        rrect(ctx, -105, -140, 210, 280, 8)
        fill_stroke(ctx, hexc("#F3EBD5"), INK, 5)
        text(ctx, "業務の手引き", 0, -30, 30, (0.25, 0.2, 0.12, 1))
        text(ctx, "作成：完成の日", 0, 36, 22, (0.35, 0.3, 0.2, 1))
        ctx.pop_group_to_source()
        ctx.paint()
        ctx.restore()
    props_add(ev, a63 - 0.4, b63 + 0.5, booklet)
    # #64 R8 の引き。通知があふれる
    kt = tl.t
    ch64 = sc({"a": (480, 560), "b": (960, 560), "c": (1440, 560)})
    stage.add(kt, 0.5, ch64, 0.0, 1.0, (960, 540), "desk", {**fc, "c": "trouble"})
    a64, b64 = say_no(tl, 64)
    rnd = random.Random(5)
    flood = []
    for i in range(16):
        flood.append((a64 + 0.2 + i * 0.17, rnd.uniform(380, 1540), rnd.uniform(160, 560), rnd.choice(names + ("お知らせ",))))

    def over(ctx, t):
        for ts, x, y, s in flood:
            u = (t - ts) / 0.2
            if u < 0:
                continue
            k = ease_out(min(u, 1))
            notif(ctx, x, y + (1 - k) * 20, s, al=clamp(u * 3))
    props_add(ev, a64, b64 + 0.4, over)
    sfx_file(tl, "notify_pikon", a64, 0.35, dur=0.5, fade=0.08)
    sfx_file(tl, "notify_pikon", a64 + 0.4, 0.35, dur=0.5, fade=0.08)


def counter_silhouettes(ctx, t, t0):
    k = clamp((t - t0) / 0.4)
    for x in (605, 961, 1317):
        silhouette(ctx, x, 480, 0.95, k)


def scene_k10(tl, stage, ev):
    """場面K10：記念写真と時の経過（R6 → R4 の寄り。ここから「数年後（作者の想像）」）。"""
    fc = {"boss": "proud", "a": "grin", "b": "base", "c": "base"}
    ch = sc({"a": (560, 520), "b": (900, 520), "c": (1240, 520), "boss": (1560, 640)})
    kt = tl.t
    stage.add(kt, 0.01, ch, 0.0, 1.0, (960, 540), "stage", fc)
    a65, b65 = say_no(tl, 65)
    ev["photo"] = [kt, None]
    ev.setdefault("hops", []).append(("boss", a65 + 0.4))
    a66, b66 = conv(tl, stage, 66, "stage", "all4", "a", {**fc, "a": "base"})
    kt = tl.t
    stage.add(kt, 0.3, ch, 0.0, 1.0, (960, 540), "stage", fc)
    a67, b67 = say_no(tl, 67)
    sfx_file(tl, "shutter", b67, 0.5)
    ev["flash"] = b67
    kt = tl.t
    stage.add(kt, 0.01, ch, 0.0, 1.0, (960, 540), "stage", fc)
    a68, b68 = say_no(tl, 68)
    ev["photo"][1] = b68 + 0.35
    # 写真の枠で静止 → 支店の窓口（昼）の寄りへ流れる。空いていた席に別の人
    stage.add(b68, 0.01, {}, 0.0, 1.4, (520, 480), "day", {})
    stage.add(b68 + 0.02, 1.95, {}, 0.0, 1.4, (1450, 480), "day", {})
    props_add(ev, b68, b68 + 2.2, lambda ctx, t: counter_silhouettes(ctx, t, b68 + 0.1))
    ev["years_from"] = b68 + 0.1
    sfx_file(tl, "clock_fast", b68 + 0.1, 0.4, dur=1.85, speed=2.0, fade=0.15)
    ev["jump"] = [(b68 + 0.1, "1年後"), (b68 + 0.7, "2年後"), (b68 + 1.3, "数年後")]
    ev["k10_end"] = tl.t


def scene_k11(tl, stage, ev, tachie):
    """場面K11：古い答え（R9 数年後の支店の窓口）。数年後なので全員 aged。"""
    SENP = [1260, 700, 1, 0, 0, 0]
    kt = tl.t
    stage.add(kt, 0.01, {"senpai": SENP}, 0.0, 1.0, (960, 540), "later", {"senpai": "aged"})
    a69, b69 = say_no(tl, 69)

    def term(ctx, t, kt=kt):
        k = clamp((t - kt - 0.3) / 0.15)
        bubble(ctx, 1570, 290, 540, 96, "奥の棚の、青いファイルの3ページ目です", al=k, size=26, tail=(1737, 390))
    props_add(ev, kt, tl.t + 0.2, term)
    ev.setdefault("shakes", []).append(("senpai", a69, b69, 3))
    # #70 先輩 困り
    conv(tl, stage, 70, "later", None, None, {"senpai": "aged"}, chars={"senpai": [1150, 880, 1, 0, 0, 0]})
    # #71 受話器。呼び出し音は K4 と同じ素材・同じ音量
    ring = tl.t
    sfx_file(tl, "phone_ring", ring, 0.5, dur=2.0, fade=0.12)
    kt = tl.t
    ch = {"senpai": [1150, 880, 1, 0, 0, 0]}
    stage.add(kt, 0.01, ch, 1.0, 1.0, (960, 540), "later", {"senpai": "aged"})
    a71, b71 = say_no(tl, 71, phone=True)
    inset_prop(ev, stage, tachie, tl, a71 - 0.3, b71 + 0.3, "a", "aged", "desk", 340, 340, 640, 640, (90, 100, 400, 360))
    handset_prop(ev, stage, tachie, "senpai", ring + 0.9, b71 + 0.3, side=-1, sleeve=hexc("#6E4F3C"))
    # #72 行員A（R8 のぼかし背景）
    cha = {"a": [700, 780, 1, 0, 0, 0]}
    a72, b72 = conv(tl, stage, 72, "desk", None, None, {"a": "aged"}, chars=cha)
    inset_prop(ev, stage, tachie, tl, a72 - 0.3, b72 + 0.3, "senpai", "aged", "later", 1068, 270, 1450, 760,
               (1440, 100, 420, 360))
    handset_prop(ev, stage, tachie, "a", a72 - 0.3, b72 + 0.3, side=-1)
    ev.setdefault("shakes", []).append(("a", a72, b72, 7))
    a73, b73 = conv(tl, stage, 73, "later", None, None, {"senpai": "aged"}, chars=ch, phone=True)
    inset_prop(ev, stage, tachie, tl, a73 - 0.3, b73 + 0.3, "a", "aged", "desk", 340, 340, 640, 640, (90, 100, 400, 360))
    handset_prop(ev, stage, tachie, "senpai", a73 - 0.3, b73 + 0.3, side=-1, sleeve=hexc("#6E4F3C"))
    memo_prop(ev, a72, b73 + 3.0, strike_at=a73 + 0.5)
    a74, b74 = conv(tl, stage, 74, "desk", None, None, {"a": "aged"}, chars=cha)
    inset_prop(ev, stage, tachie, tl, a74 - 0.3, b74 + 0.3, "senpai", "aged", "later", 1068, 270, 1450, 760,
               (1440, 100, 420, 360))
    handset_prop(ev, stage, tachie, "a", a74 - 0.3, b74 + 0.3, side=-1)

    def surprise(ctx, t):
        k = clamp((t - a74) / 0.12) * clamp((b74 + 0.3 - t) / 0.2)
        if k > 0:
            burst(ctx, 700, GROUND_Y + 6 - 780 + 70, 120, al=k, n=9)
    props_add(ev, a74, b74 + 0.4, surprise)
    ev.setdefault("shakes", []).append(("a", a74, a74 + 0.3, 8))
    # #75 しょんぼり。受話器は消える
    kt = tl.t
    stage.add(kt, 0.3, cha, 1.0, 1.0, (960, 540), "desk", {"a": "aged"})
    a75, b75 = say_no(tl, 75)
    stage.add(a75 + 0.3, 1.0, {"a": [700, 780, 1, 0, 40, -0.05]}, 1.0, 1.0, (960, 540), "desk", {"a": "aged"})


def scene_k12(tl, stage, ev):
    """場面K12：直せる人は（R10 数年後の本部の大画面）。"""
    fb = {"boss": "trouble", "a": "aged", "b": "aged", "c": "aged"}
    kt = tl.t
    stage.add(kt, 0.01, {"boss": [620, 780, 1, 0, 0, 0]}, 0.0, 1.0, (960, 540), "big", {"boss": "trouble"})
    a76, b76 = say_no(tl, 76)
    screen_bubble_prop(ev, kt, b76 + 0.3)
    ev.setdefault("shakes", []).append(("boss", a76, b76, 4))
    a77, b77 = conv(tl, stage, 77, "big", "all4", "boss", fb)

    def photo(ctx, t):
        k = ease_back(clamp((t - a77 - 0.2) / 0.4))
        if k <= 0:
            return
        ctx.save()
        ctx.translate(1700, 190)
        ctx.rotate(0.07)
        ctx.scale(k, k)
        ctx.set_source_rgba(0, 0, 0, 0.18)
        rrect(ctx, -150, -100, 310, 210, 6)
        ctx.fill()
        rrect(ctx, -155, -105, 310, 210, 6)
        fill_stroke(ctx, (1, 1, 1, 1), (0.5, 0.5, 0.55, 1), 3)
        ctx.save()
        rrect(ctx, -138, -88, 276, 176, 3)
        ctx.clip()
        ctx.translate(-138, -88)
        ctx.scale(276 / 1920 * 1.5, 276 / 1920 * 1.5)
        ctx.translate(-300, -150)
        ctx.set_source_surface(get_bg("stage", 0), 0, 0)
        ctx.paint()
        ctx.restore()
        ctx.restore()
    props_add(ev, a77, b77 + 0.4, photo, layer="screen")
    # #78 H0 #1 と同じ寄り・同じ動き（先出しの回収）
    kt = tl.t
    stage.add(kt, 0.01, h0_boss_chars(), 0.0, H0_BOSS_SHOT["zoom"], H0_BOSS_SHOT["pivot"], "big", {"boss": "trouble"})
    a78, b78 = say_no(tl, 78)
    bubble_always = lambda ctx, t: bubble(ctx, 1540, 250, 370, 150, "ルール改正に\n対応できません", size=36, tail=(1370, 300))
    props_add(ev, kt, b78 + 0.4, bubble_always)
    ev.setdefault("shakes", []).append(("boss", a78, b78, 5))
    conv(tl, stage, 79, "big", "all4", "a", fb)
    conv(tl, stage, 80, "big", "all4", "boss", {**fb, "boss": "aged"})
    conv(tl, stage, 81, "big", "all4", "b", fb)
    # #82 H0 #2 と同じ寄り
    kt = tl.t
    stage.add(kt, 0.01, h0_three_chars(), 0.0, 1.15, (1100, 540), "big", {"a": "aged", "b": "aged", "c": "aged"})
    say_no(tl, 82)
    conv(tl, stage, 83, "big", "all4", "c", fb, kind="talk_c")


def scene_k13(tl, stage, ev):
    """場面K13：分かれてしまった（R10 の引き）。"""
    fb = {"boss": "aged", "a": "aged", "b": "aged", "c": "aged", "senpai": "aged"}
    base = layout("conv", "boss", preset="k13")
    for v in base.values():
        v[2] = v[2]
    base["senpai"][0] = 2300  # 右の外
    base["senpai"][2] = 1.0
    kt = tl.t
    stage.add(kt, 0.3, base, 1.0, 1.0, (960, 540), "big", fb)
    a84, b84 = say_no(tl, 84)
    # 言い終わりで画面の右から先輩が入ってくる（本部に呼ばれた先輩）
    enter = layout("conv", "boss", preset="k13")
    stage.add(b84 - 0.5, 1.0, enter, 1.0, 1.0, (960, 540), "big", fb)
    a85, b85 = conv(tl, stage, 85, "big", "k13", "senpai", fb)
    a86, b86 = conv(tl, stage, 86, "big", "k13", ["a", "b", "c"], fb)
    ev.setdefault("shakes", []).extend([("a", a86, b86, 5), ("b", a86, b86, 5), ("c", a86, b86, 5)])
    # #87 R10 の引き。偉い人が両者のあいだで青ざめる。BGM を止める
    kt = tl.t
    sce = layout("scene", preset="k13")
    stage.add(kt, 0.4, sce, 0.0, 1.05, (960, 540), "big", {**fb, "boss": "trouble"})
    a87, b87 = say_no(tl, 87)
    stage.add(a87, b87 - a87 + 0.8, sce, 0.0, 1.0, (960, 540), "big", {**fb, "boss": "trouble"})
    ev["bgm_stop"] = b87

    def pale(ctx, t):
        k = clamp((t - a87) / 0.3) * clamp((b87 + 1.0 - t) / 0.4)
        blue_lines(ctx, 870, 1086 - 740 + 20, 240, 190, al=k)
    props_add(ev, a87, b87 + 1.2, pale)


def scene_k14(tl, stage, ev):
    """場面K14：幕切れ（R11 夜の支店）。効果音なし。笑わせない。"""
    kt = tl.t
    stage.add(kt, 0.01, {}, 0.0, 1.6, (1700, 420), "night", {})
    a88, b88 = say_no(tl, 88)
    a89, b89 = say_no(tl, 89)
    stage.add(b88, b89 - b88 + 0.5, {}, 0.0, 1.0, (960, 540), "night", {})

    def glow_bubble(ctx, t):
        k = clamp((t - kt - 0.5) / 0.6)
        g = 0.6 + 0.4 * math.sin(t * 2.2)
        bubble(ctx, 1480, 300, 580, 90, "奥の棚の、青いファイルの3ページ目です", al=k, size=26, tail=(1735, 390), glow=g)
    props_add(ev, kt, b89 + 2.0, glow_bubble)
    ev["years_to"] = a89
    ev["k14_end"] = b89


# ---------------------------------------------------------------- 全体
def build(vv, upto="k14"):
    tl = Timeline(vv, CAST)
    stage, ev = Stage(), {}
    tachie = load_tachie()
    ev["tachie"] = tachie
    bgm_path = latest(BGM_SKIT)
    scene_h0(tl, stage, ev)
    scene_k0(tl, stage, ev)
    scene_k1(tl, stage, ev)
    ev["k1_end_t"] = tl.t
    if upto == "k1":
        total = ev["k1_end"] + 1.0
    else:
        scene_k2(tl, stage, ev)
        scene_k3(tl, stage, ev)
        scene_k4(tl, stage, ev, tachie)
        scene_k5(tl, stage, ev)
        scene_k6(tl, stage, ev)
        scene_k7(tl, stage, ev)
        scene_k8(tl, stage, ev)
        scene_k9(tl, stage, ev)
        scene_k10(tl, stage, ev)
        scene_k11(tl, stage, ev, tachie)
        scene_k12(tl, stage, ev)
        scene_k13(tl, stage, ev)
        scene_k14(tl, stage, ev)
        total = ev["k14_end"] + 1.5  # #89 の後はそのまま（sound.md の後の間 1.5 秒）
    # BGM：H0 #3 から小さく（0.10）、K0 のタイトルで 0.15 へ。K13 #87 の言い終わりで切り出し 0.3 秒で止める
    if os.path.exists(bgm_path):
        end = ev.get("bgm_stop", total)
        tl.bgm(bgm_path, at=ev["a3"], until=end, fade=1.5, fade_out=0.3,
               ramp=[(ev["a3"], 0.10), (ev["k0"], 0.10), (ev["k0"] + 0.6, 0.15), (end, 0.15)])
    else:
        print("注意: BGM のファイルがない（BGM なしで進める）:", bgm_path)
    tl.wait(total - tl.t)
    tl.stage, tl.ev, tl.total = stage, ev, total  # audio_check.py は build() の戻り値を Timeline として読む
    return tl


# ---------------------------------------------------------------- 描画
def make_draw(tl, stage, ev, tachie):
    ORDER = ["c", "b", "a", "boss", "senpai"]
    props = ev.get("props", [])

    def draw_bg(ctx, st):
        name = st["bg"]
        ctx.set_source_surface(get_bg(name, 0), 0, 0)
        ctx.paint()
        b = st["blur"]
        if b > 0:
            ctx.set_source_surface(get_bg(name, 14), 0, 0)
            ctx.paint_with_alpha(clamp(b))
        if b > 1:
            ctx.set_source_surface(get_bg(name, 40), 0, 0)
            ctx.paint_with_alpha(clamp(b - 1))

    def shake(n, t):
        dx = 0.0
        for who, t0, t1, amp in ev.get("shakes", []):
            if who == n and t0 <= t <= t1:
                dx += amp * math.sin(t * 2 * math.pi * 4.2)
        return dx

    def hop(n, t):
        out = 0.0
        for who, t0 in ev.get("hops", []):
            p = (t - t0) / 0.4
            if who == n and 0 <= p <= 1:
                out += 46 * math.sin(math.pi * p)
        return out

    def draw(ctx, t):
        st = stage.at(t)
        ctx.set_source_rgb(1, 1, 1)
        ctx.paint()
        # --- 背景＋立ち絵（カメラの寄りをかける）
        ctx.save()
        px, py = st["pivot"]
        ctx.translate(px, py)
        ctx.scale(st["zoom"], st["zoom"])
        ctx.translate(-px, -py)
        draw_bg(ctx, st)
        who_now = []
        for ln in tl.lines:
            if ln.t0 - 0.35 <= t:
                who_now = list(ln.who)
        order = [n for n in ORDER if n not in who_now] + [n for n in ORDER if n in who_now]
        for n in order:
            if n not in st["chars"]:
                continue
            x, h, al, dim, dy, rot = st["chars"][n]
            face = st["faces"].get(n, "base")
            speaking = tl.speaking(n, t)
            has_mouth = tachie[n].faces[face]["open"] is not None
            bob = 0.0
            if speaking:
                bob = (5 if has_mouth else 9) * math.sin(t * 2 * math.pi * 2.6) ** 2
            bob += hop(n, t)
            x += shake(n, t)
            ctx.save()
            if rot:
                ctx.translate(x, GROUND_Y + 6 + dy)
                ctx.rotate(rot)
                ctx.translate(-x, -(GROUND_Y + 6 + dy))
            tachie[n].draw(ctx, x, GROUND_Y + 6 + dy, h, mouth=tl.mouth(n, t) if has_mouth else 0.0, alpha=al,
                           dim=dim, dim_rgb=(0.96, 0.95, 0.93), bob=bob, face=face, t=None)
            ctx.restore()
        for t0, t1, fn, layer in props:
            if layer == "world" and t0 <= t <= t1:
                fn(ctx, t)
        ctx.restore()
        for t0, t1, fn, layer in props:
            if layer == "screen" and t0 <= t <= t1:
                fn(ctx, t)
        # --- 時の経過（K10 #68）
        for ts, s in ev.get("jump", []):
            if ts <= t < ts + 0.6:
                k = ease_back((t - ts) / 0.25)
                ctx.save()
                ctx.translate(W / 2, H / 2 - 60)
                ctx.scale(0.7 + 0.3 * k, 0.7 + 0.3 * k)
                text(ctx, s, 0, 0, 150, (0.2, 0.2, 0.26, 1), outline=(1, 1, 1, 1), ow=26)
                ctx.restore()
        # --- 記念写真の白い枠（K10）
        ph = ev.get("photo")
        if ph and ph[1] and ph[0] <= t <= ph[1]:
            k = clamp((ph[1] - t) / 0.35)
            ctx.save()
            ctx.set_source_rgba(1, 1, 1, k)
            ctx.set_line_width(70)
            ctx.rectangle(35, 35, W - 70, H - 70)
            ctx.stroke()
            ctx.set_line_width(4)
            ctx.set_source_rgba(0.6, 0.6, 0.64, 0.8 * k)
            ctx.rectangle(70, 70, W - 140, H - 140)
            ctx.stroke()
            ctx.restore()
        fl = ev.get("flash")
        if fl is not None and fl <= t < fl + 0.15:
            ctx.set_source_rgba(1, 1, 1, 1 - (t - fl) / 0.15 * 0.3)
            ctx.paint()
        # --- K0 のタイトル
        k0, k1 = ev["k0"], ev["k1"]
        if k0 <= t < k1 + 0.6:
            ta = ev["title_at"]
            k = ease_back((t - ta) / 0.45)
            out = 1 - clamp((t - (k1 - 0.3)) / 0.4)
            if t >= ta and out > 0:
                ctx.save()
                ctx.translate(W / 2, H / 2 - 40)
                ctx.scale(0.6 + 0.4 * k, 0.6 + 0.4 * k)
                s = "スコップを渡された人たち"
                text(ctx, s, 6, 8, 112, (0.55, 0.45, 0.3, 0.35 * out), outline=None)
                text(ctx, s, 0, 0, 112, (0.17, 0.17, 0.2, clamp(k) * out),
                     outline=(1, 1, 1, clamp(k) * out), ow=22)
                text(ctx, s, 0, 0, 112, (0.17, 0.17, 0.2, clamp(k) * out))
                ctx.restore()
            note_fiction(ctx, small=False, alpha=out)
        # --- 「※この物語はフィクションです」：H0 は下の中央に小さく → #3 から右下のごく小さい表示（K14 まで出し続ける）
        if t < k0:
            u = clamp((t - ev["a3"]) / 0.6)
            if u < 1:
                note_fiction(ctx, small=True, alpha=1 - u, center=True)
            if u > 0:
                note_fiction(ctx, small=True, alpha=u)
        elif t >= k1 - 0.3:
            note_fiction(ctx, small=True, alpha=clamp((t - (k1 - 0.3)) / 0.4))
        # --- 左上「数年後（作者の想像）」：H0 の #1〜#2 と、K10 の終わり〜K14 #89 の頭まで
        yl = 0.0
        h0l = ev.get("h0_label")
        if h0l and t < k0:
            yl = clamp((h0l[1] - t) / 0.25) if h0l[1] else 1.0
        if "years_from" in ev and t >= ev["years_from"]:
            yl = clamp((t - ev["years_from"]) / 0.4)
            if "years_to" in ev and t >= ev["years_to"]:
                yl *= clamp(1 - (t - ev["years_to"]) / 0.4)
        years_later(ctx, yl)
        caption(ctx, tl, t, NAMES, COLORS, by=CAP_BY)
        # --- 暗転（H0 の終わり）と K0 の頭の明るくなる所
        bl = ev.get("black")
        if bl:
            if bl[0] <= t < k0:
                ctx.set_source_rgba(0, 0, 0, clamp((t - bl[0]) / (k0 - bl[0] - 0.05)))
                ctx.paint()
            elif k0 <= t < k0 + 0.3:
                ctx.set_source_rgba(0, 0, 0, 1 - (t - k0) / 0.3)
                ctx.paint()

    return draw


def contact_sheet(files, out, cols=4, tw=480):
    ims = [Image.open(f).convert("RGB") for f in files]
    th = int(tw * 9 / 16)
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * th), "white")
    for i, im in enumerate(ims):
        sheet.paste(im.resize((tw, th), Image.LANCZOS), ((i % cols) * tw, (i // cols) * th))
    sheet.save(out)


def main():
    os.makedirs(OUT, exist_ok=True)
    vv = Voicevox(cache_dir=os.path.join(OUT, "cache"))
    upto = "k1" if "--sample" in sys.argv else "k14"
    tl = build(vv, upto)
    stage, ev, total = tl.stage, tl.ev, tl.total
    tachie = ev["tachie"]
    draw = make_draw(tl, stage, ev, tachie)
    nos = [1, 2, 3, 4] + list(range(5, 90 if upto == "k14" else 14))
    L = dict(zip(nos, tl.lines))
    if "--stills" in sys.argv:
        frames, labels = [], []
        for no, ln in L.items():
            frames.append(round(min(ln.t0 + (ln.t1 - ln.t0) * 0.55, ln.t1 - 0.05), 2))
            labels.append(no)
        extra = [("k0", ev["k0"] + 2.0), ("k1_sign", ev["k1"] + 0.8)]
        if upto == "k14":
            extra += [("k4_ring", ev["h0_end"] + 99)] if False else []
            extra += [("k10_y1", ev["jump"][0][0] + 0.3), ("k10_y3", ev["jump"][2][0] + 0.3),
                      ("k10_flash", ev["flash"] + 0.05), ("k14_end", total - 0.1)]
        for lb, tt in extra:
            frames.append(round(tt, 2))
            labels.append(lb)
        order = sorted(range(len(frames)), key=lambda i: frames[i])
        frames = [frames[i] for i in order]
        labels = [labels[i] for i in order]
        for f in glob.glob(os.path.join(OUT, "still_skit_*.png")):
            os.remove(f)
        render(draw, total, None, os.path.join(OUT, "still_skit"), frames=frames)
        files = sorted(glob.glob(os.path.join(OUT, "still_skit_*.png")))
        per = 20
        first = core.next_version(os.path.join(OUT, "shovel_skit_sheet_p1.png"))
        ver = os.path.splitext(first)[0].rsplit("_v", 1)[1]
        outs = []
        for i in range(0, len(files), per):
            p = os.path.join(OUT, f"shovel_skit_sheet_p{i // per + 1}_v{ver}.png")
            contact_sheet(files[i:i + per], p)
            outs.append(p)
        print("静止画", len(files), "枚 →", *outs, f"/ 全体 {total:.1f}秒")
        for no, ln in L.items():
            print(f"#{no} {ln.t0:.2f}-{ln.t1:.2f}")
        print("labels:", list(zip(frames, labels)))
        return
    audio = tl.audio(total)
    name = "shovel_sample.mp4" if upto == "k1" else "shovel_skit.mp4"
    path = render(draw, total, audio, os.path.join(OUT, name))
    print("書き出し →", path, f"{total:.1f}秒")
    for no, ln in L.items():
        print(f"#{no} {ln.t0:.2f}-{ln.t1:.2f}")


if __name__ == "__main__":
    main()
