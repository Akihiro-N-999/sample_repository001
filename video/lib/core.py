"""寸劇アニメーション用の共通処理: VOICEVOX合成、効果音、タイムライン、描画部品、書き出し。"""
import hashlib
import io
import json
import math
import os
import subprocess
import urllib.parse
import urllib.request
import wave

import cairo
import numpy as np

W, H, FPS, SR = 1920, 1080, 30, 48000
FONT = "Noto Sans CJK JP"
GROUND = 800


# ---------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def lerp(a, b, u):
    return a + (b - a) * u


def ease_io(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_back(x):
    x = clamp(x)
    c = 1.70158
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def hexc(h, a=1.0):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (a,)


# ---------------------------------------------------------------- VOICEVOX
class Voicevox:
    def __init__(self, host=None, cache_dir=None):
        self.host = host or os.environ.get("VOICEVOX_HOST", "http://127.0.0.1:50021")
        self.cache_dir = cache_dir
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)

    def _post(self, path, params, body=None):
        url = f"{self.host}{path}?{urllib.parse.urlencode(params)}"
        data = json.dumps(body).encode() if body is not None else b""
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()

    def synth(self, text, speaker, speed=1.0, pitch=0.0, intonation=1.15, volume=1.0, pause=1.0):
        """1回の呼び出しで1つの発話を合成する。改行は読み上げの区切りにしない。"""
        text = text.replace("<br>", "").replace("\n", "")
        key = hashlib.sha1(json.dumps([text, speaker, speed, pitch, intonation, volume, pause]).encode()).hexdigest()
        path = os.path.join(self.cache_dir, key + ".npy") if self.cache_dir else None
        if path and os.path.exists(path):
            return np.load(path)
        q = json.loads(self._post("/audio_query", {"text": text, "speaker": speaker}))
        q.update(speedScale=speed, pitchScale=pitch, intonationScale=intonation,
                 volumeScale=volume, pauseLengthScale=pause, outputSamplingRate=SR, outputStereo=False,
                 prePhonemeLength=0.05, postPhonemeLength=0.08)
        wav = self._post("/synthesis", {"speaker": speaker}, q)
        with wave.open(io.BytesIO(wav)) as w:
            a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        if path:
            np.save(path, a)
        return a


def load_audio(path):
    """mp3/wav などを ffmpeg で SR のモノラル float32 に読み込む。"""
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-f", "f32le", "-ac", "1",
                          "-ar", str(SR), "-"], check=True, capture_output=True).stdout
    return np.frombuffer(raw, np.float32).copy()


# ---------------------------------------------------------------- 効果音（その場で合成）
def make_sfx(kind):
    rng = np.random.default_rng(len(kind))

    def env(n, attack, decay):
        t = np.arange(n) / SR
        return np.minimum(t / attack, 1) * np.exp(-t / decay)

    def lowpass(x, k):
        return np.convolve(x, np.ones(k) / k, mode="same")

    if kind == "dig":
        n = int(0.22 * SR)
        x = lowpass(rng.standard_normal(n), 12) * env(n, 0.004, 0.05)
        return 0.9 * x / np.abs(x).max()
    if kind == "whoosh":
        n = int(0.5 * SR)
        t = np.arange(n) / SR
        x = rng.standard_normal(n)
        x = lowpass(x, 6) - lowpass(x, 40)
        x *= np.sin(np.pi * t / t[-1]) ** 2
        return 0.6 * x / np.abs(x).max()
    if kind == "thud":
        n = int(0.6 * SR)
        t = np.arange(n) / SR
        x = np.sin(2 * np.pi * (70 - 30 * t) * t) * env(n, 0.003, 0.15)
        x += 0.4 * lowpass(rng.standard_normal(n), 30) * env(n, 0.002, 0.06)
        return 0.95 * x / np.abs(x).max()
    if kind == "pop":
        n = int(0.15 * SR)
        t = np.arange(n) / SR
        f = 500 + 2500 * t / t[-1]
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.002, 0.04)
        return 0.45 * x
    if kind == "chime":
        n = int(1.4 * SR)
        x = np.zeros(n)
        for i, f in enumerate([1318.5, 1568.0, 2093.0, 2637.0]):
            s = int(i * 0.07 * SR)
            m = n - s
            t = np.arange(m) / SR
            x[s:] += np.sin(2 * np.pi * f * t) * env(m, 0.003, 0.35) * 0.25
        return x
    if kind == "shock":  # ガーン的な低い和音
        n = int(1.2 * SR)
        t = np.arange(n) / SR
        x = sum(np.sign(np.sin(2 * np.pi * f * t)) * 0.12 for f in (98, 116.5, 138.6))
        return lowpass(x, 20) * env(n, 0.005, 0.5)
    raise ValueError(kind)


