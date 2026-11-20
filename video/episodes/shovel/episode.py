"""note「スコップを渡された人たち」寸劇アニメ（漫画動画方式。台本 script.md に従う）

今回は見本段階：場面K0（タイトル）と場面K1（辞令、台詞 #5〜#13）だけを実装している。
ほかの場面は、場面ごとの関数（scene_xx）を足して build() から呼ぶ。
前の試作は versions/episode_prototype_v1.py。

使い方（リポジトリ直下で）:
    python3 video/episodes/shovel/episode.py --stills   # 確認用の静止画と一覧画像
    python3 video/episodes/shovel/episode.py --sample   # 見本（K0〜K1）の MP4
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "..", "lib")
sys.path.insert(0, LIB)
import core  # noqa: E402
from core import (H, W, INK, Tachie, Timeline, Voicevox, caption, clamp, ease_back,  # noqa: E402
                  ease_io, ease_out, fill_stroke, hexc, latest, lerp, render, rrect, text)
from voice_preview import load_lines, load_tuning, load_voices  # noqa: E402
import cairo  # noqa: E402
from PIL import Image, ImageFilter  # noqa: E402

ROOT = os.path.join(HERE, "..", "..")
OUT = os.path.join(ROOT, "out")
IMG = os.path.join(ROOT, "assets", "images", "shovel")
BGM_SKIT = os.path.join(ROOT, "assets", "bgm", "bgm_skit_light.mp3")

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


# ---------------------------------------------------------------- 画像
def _img(name):
    return os.path.join(IMG, name + ".png")


def load_tachie():
    return {
        "boss": Tachie(_img("shovel_boss_base"), _img("shovel_boss_mouth_open"), half=_img("shovel_boss_mouth_half")),
        "a": Tachie(_img("shovel_a_base"), _img("shovel_a_mouth_open"), half=_img("shovel_a_mouth_half")),
        "b": Tachie(_img("shovel_b_base"), _img("shovel_b_mouth_open"), half=_img("shovel_b_mouth_half")),
        "c": Tachie(_img("shovel_c_base"), _img("shovel_c_mouth_open"), half=_img("shovel_c_mouth_half")),
    }


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


# ---------------------------------------------------------------- 描画部品
def note_fiction(ctx, small=True, alpha=1.0):
    """「※この物語はフィクションです」。K0 は下に中央、K1 以降は右下にごく小さく。"""
    s = "※この物語はフィクションです"
    if small:
        text(ctx, s, W - 24, H - 18, 21, (0.25, 0.25, 0.28, 0.9 * alpha), align="right", bold=False,
             outline=(1, 1, 1, 0.8 * alpha), ow=5)
    else:
        text(ctx, s, W / 2, H - 56, 32, (0.2, 0.2, 0.24, alpha), bold=False, outline=(1, 1, 1, 0.85 * alpha), ow=7)


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


def hand_arm(ctx, x0, y0, x1, y1, sleeve):
    """肩側 (x0,y0) から手 (x1,y1) までの腕と手（スーツの袖と肌）。"""
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_width(64)
    ctx.set_source_rgba(*INK)
    ctx.move_to(x0, y0)
    ctx.line_to(x1, y1)
    ctx.stroke()
    ctx.set_line_width(50)
    ctx.set_source_rgba(*sleeve)
    ctx.move_to(x0, y0)
    ctx.line_to(x1, y1)
    ctx.stroke()
    ctx.arc(x1, y1, 30, 0, 2 * math.pi)
    fill_stroke(ctx, core.SKIN, INK, 5)


# ---------------------------------------------------------------- 画面の状態（キーフレーム）
# 各キーフレーム：(開始時刻, 所要秒, 状態)。状態の人物は (x, 高さ, 不透明度, 薄め)。
# blur は 0=ぼかしなし、1=ふつうのぼかし（会話ショットの背景）、2=強いぼかし（K0）。zoom はカメラの寄り。
GROUND_Y = H  # 立ち絵（胸から上）の下端は画面の下端にそろえる
X_BOSS, X_A, X_B, X_C = 360, 900, 1280, 1660
H_BOSS, H_STAFF = 770, 630


def layout(kind, who=None):
    """配置の型。scene=場面ショット、conv=会話ショット（who が話者）、talk_c=C を右に大きく、
    boss_push=偉い人を少し前へ。"""
    st = {"boss": [X_BOSS, H_BOSS, 1.0, 0.0], "a": [X_A, H_STAFF, 1.0, 0.0],
          "b": [X_B, H_STAFF, 1.0, 0.0], "c": [X_C, H_STAFF, 1.0, 0.0]}
    if kind == "scene":
        return st
    for k, v in st.items():
        v[2], v[3] = 1.0, 0.42  # 話していない人は透かさず、白っぽく淡くする（透かすと背景が顔に透けて幽霊のように見え、暗くすると肌の色が変わって見える）
    if kind == "talk_c":
        st["boss"][0], st["a"][0], st["b"][0] = 300, 760, 1060
        st["c"] = [1440, 920, 1.0, 0.0]
        return st
    if kind == "boss_push":
        st["boss"] = [470, 880, 1.0, 0.0]
        return st
    st[who][2], st[who][3] = 1.0, 0.0
    st[who][1] = st[who][1] * 1.1
    return st


class Stage:
    def __init__(self):
        self.kf = []

    def add(self, t, dur, chars, blur, zoom, pivot=(X_BOSS, 700)):
        self.kf.append(dict(t=t, dur=dur, chars=chars, blur=blur, zoom=zoom, pivot=pivot))

    def at(self, t):
        cur = [k for k in self.kf if k["t"] <= t]
        i = len(cur) - 1
        k = cur[-1]
        p = self.kf[i - 1] if i > 0 else k
        u = ease_io((t - k["t"]) / k["dur"]) if k["dur"] > 0 else 1.0
        chars = {n: [lerp(p["chars"][n][j], k["chars"][n][j], u) for j in range(4)] for n in k["chars"]}
        return dict(chars=chars, blur=lerp(p["blur"], k["blur"], u), zoom=lerp(p["zoom"], k["zoom"], u),
                    pivot=k["pivot"])


# ---------------------------------------------------------------- 台本（場面ごと）
def scene_k0(tl, stage, ev):
    """場面K0：タイトル（R1 を強くぼかした上にタイトルだけ。台詞なし、5秒）。"""
    t0 = tl.t
    tl.scene("k0")
    stage.add(t0, 0.01, layout("scene"), 2.0, 1.0)
    ev["k0"] = (t0, t0 + 5.0)
    ev["title_at"] = t0 + 0.4
    tl.sfx("pop", at=ev["title_at"], vol=0.5)
    tl.wait(5.0)


def scene_k1(tl, stage, ev):
    """場面K1：辞令（#5〜#13）。"""
    t0 = tl.t
    tl.scene("k1")
    # #5 場面ショット：看板の文字を1.5秒、そのあと台詞（偉い人へゆっくり寄る）
    stage.add(t0, 0.7, layout("scene"), 0.0, 1.0)
    ev["k1"] = t0
    ev["sign"] = (t0 + 0.1, t0 + 1.6)
    tl.wait(1.5)
    a, b = say_no(tl, 5)
    ev["l5"] = (a, b)
    stage.add(a, b - a, layout("scene"), 0.0, 1.1)
    ev["paper"] = (a - 0.2, a + 1.0)
    for no, who in ((6, "a"), (7, "b")):
        kt = tl.t
        stage.add(kt, 0.3, layout("conv", who), 1.0, 1.0)
        say_no(tl, no)
    # #8 偉い人：立ち絵を1回小さく跳ねさせる
    kt = tl.t
    stage.add(kt, 0.3, layout("conv", "boss"), 1.0, 1.0)
    a, b = say_no(tl, 8)
    ev["hop"] = a
    # #9 行員Cを右に大きく（台詞の前に0.3秒の間）
    kt = tl.t
    stage.add(kt, 0.3, layout("talk_c"), 1.0, 1.0)
    say_no(tl, 9)
    # #10〜#12 K1 の並びに戻す
    for no, who in ((10, "boss"), (11, "a"), (12, "boss")):
        kt = tl.t
        stage.add(kt, 0.3, layout("conv", who), 1.0, 1.0)
        say_no(tl, no)
    # #13 偉い人が少し前へ寄って3人を指さす。言い終わりで pop
    kt = tl.t
    stage.add(kt, 0.3, layout("conv", "boss"), 1.0, 1.0)
    a, b = say_no(tl, 13)
    stage.add(a, 0.5, layout("boss_push"), 1.0, 1.0)
    tl.sfx("pop", at=b, vol=0.5)
    ev["end"] = b