# ---------------------------------------------------------------- タイムライン
class Line:
    def __init__(self, who, text, t0, t1, env):
        self.who, self.text, self.t0, self.t1, self.env = who, text, t0, t1, env


class Timeline:
    """台本を時間軸に並べる。say()で台詞を合成し、mark()で演出の開始時刻を打つ。"""

    def __init__(self, vv, cast):
        self.vv, self.cast = vv, cast
        self.t = 0.0
        self.lines, self.marks, self.scenes, self.clips = [], {}, [], []
        self.voice_clips, self.bgms = [], []
        self.voice_idx = set()  # clips のうち台詞の音声の番号（品質チェックで声とそれ以外を分けるため）

    def say(self, who, text, voice=None, ids=None, speed=None, pitch=None, intonation=None,
            pause=1.0, pre=0.0, gap=0.3, vol=1.0):
        """台詞1つ＝合成1回。字幕(text)の改行は表示だけに効き、読み上げは途切れない。
        pre/gap は台詞の前後の間（秒）。speed/pitch/intonation/pause は音声担当の調整値。"""
        whos = who if isinstance(who, list) else [who]
        speak = voice or text
        self.t += pre
        auds = []
        for i, w in enumerate(whos):
            c = self.cast[w]
            sid = ids[i] if ids else c["id"]
            auds.append(self.vv.synth(speak, sid, speed=speed or c.get("speed", 1.1),
                                      pitch=c.get("pitch", 0.0) if pitch is None else pitch,
                                      intonation=intonation or c.get("intonation", 1.15),
                                      pause=pause))
        n = max(len(a) for a in auds)
        mix = np.zeros(n, np.float32)
        for a in auds:
            mix[:len(a)] += a
        if len(auds) > 1:
            mix *= 0.75
        t0 = self.t
        dur = n / SR
        hop = SR // FPS
        rms = np.array([np.sqrt(np.mean(mix[i:i + hop] ** 2) + 1e-9) for i in range(0, n, hop)])
        ref = np.percentile(rms, 90) + 1e-6
        env = np.clip(rms / ref, 0, 1)
        self.voice_idx.add(len(self.clips))
        self.clips.append((t0, mix * vol))
        self.voice_clips.append((t0, t0 + dur))
        line = Line(whos, text, t0, t0 + dur, env)
        self.lines.append(line)
        self.t = t0 + dur + gap
        return t0, t0 + dur

    def wait(self, d):
        self.t += d

    def mark(self, name, at=None, dur=0.5):
        self.marks[name] = (self.t if at is None else at, dur)

    def sfx(self, kind, at=None, vol=1.0):
        """kind は合成効果音の名前（dig / whoosh / thud / pop / chime / shock）か、音声ファイルのパス。"""
        a = load_audio(kind) if os.path.splitext(kind)[1] else make_sfx(kind)
        self.clips.append((self.t if at is None else at, a * vol))

    def scene(self, name, at=None):
        self.scenes.append((self.t if at is None else at, name))

    def bgm(self, path, at=None, until=None, vol=0.18, fade=1.5, duck=0.4):
        """BGMを at〜until 秒に流す（曲が短ければループ）。台詞の間は duck 倍に下げる。
        until を省くと動画の終わりまで。"""
        self.bgms.append(dict(path=path, t0=self.t if at is None else at, t1=until,
                              vol=vol, fade=fade, duck=duck))

    # ---- 再生時の問い合わせ
    def prog(self, name, t, ease=ease_io):
        if name not in self.marks:
            return 0.0
        t0, d = self.marks[name]
        return ease((t - t0) / d) if d > 0 else float(t >= t0)

    def since(self, name, t):
        return t - self.marks[name][0] if name in self.marks else -1e9

    def scene_at(self, t):
        cur = self.scenes[0][1]
        for ts, n in self.scenes:
            if t >= ts:
                cur = n
        return cur

    def fade(self, t, d=0.35):
        a = 0.0
        for ts, _ in self.scenes[1:]:
            a = max(a, 1 - abs(t - ts) / d)
        return clamp(a)

    def mouth(self, who, t):
        for ln in self.lines:
            if who in ln.who and ln.t0 <= t < ln.t1:
                k = int((t - ln.t0) * FPS)
                v = ln.env[min(k, len(ln.env) - 1)]
                return 0.0 if v < 0.25 else (0.55 if v < 0.6 else 1.0)
        return 0.0

    def speaking(self, who, t):
        return any(who in ln.who and ln.t0 <= t < ln.t1 for ln in self.lines)

    def caption(self, t, hold=0.35):
        cur = None
        for ln in self.lines:
            if ln.t0 <= t < ln.t1 + hold:
                cur = ln
        return cur

    def audio(self, total, parts=("voice", "sfx", "bgm"), normalize=True):
        """音声を合成する。parts で声・効果音・BGMの一部だけを取り出せる（品質チェック用）。"""
        out = np.zeros(int(total * SR) + SR, np.float32)
        for i, (t0, a) in enumerate(self.clips):
            if ("voice" if i in self.voice_idx else "sfx") not in parts:
                continue
            s = int(t0 * SR)
            out[s:s + len(a)] += a[:len(out) - s]
        if self.bgms and "bgm" in parts:
            # 台詞が鳴っている区間（前後0.15秒の余裕つき）を求め、なめらかにBGMを下げる
            speech = np.zeros(len(out), np.float32)
            for a, b in self.voice_clips:
                speech[max(0, int((a - 0.15) * SR)):int((b + 0.15) * SR)] = 1
            k = int(0.25 * SR)
            speech = np.convolve(speech, np.ones(k) / k, mode="same")
            for m in self.bgms:
                src = load_audio(m["path"])
                s = int(m["t0"] * SR)
                e = int((m["t1"] if m["t1"] is not None else total) * SR)
                n = max(0, min(e, len(out)) - s)
                if n == 0:
                    continue
                track = np.resize(src, n)
                f = max(1, int(m["fade"] * SR))
                g = np.ones(n, np.float32)
                g[:min(f, n)] = np.linspace(0, 1, min(f, n))
                g[-min(f, n):] = np.minimum(g[-min(f, n):], np.linspace(1, 0, min(f, n)))
                g *= 1 - (1 - m["duck"]) * speech[s:s + n]
                out[s:s + n] += track * g * m["vol"]
        peak = np.abs(out).max()
        if normalize and peak > 0.95:
            out *= 0.95 / peak
        return out


# ---------------------------------------------------------------- 描画部品
def rrect(ctx, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    ctx.close_path()


def fill_stroke(ctx, fill, stroke=(0.13, 0.13, 0.16, 1), lw=5):
    ctx.set_source_rgba(*fill)
    ctx.fill_preserve()
    ctx.set_line_width(lw)
    ctx.set_source_rgba(*stroke)
    ctx.stroke()


def font(ctx, size, bold=True):
    ctx.select_font_face(FONT, cairo.FONT_SLANT_NORMAL,
                         cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)


def text(ctx, s, x, y, size, color=(0.1, 0.1, 0.12, 1), align="center", bold=True,
         outline=None, ow=8):
    """y はベースラインではなく文字の縦中央。"""
    font(ctx, size, bold)
    e = ctx.text_extents(s)
    fx = ctx.font_extents()
    if align == "center":
        x0 = x - (e.x_advance) / 2
    elif align == "right":
        x0 = x - e.x_advance
    else:
        x0 = x
    y0 = y + (fx[0] - fx[1]) / 2
    ctx.move_to(x0, y0)
    ctx.text_path(s)
    if outline:
        ctx.set_source_rgba(*outline)
        ctx.set_line_width(ow)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)
        ctx.stroke_preserve()
    ctx.set_source_rgba(*color)
    ctx.fill()
    return e.x_advance