def build(vv, upto="k1"):
    tl = Timeline(vv, CAST)
    stage, ev = Stage(), {}
    # BGM：寸劇の軽い曲。見本は K0 から始まるので、K0 の頭から 1.5 秒のフェードインで 0.15
    bgm_path = latest(BGM_SKIT)
    scene_k0(tl, stage, ev)
    scene_k1(tl, stage, ev)
    total = ev["end"] + 1.0
    if os.path.exists(bgm_path):
        tl.bgm(bgm_path, at=0.0, until=total, vol=0.15, fade=1.5)
    else:
        print("注意: BGM のファイルがない（BGM なしで進める）:", bgm_path)
    tl.wait(total - tl.t)
    tl.stage, tl.ev, tl.total = stage, ev, total  # audio_check.py は build() の戻り値を Timeline として読む
    return tl


# ---------------------------------------------------------------- 描画
def make_draw(tl, stage, ev, tachie):
    bg = {b: cover_bg(os.path.join(IMG, "shovel_bg_branch_office.png"), b) for b in (0, 14, 40)}

    def draw_bg(ctx, st):
        ctx.set_source_surface(bg[0], 0, 0)
        ctx.paint()
        b = st["blur"]
        if b > 0:
            ctx.set_source_surface(bg[14], 0, 0)
            ctx.paint_with_alpha(clamp(b))
        if b > 1:
            ctx.set_source_surface(bg[40], 0, 0)
            ctx.paint_with_alpha(clamp(b - 1))

    def sign(ctx, t):
        a, b = ev["sign"]
        al = clamp((t - a) / 0.2) * clamp((b - t) / 0.2)
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

    def draw(ctx, t):
        st = stage.at(t)
        k0 = t < ev["k1"] - 0.3
        ctx.set_source_rgb(1, 1, 1)
        ctx.paint()
        # --- 背景＋立ち絵（カメラの寄りをかける）
        ctx.save()
        px, py = st["pivot"]
        ctx.translate(px, py)
        ctx.scale(st["zoom"], st["zoom"])
        ctx.translate(-px, -py)
        draw_bg(ctx, st)
        if t >= ev["k1"] - 0.25:  # K0 のあいだは人物を出さない（K1 の頭で出す）
            who_now = None
            for ln in tl.lines:
                if ln.t0 - 0.35 <= t:
                    who_now = ln.who[0]
            fadein = clamp((t - (ev["k1"] - 0.25)) / 0.5)
            order = [n for n in ("c", "b", "a", "boss") if n != who_now] + ([who_now] if who_now in tachie else [])
            for n in order:
                x, h, al, dim = st["chars"][n]
                bob = 0.0
                hop = 0.0
                if tl.speaking(n, t):
                    bob = 5 * math.sin((t - ev["k1"]) * 2 * math.pi * 2.6) ** 2
                if n == "boss" and "hop" in ev:
                    p = (t - ev["hop"]) / 0.4
                    if 0 <= p <= 1:
                        hop = 46 * math.sin(math.pi * p)
                tachie[n].draw(ctx, x, GROUND_Y + 6, h, mouth=tl.mouth(n, t), alpha=al * fadein, dim=dim, dim_rgb=(0.96, 0.95, 0.93),
                               bob=bob + hop, t=None)
        # 辞令（無地の紙）：偉い人の手前に、手渡すように
        if "paper" in ev:
            a0, a1 = ev["paper"]
            if a0 <= t <= ev["l5"][1] + 0.2:
                u = ease_out((t - a0) / 1.2)
                al = clamp((t - a0) / 0.15) * clamp((ev["l5"][1] + 0.2 - t) / 0.2)
                bx, by = lerp(520, 620, u), lerp(800, 750, u)
                ctx.push_group()
                hand_arm(ctx, bx - 150, 1130, bx - 36, by + 100, hexc("#262F4A"))
                paper(ctx, bx, by, 0.12, 1.0)
                hand_arm(ctx, bx - 150, 1130, bx - 36, by + 100, hexc("#262F4A"))
                ctx.pop_group_to_source()
                ctx.paint_with_alpha(al)
        sign(ctx, t)
        ctx.restore()
        # --- K0 のタイトル
        if t < ev["k1"] + 0.6:
            ta = ev["title_at"]
            k = ease_back((t - ta) / 0.45)
            out = 1 - clamp((t - (ev["k1"] - 0.3)) / 0.4)
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
        if t >= ev["k1"] - 0.3:
            note_fiction(ctx, small=True, alpha=clamp((t - (ev["k1"] - 0.3)) / 0.4))
        caption(ctx, tl, t, NAMES, COLORS)

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
    tl = build(vv)
    stage, ev, total = tl.stage, tl.ev, tl.total
    tachie = load_tachie()
    draw = make_draw(tl, stage, ev, tachie)
    L = {i + 5: ln for i, ln in enumerate(tl.lines)}  # 見本は #5 から順に並ぶ
    if "--stills" in sys.argv:
        frames = [1.2, 4.7, ev["k1"] + 0.8]
        for no in (5, 6, 7, 8, 9, 10, 11, 12, 13):
            ln = L[no]
            frames.append(round(min(ln.t0 + (ln.t1 - ln.t0) * 0.55, ln.t1 - 0.05), 2))
        frames.append(round(ev["end"] - 0.05, 2))
        import glob
        for f in glob.glob(os.path.join(OUT, "still_k01_*.png")):
            os.remove(f)
        render(draw, total, None, os.path.join(OUT, "still_k01"), frames=frames)
        files = sorted(glob.glob(os.path.join(OUT, "still_k01_*.png")))
        sheet = core.next_version(os.path.join(OUT, "shovel_sample_sheet.png"))
        contact_sheet(files, sheet)
        print("静止画", len(files), "枚 →", sheet, f"/ 全体 {total:.1f}秒")
        for no, ln in L.items():
            print(f"#{no} {ln.t0:.2f}-{ln.t1:.2f}")
        return
    audio = tl.audio(total)
    path = render(draw, total, audio, os.path.join(OUT, "shovel_sample.mp4"))
    print("書き出し →", path, f"{total:.1f}秒")


if __name__ == "__main__":
    main()