def vtext(ctx, s, x, y, size, color):
    """縦書き。長音記号は縦棒で描く。"""
    for i, ch in enumerate(s):
        cy = y + i * size * 1.05
        if ch in "ーｰ—":
            ctx.set_source_rgba(*color)
            ctx.set_line_width(size * 0.11)
            ctx.move_to(x, cy - size * 0.38)
            ctx.line_to(x, cy + size * 0.38)
            ctx.stroke()
        else:
            text(ctx, ch, x, cy, size, color)


NO_HEAD = set("、。，．・：；？！ー―…‥っゃゅょぁぃぅぇぉッャュョァィゥェォ）」』】〕〉》”’")
NO_TAIL = set("（「『【〔〈《“‘")
BREAK_AFTER = set("、。！？」』…")


def wrap(ctx, s, size, maxw):
    """字幕の折り返し。行頭禁則（、。っ」など）と行末禁則（「（など）を守り、
    行の後半に読点などがあればそこで折る。明示の改行も尊重する。"""
    font(ctx, size)
    out = []
    for para in s.replace("<br>", "\n").split("\n"):
        while para:
            if ctx.text_extents(para).x_advance <= maxw:
                out.append(para)
                break
            n = 1
            while n < len(para) and ctx.text_extents(para[:n + 1]).x_advance <= maxw:
                n += 1
            # 行の後半40%に区切りのよい文字があれば、そこで折る
            for j in range(n, int(n * 0.6), -1):
                if para[j - 1] in BREAK_AFTER:
                    n = j
                    break
            # 禁則：次の行頭に来てはいけない文字は前の行へ（ぶら下げ）、行末に来てはいけない文字は次の行へ
            while n < len(para) and para[n] in NO_HEAD:
                n += 1
            while n > 1 and para[n - 1] in NO_TAIL:
                n -= 1
            out.append(para[:n])
            para = para[n:]
    return out


def caption_pages(ctx, s, size, maxw, max_lines=2):
    """字幕をページ（最大 max_lines 行）に分け、各ページの文字数の割合を返す。"""
    lines = wrap(ctx, s, size, maxw)
    pages = [lines[i:i + max_lines] for i in range(0, len(lines), max_lines)]
    counts = [sum(len(x) for x in p) for p in pages]
    total = sum(counts) or 1
    return pages, [c / total for c in counts]


def star(ctx, x, y, r, rot=0.0):
    ctx.new_path()
    for i in range(8):
        rr = r if i % 2 == 0 else r * 0.38
        a = rot + i * math.pi / 4
        ctx.line_to(x + rr * math.cos(a), y + rr * math.sin(a))
    ctx.close_path()


INK = (0.13, 0.13, 0.16, 1)
SKIN = hexc("#F4CDA5")


def shovel(ctx, x, y, ang, s=1.0, label="AI"):
    """握り位置(x,y)から ang 方向（0=真下）に柄が伸びるスコップ。"""
    if s <= 0.01:
        return
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(-ang)
    ctx.scale(s, s)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_width(14)
    ctx.set_source_rgba(*INK)
    ctx.move_to(0, -38)
    ctx.line_to(0, 78)
    ctx.stroke()
    ctx.set_line_width(8)
    ctx.set_source_rgba(*hexc("#B9844F"))
    ctx.move_to(0, -38)
    ctx.line_to(0, 78)
    ctx.stroke()
    ctx.new_path()
    ctx.move_to(-27, 72)
    ctx.line_to(27, 72)
    ctx.line_to(23, 118)
    ctx.curve_to(15, 132, -15, 132, -23, 118)
    ctx.close_path()
    fill_stroke(ctx, hexc("#A9B3BD"), lw=4)
    if label:
        text(ctx, label, 0, 99, 25, hexc("#D23B2F"))
    ctx.restore()


def person(ctx, x, y, s=1.0, kind="staff", body="#4C83D1", hair="#7A4A2A", mouth=0.0,
           eyes="normal", sweat=False, arms="down", shovel_s=0.0, dig=0.0, rot=0.0,
           alpha=1.0, bob=0.0):
    """足元(x,y)を基準に人物を描く。"""
    if alpha <= 0.01:
        return
    ctx.save()
    if alpha < 1:
        ctx.push_group()
    ctx.translate(x, y - bob)
    ctx.rotate(rot)
    ctx.scale(s, s)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    boss = kind == "boss"
    bodyc = hexc(body)
    bw = 140 if boss else 100

    # 脚
    for lx in (-bw * 0.26, bw * 0.26):
        ctx.set_line_width(22)
        ctx.set_source_rgba(*INK)
        ctx.move_to(lx, -80)
        ctx.line_to(lx, -8)
        ctx.stroke()
        ctx.save()
        ctx.translate(lx + 4, -6)
        ctx.scale(1.6, 0.8)
        ctx.arc(0, 0, 12, 0, 2 * math.pi)
        ctx.restore()
        ctx.set_source_rgba(*INK)
        ctx.fill()

    # 胴体
    top = -205 if boss else -185
    rrect(ctx, -bw / 2, top, bw, -75 - top, 24)
    fill_stroke(ctx, bodyc)
    if boss:
        ctx.new_path()
        ctx.move_to(-22, top + 2)
        ctx.line_to(0, top + 46)
        ctx.line_to(22, top + 2)
        ctx.close_path()
        fill_stroke(ctx, (1, 1, 1, 1), lw=3)
        ctx.new_path()
        ctx.move_to(-7, top + 8)
        ctx.line_to(7, top + 8)
        ctx.line_to(10, top + 70)
        ctx.line_to(0, top + 82)
        ctx.line_to(-10, top + 70)
        ctx.close_path()
        fill_stroke(ctx, hexc("#D33A2C"), lw=3)
        ctx.set_source_rgba(*hexc("#E8C34A"))
        ctx.arc(-44, top + 34, 7, 0, 2 * math.pi)
        ctx.fill()
    else:
        rrect(ctx, 12, top + 26, 28, 13, 3)
        fill_stroke(ctx, (1, 1, 1, 1), lw=3)

    # 腕
    shx = bw / 2 - 6
    shy = top + 18
    L = 92 if boss else 80

    def arm(sx, sy, a, ln=L):
        ex, ey = sx + ln * math.sin(a), sy + ln * math.cos(a)
        ctx.set_line_width(26 if boss else 22)
        ctx.set_source_rgba(*INK)
        ctx.move_to(sx, sy)
        ctx.line_to(ex, ey)
        ctx.stroke()
        ctx.set_line_width(17 if boss else 14)
        ctx.set_source_rgba(*bodyc)
        ctx.move_to(sx, sy)
        ctx.line_to(ex, ey)
        ctx.stroke()
        ctx.arc(ex, ey, 14 if boss else 12, 0, 2 * math.pi)
        fill_stroke(ctx, SKIN, lw=4)
        return ex, ey

    if arms == "cross":
        rrect(ctx, -bw / 2 - 8, top + 45, bw + 16, 34, 16)
        fill_stroke(ctx, tuple(c * 0.85 for c in bodyc[:3]) + (1,))
        for hx in (-bw / 2 + 6, bw / 2 - 6):
            ctx.arc(hx, top + 62, 13, 0, 2 * math.pi)
            fill_stroke(ctx, SKIN, lw=4)
    elif arms == "push":
        arm(-shx, shy, 1.35, L + 18)
        arm(shx, shy, 1.45, L + 18)
    elif arms == "point":
        arm(-shx, shy, -0.2)
        arm(shx, shy, 1.5, L + 10)
    elif arms == "up":
        arm(-shx, shy, -2.6)
        arm(shx, shy, 2.6)
    elif arms == "flail":
        arm(-shx, shy, -2.2 + 0.5 * math.sin(dig * 12))
        arm(shx, shy, 2.4 + 0.5 * math.cos(dig * 12))
    elif arms == "dig":
        sw = math.sin(2 * math.pi * dig)
        a = 0.75 + 0.45 * sw
        hx, hy = shx + L * math.sin(a), shy + L * math.cos(a)
        arm(-shx, shy, 0.55 + 0.35 * sw, L * 0.95)
        arm(shx, shy, a)
        shovel(ctx, hx, hy, 0.35 + 0.75 * sw, shovel_s)
    else:  # down（スコップ持ちなら右手で持つ）
        arm(-shx, shy, -0.18)
        if shovel_s > 0:
            hx, hy = arm(shx, shy, 0.85)
            shovel(ctx, hx, hy, -0.08, shovel_s)
        else:
            arm(shx, shy, 0.18)

    # 頭
    hy = top - 58
    if boss:
        rrect(ctx, -60, hy - 62, 120, 124, 34)
        fill_stroke(ctx, SKIN)
        ctx.new_path()
        ctx.move_to(-62, hy - 6)
        ctx.line_to(-62, hy - 48)
        ctx.curve_to(-50, hy - 78, 50, hy - 78, 62, hy - 48)
        ctx.line_to(62, hy - 22)
        ctx.curve_to(30, hy - 44, -10, hy - 50, -40, hy - 30)
        ctx.line_to(-48, hy - 6)
        ctx.close_path()
        fill_stroke(ctx, hexc("#1C1C22"), lw=4)
    else:
        ctx.arc(0, hy, 60, 0, 2 * math.pi)
        fill_stroke(ctx, SKIN)
        ctx.new_path()
        ctx.arc(0, hy, 62, math.pi * 1.03, math.pi * 1.97)
        ctx.curve_to(40, hy - 30, -10, hy - 22, -60, hy - 12)
        ctx.close_path()
        fill_stroke(ctx, hexc(hair), lw=4)

    ex, ey = 22, hy + 4
    ctx.set_source_rgba(*INK)
    if eyes == "wide":
        for sx in (-ex, ex):
            ctx.arc(sx, ey, 15, 0, 2 * math.pi)
            fill_stroke(ctx, (1, 1, 1, 1), lw=4)
            ctx.arc(sx, ey, 5, 0, 2 * math.pi)
            ctx.set_source_rgba(*INK)
            ctx.fill()
    elif eyes == "happy":
        ctx.set_line_width(6)
        for sx in (-ex, ex):
            ctx.arc(sx, ey + 4, 10, math.pi * 1.1, math.pi * 1.9)
            ctx.stroke()
    elif eyes == "smug":
        ctx.set_line_width(9)
        for sx, d in ((-ex, 1), (ex, -1)):
            ctx.move_to(sx - 16 * d, ey - 22)
            ctx.line_to(sx + 14 * d, ey - 12)
            ctx.stroke()
        ctx.set_line_width(6)
        for sx in (-ex, ex):
            ctx.move_to(sx - 9, ey)
            ctx.line_to(sx + 9, ey)
            ctx.stroke()
    elif eyes == "evil":
        ctx.set_line_width(10)
        for sx, d in ((-ex, 1), (ex, -1)):
            ctx.move_to(sx - 18 * d, ey - 26)
            ctx.line_to(sx + 12 * d, ey - 8)
            ctx.stroke()
        for sx in (-ex, ex):
            ctx.arc(sx, ey + 2, 6, 0, 2 * math.pi)
            ctx.set_source_rgba(*hexc("#E8C34A"))
            ctx.fill()
        ctx.set_source_rgba(*INK)
    else:
        for sx in (-ex, ex):
            ctx.save()
            ctx.translate(sx, ey)
            ctx.scale(0.8, 1.0)
            ctx.arc(0, 0, 8, 0, 2 * math.pi)
            ctx.restore()
            ctx.fill()

    # 口
    my = hy + 32
    if boss:
        w = 30
        ctx.new_path()
        ctx.move_to(-w, my - 4)
        ctx.curve_to(-w * 0.5, my + 6 + 18 * mouth, w * 0.5, my + 6 + 18 * mouth, w, my - 4)
        if mouth > 0.1:
            ctx.close_path()
            fill_stroke(ctx, hexc("#7A2A2A"), lw=4)
            ctx.set_source_rgba(1, 1, 1, 1)
            rrect(ctx, -w * 0.7, my - 2, w * 1.4, 7, 2)
            ctx.fill()
        else:
            ctx.set_line_width(5)
            ctx.set_source_rgba(*INK)
            ctx.stroke()
    else:
        if mouth > 0.1:
            ctx.save()
            ctx.translate(0, my)
            ctx.scale(1.0, 0.25 + 0.75 * mouth)
            ctx.arc(0, 0, 11, 0, 2 * math.pi)
            ctx.restore()
            fill_stroke(ctx, hexc("#8A3434"), lw=4)
        else:
            ctx.set_line_width(5)
            ctx.set_source_rgba(*INK)
            if eyes == "wide":
                ctx.arc(0, my + 6, 9, math.pi * 1.15, math.pi * 1.85)
            else:
                ctx.arc(0, my - 8, 12, math.pi * 0.2, math.pi * 0.8)
            ctx.stroke()

    if sweat:
        sx, sy = (58 if not boss else 66), hy - 18
        ctx.new_path()
        ctx.move_to(sx, sy - 18)
        ctx.curve_to(sx + 12, sy, sx + 10, sy + 12, sx, sy + 12)
        ctx.curve_to(sx - 10, sy + 12, sx - 12, sy, sx, sy - 18)
        fill_stroke(ctx, hexc("#7CC4F0"), lw=3)

    if alpha < 1:
        ctx.pop_group_to_source()
        ctx.paint_with_alpha(alpha)
    ctx.restore()


def portrait_narrator(ctx, x, y, r, mouth):
    """語り手アキヒロの顔アイコン。"""
    ctx.save()
    ctx.arc(x, y, r, 0, 2 * math.pi)
    fill_stroke(ctx, hexc("#FFF6E5"), lw=6)
    ctx.arc(x, y, r - 3, 0, 2 * math.pi)
    ctx.clip()
    ctx.translate(x, y + r * 0.25)
    sc = r / 85
    ctx.scale(sc, sc)
    rrect(ctx, -70, 55, 140, 80, 30)
    fill_stroke(ctx, hexc("#3D5A80"))
    ctx.arc(0, -10, 58, 0, 2 * math.pi)
    fill_stroke(ctx, SKIN)
    ctx.new_path()
    ctx.arc(0, -12, 61, math.pi * 1.0, math.pi * 2.0)
    ctx.curve_to(50, -40, 0, -48, -61, -12)
    ctx.close_path()
    fill_stroke(ctx, hexc("#2B2B33"), lw=4)
    ctx.set_line_width(5)
    ctx.set_source_rgba(*INK)
    for sx in (-22, 22):
        rrect(ctx, sx - 16, -14, 32, 22, 7)
        ctx.stroke()
    ctx.move_to(-6, -4)
    ctx.line_to(6, -4)
    ctx.stroke()
    for sx in (-22, 22):
        ctx.arc(sx, -3, 4.5, 0, 2 * math.pi)
        ctx.fill()
    if mouth > 0.1:
        ctx.save()
        ctx.translate(0, 26)
        ctx.scale(1, 0.3 + 0.7 * mouth)
        ctx.arc(0, 0, 10, 0, 2 * math.pi)
        ctx.restore()
        fill_stroke(ctx, hexc("#8A3434"), lw=4)
    else:
        ctx.arc(0, 16, 12, math.pi * 0.2, math.pi * 0.8)
        ctx.stroke()
    ctx.restore()


def caption(ctx, tl, t, names, colors):
    ln = tl.caption(t)
    if not ln:
        return
    key = "+".join(ln.who)
    name = names.get(key) or names.get(ln.who[0], "")
    col = colors.get(key) or colors.get(ln.who[0], INK)
    k = ease_out((t - ln.t0) / 0.15)
    bx, by, bw, bh = 300, 880, 1460, 170
    ctx.save()
    ctx.translate(0, (1 - k) * 20)
    rrect(ctx, bx, by, bw, bh, 26)
    fill_stroke(ctx, (1, 1, 1, 0.94 * k), INK[:3] + (k,), 6)
    if name:
        font(ctx, 34)
        nw = ctx.text_extents(name).x_advance + 50
        rrect(ctx, bx + 30, by - 30, nw, 56, 16)
        fill_stroke(ctx, col[:3] + (k,), INK[:3] + (k,), 5)
        text(ctx, name, bx + 30 + nw / 2, by - 2, 34, (1, 1, 1, k))
    # 長い台詞は字幕だけページ送りする（音声は1回の合成のまま途切れない）。
    # ページの切り替えは、話している時間を文字数の割合で配分して決める。
    pages, ratios = caption_pages(ctx, ln.text, 52, bw - 120)
    frac = clamp((t - ln.t0) / max(ln.t1 - ln.t0, 1e-3))
    acc, pi = 0.0, 0
    for i, r in enumerate(ratios):
        acc += r
        pi = i
        if frac < acc:
            break
    lines = pages[pi]
    y0 = by + bh / 2 - (len(lines) - 1) * 33
    for i, s in enumerate(lines):
        text(ctx, s, bx + 60, y0 + i * 66, 52, INK[:3] + (k,), align="left")
    ctx.restore()
    if "narr" in ln.who:
        portrait_narrator(ctx, 190, 950, 95, tl.mouth("narr", t))


# ---------------------------------------------------------------- 書き出し
def render(draw, total, audio, out_path, frames=None):
    """draw(ctx, t) を毎フレーム呼んで MP4 に書き出す。frames=[t,...] なら静止画だけ出す。"""
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
    if frames is not None:
        for i, t in enumerate(frames):
            ctx = cairo.Context(surf)
            draw(ctx, t)
            surf.write_to_png(f"{out_path}_{i:02d}_{t:05.1f}s.png")
        return
    wav_path = out_path + ".wav"
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    n = int(total * FPS)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "bgr0", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", wav_path, "-c:v", "libx264", "-preset", "medium", "-crf", "20",
           "-pix_fmt", "yuv420p",
           # YouTube の基準（およそ -14 LUFS）に音量をそろえる
           "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", str(SR),
           "-c:a", "aac", "-b:a", "192k", "-shortest",
           "-movflags", "+faststart", out_path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(n):
        ctx = cairo.Context(surf)
        draw(ctx, f / FPS)
        surf.flush()
        p.stdin.write(bytes(surf.get_data()))
    p.stdin.close()
    p.wait()
    os.remove(wav_path)
    if p.returncode:
        raise RuntimeError("ffmpeg failed")
