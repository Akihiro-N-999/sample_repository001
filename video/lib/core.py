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


def phone_filter(a, lo=350.0, hi=3000.0):
    """電話らしいこもった音：帯域を絞り（lo〜hi Hz）、軽くひずませ、音量は元にそろえる。"""
    n = len(a)
    spec = np.fft.rfft(a, n=n)
    f = np.fft.rfftfreq(n, 1 / SR)
    g = 1 / (1 + (lo / np.maximum(f, 1e-3)) ** 4) / (1 + (f / hi) ** 4)
    b = np.fft.irfft(spec * g, n=n).astype(np.float32)
    r0, r1 = np.sqrt(np.mean(a ** 2) + 1e-12), np.sqrt(np.mean(b ** 2) + 1e-12)
    b = np.tanh(b * (r0 / r1) * 2.2) / 2.2 * 1.6
    b *= r0 / (np.sqrt(np.mean(b ** 2)) + 1e-12)
    return b.astype(np.float32)


# ---------------------------------------------------------------- タイムライン
class Line:
    def __init__(self, who, text, t0, t1, env, face=None):
        self.who, self.text, self.t0, self.t1, self.env = who, text, t0, t1, env
        self.face = face


class Timeline:
    """台本を時間軸に並べる。say()で台詞を合成し、mark()で演出の開始時刻を打つ。"""

    def __init__(self, vv, cast):
        self.vv, self.cast = vv, cast
        self.t = 0.0
        self.lines, self.marks, self.scenes, self.clips = [], {}, [], []
        self.voice_clips, self.bgms = [], []
        self.voice_idx = set()  # clips のうち台詞の音声の番号（品質チェックで声とそれ以外を分けるため）

    def say(self, who, text, voice=None, ids=None, speed=None, pitch=None, intonation=None,
            pause=1.0, pre=0.0, gap=0.3, vol=1.0, phone=False, face=None):
        """台詞1つ＝合成1回。字幕(text)の改行は表示だけに効き、読み上げは途切れない。
        pre/gap は台詞の前後の間（秒）。speed/pitch/intonation/pause は音声担当の調整値。
        phone=True で電話越しのこもった声にする。face は話者の表情名（tl.face() で引ける。
        複数人の台詞なら {人物: 表情名} の辞書）。"""
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
        if phone:
            mix = phone_filter(mix)
        t0 = self.t
        dur = n / SR
        hop = SR // FPS
        rms = np.array([np.sqrt(np.mean(mix[i:i + hop] ** 2) + 1e-9) for i in range(0, n, hop)])
        ref = np.percentile(rms, 90) + 1e-6
        env = np.clip(rms / ref, 0, 1)
        self.voice_idx.add(len(self.clips))
        self.clips.append((t0, mix * vol))
        self.voice_clips.append((t0, t0 + dur))
        line = Line(whos, text, t0, t0 + dur, env, face)
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

    def bgm(self, path, at=None, until=None, vol=0.18, fade=1.5, duck=0.4, fade_out=None, ramp=None):
        """BGMを at〜until 秒に流す（曲が短ければループ）。台詞の間は duck 倍に下げる。
        until を省くと動画の終わりまで。fade_out を渡すと終わりのフェードだけ別の長さにする。
        ramp=[(秒, 音量), ...] を渡すと、音量をその点のあいだで直線的に変える（vol は使わない）。"""
        self.bgms.append(dict(path=path, t0=self.t if at is None else at, t1=until,
                              vol=vol, fade=fade, duck=duck, fade_out=fade_out, ramp=ramp))

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

    def face(self, who, t, default="default"):
        """who の表情名。who が最後に話した台詞（t までに始まったもの）の face を、
        次に話すまで保つ。face の指定がなければ default。"""
        cur = default
        for ln in self.lines:
            if ln.t0 > t:
                break
            if who in ln.who and ln.face:
                cur = ln.face.get(who, default) if isinstance(ln.face, dict) else ln.face
        return cur

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
                fo = max(1, int(m["fade_out"] * SR)) if m.get("fade_out") is not None else f
                g[-min(fo, n):] = np.minimum(g[-min(fo, n):], np.linspace(1, 0, min(fo, n)))
                g *= 1 - (1 - m["duck"]) * speech[s:s + n]
                if m.get("ramp"):
                    rt, rv = zip(*m["ramp"])
                    vv = np.interp(np.arange(n) / SR + m["t0"], rt, rv).astype(np.float32)
                else:
                    vv = m["vol"]
                out[s:s + n] += track * g * vv
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


# ---------------------------------------------------------------- ファイル名のバージョン
# 統一ルール：生成するファイル（画像の素材、動画・音声などの成果物）は「名前_v番号.拡張子」にする。
# 作り直すたびに番号を上げ、同じ名前で上書きしない。読み込みは、指定がなければ最新の番号を使う。
_VER_RE = r"_v(\d+)$"


def _versions(path):
    """path（番号なしの名前）に対応する既存の版を [(番号, パス), ...] で返す。"""
    import glob
    import re
    base, ext = os.path.splitext(path)
    out = []
    for p in glob.glob(glob.escape(base) + "_v*" + ext):
        m = re.search(_VER_RE, os.path.splitext(p)[0])
        if m and os.path.splitext(p)[0][:m.start()] == base:
            out.append((int(m.group(1)), p))
    return sorted(out)


def latest(path, version=None):
    """番号なしの名前から、最新の版（version を指定すればその版）のパスを返す。
    すでに番号付きの名前ならそのまま返す。どの版もなければ番号なしの名前を返す。"""
    import re
    if re.search(_VER_RE, os.path.splitext(path)[0]):
        return path
    vs = _versions(path)
    if version is not None:
        for n, p in vs:
            if n == version:
                return p
        raise FileNotFoundError(f"{path} の v{version} がない")
    return vs[-1][1] if vs else path


def next_version(path):
    """番号なしの名前から、まだ使われていない次の版のパスを返す（書き出し用）。"""
    import re
    if re.search(_VER_RE, os.path.splitext(path)[0]):
        return path
    vs = _versions(path)
    n = vs[-1][0] + 1 if vs else 1
    base, ext = os.path.splitext(path)
    return f"{base}_v{n}{ext}"


NARRATOR_IMAGE = None  # 語り手アイコンに使う画像（PNG）。None ならコードで描いた顔を使う
_img_cache = {}


def load_image(path):
    path = latest(path)
    if path not in _img_cache:
        _img_cache[path] = cairo.ImageSurface.create_from_png(path)
    return _img_cache[path]


def portrait_image(ctx, x, y, r, path, focus=(0.5, 0.56), speaking=0.0, ring=None):
    """画像を円形に切り抜いて描く。focus は円の中心にする画像内の位置（0〜1）。
    話している間は縁の色を濃くして、口が動かない代わりに話者を示す。"""
    img = load_image(path)
    iw, ih = img.get_width(), img.get_height()
    sc = 2 * r / min(iw, ih)
    ctx.save()
    ctx.arc(x, y, r, 0, 2 * math.pi)
    ctx.clip()
    ctx.translate(x - focus[0] * iw * sc, y - focus[1] * ih * sc)
    ctx.scale(sc, sc)
    ctx.set_source_surface(img, 0, 0)
    ctx.paint()
    ctx.restore()
    ctx.arc(x, y, r, 0, 2 * math.pi)
    ctx.set_line_width(6 + 4 * speaking)
    ctx.set_source_rgba(*(ring or hexc("#F5C542" if speaking else "#FFF6E5")))
    ctx.stroke()


def caption(ctx, tl, t, names, colors, by=880):
    ln = tl.caption(t)
    if not ln:
        return
    key = "+".join(ln.who)
    name = names.get(key) or names.get(ln.who[0], "")
    col = colors.get(key) or colors.get(ln.who[0], INK)
    k = ease_out((t - ln.t0) / 0.15)
    bx, bw, bh = 300, 1460, 170
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
        if NARRATOR_IMAGE and os.path.exists(latest(NARRATOR_IMAGE)):
            portrait_image(ctx, 190, 950, 95, latest(NARRATOR_IMAGE),
                           speaking=1.0 if tl.speaking("narr", t) else 0.0)
        else:
            portrait_narrator(ctx, 190, 950, 95, tl.mouth("narr", t))


# ---------------------------------------------------------------- 書き出し
def loudnorm_filter(wav_path, target=-14.0, tp=-1.5, lra=11):
    """2段階のラウドネス正規化。まず音声全体を測り、その値を使って音量をそろえる。
    1回だけの正規化は無音の多い短い動画で小さめに仕上がるため。"""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", wav_path, "-af",
                        f"loudnorm=I={target}:TP={tp}:LRA={lra}:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    import re
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if not m:
        return f"loudnorm=I={target}:TP={tp}:LRA={lra}"
    v = json.loads(m.group(0))
    return (f"loudnorm=I={target}:TP={tp}:LRA={lra}:measured_I={v['input_i']}:"
            f"measured_TP={v['input_tp']}:measured_LRA={v['input_lra']}:"
            f"measured_thresh={v['input_thresh']}:offset={v['target_offset']}:linear=true")


def render(draw, total, audio, out_path, frames=None):
    """draw(ctx, t) を毎フレーム呼んで MP4 に書き出す。frames=[t,...] なら静止画だけ出す。"""
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
    if frames is not None:
        for i, t in enumerate(frames):
            ctx = cairo.Context(surf)
            draw(ctx, t)
            surf.write_to_png(f"{out_path}_{i:02d}_{t:05.1f}s.png")
        return
    out_path = next_version(out_path)
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
           "-af", loudnorm_filter(wav_path), "-ar", str(SR),
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
    return out_path


# ---------------------------------------------------------------- 画像の立ち絵（画像生成AIで作った素材）
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", "cache", "images")


_CODE_TAG = None


def _code_tag():
    """画像を加工する関数（緑の抜き・口と目の切り出し）の中身から作る短い印。
    関数を直すと印が変わり、直す前に作ったキャッシュを使わなくなる
    （直す前のキャッシュが残り、口の位置がずれたままになったことがあった。2026-11-20）。"""
    global _CODE_TAG
    if _CODE_TAG is None:
        import inspect
        src = "".join(inspect.getsource(f) for f in (key_green, mouth_patch, eye_patch))
        _CODE_TAG = hashlib.sha1(src.encode()).hexdigest()[:8]
    return _CODE_TAG


def _pil_to_surface(im, key):
    """PIL の RGBA 画像を cairo のサーフェスにする（PNG を経由してキャッシュ）。"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{key}_{_code_tag()}.png")
    if not os.path.exists(path):
        im.save(path)
    return load_image(path)


def key_green(path):
    """緑一色の背景（#00FF00 付近）を透明にした PIL 画像を返す。縁の緑かぶりも抑える。"""
    from PIL import Image
    path = latest(path)
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    greenness = g - np.maximum(r, b)          # 大きいほど背景
    # Gemini の緑は #00FF00 とは限らない（暗い緑 #45AF4D になることがある）ので、
    # 四隅の背景の緑の強さを測り、それに合わせて抜く範囲を決める
    k = max(8, min(a.shape[:2]) // 20)
    corners = np.concatenate([greenness[:k, :k].ravel(), greenness[:k, -k:].ravel(),
                              greenness[-k:, :k].ravel(), greenness[-k:, -k:].ravel()])
    gbg = float(np.median(corners))
    lo, hi = max(20.0, gbg * 0.3), max(60.0, gbg * 0.7)
    alpha = np.clip((hi - greenness) / (hi - lo), 0, 1)
    g2 = np.minimum(g, np.maximum(r, b) + 10)  # 緑かぶりを抑える
    out = np.dstack([r, g2, b, alpha * 255]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def mouth_patch(base_path, open_path, feather=0.35):
    """口開きの差分から口のまわりだけを取り出した RGBA 画像を返す。
    差分画像は眉や目の線も少し描き直されていることが多いので、画像を丸ごと差し替えると
    口パクのたびに目元がちらつく。口の範囲だけを楕円でぼかして切り取り、基準画像に重ねる。"""
    from PIL import Image
    base = np.asarray(Image.open(base_path).convert("RGB")).astype(np.int32)
    opn = key_green(open_path)
    if opn.size != (base.shape[1], base.shape[0]):  # チャットに貼った画像は縮んで届くことがある
        opn = opn.resize((base.shape[1], base.shape[0]), Image.LANCZOS)
    o = np.asarray(opn).astype(np.int32)
    h, w = base.shape[:2]
    # 口の位置は、縮めてぼかした画像の差で探す。拡大縮小や JPEG で輪郭線が 1〜2 画素ずれた差は
    # 縮めると薄まって消え、塗りのある口（暗い赤の口の中）だけが残る。
    f = max(1, w // 224)
    sw, sh = w // f, h // f
    # 基準画像も同じく緑を抜いてから比べる（抜いた画像と抜いていない画像を比べると、
    # あごの横に見える背景の緑が「差」になり、口の位置が横にずれる）
    bk = np.asarray(key_green(base_path).convert("RGB"))
    bs = np.asarray(Image.fromarray(bk).resize((sw, sh), Image.BOX)).astype(np.int32)
    os_ = np.asarray(Image.fromarray(o[..., :3].astype(np.uint8)).resize((sw, sh), Image.BOX)).astype(np.int32)
    sdiff = np.abs(bs - os_).sum(2) > 90
    # 口は顔の下半分の中央にあるので、その範囲の強い差だけを見る
    y0, y1, x0, x1 = int(sh * 0.3), int(sh * 0.8), int(sw * 0.3), int(sw * 0.7)
    ys, xs = np.where(sdiff[y0:y1, x0:x1])
    if len(ys) < 4:
        raise ValueError(f"口の差が見つからない: {open_path}")
    # 外れ値（眉の描き直しや汗のしずくなど）を除くため、差の多い行の塊のうち最も下の大きいものを口とみなす
    rows = np.bincount(ys, minlength=y1 - y0)
    thr = max(1, rows.max() * 0.15)
    on = rows > thr
    blocks, start = [], None
    for i, v in enumerate(list(on) + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            blocks.append((start, i))
            start = None
    by0, by1 = max(blocks, key=lambda b: (b[1] - b[0]) * (b[0] + 1) ** 0.5)
    sel = (ys >= by0) & (ys < by1)
    cx = (np.median(xs[sel]) + x0 + 0.5) * f
    cy = ((by0 + by1) / 2 + y0) * f
    rx = (np.percentile(xs[sel], 95) - np.percentile(xs[sel], 5) + 1) / 2 * f * 1.5 + 12
    ry = (by1 - by0) / 2 * f * 1.6 + 12
    # 輪郭線の描き直しを拾って範囲が広がりすぎないよう、口の大きさの上限で抑える
    rx, ry = min(rx, w * 0.18), min(ry, h * 0.07)  # 横に大きく開いた笑い口が切れないよう 0.18（0.14 では口の端がぼけた）
    yy, xx = np.mgrid[0:h, 0:w]
    dist = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
    m = np.clip((1 - dist) / feather, 0, 1)
    out = o.copy()
    out[..., 3] = (out[..., 3] * m).astype(np.int32)
    return Image.fromarray(out.astype(np.uint8), "RGBA"), (cx, cy, rx, ry)


def eye_patch(base_path, blink_path, feather=0.4):
    """目閉じの差分から、両目のまわりだけを取り出した RGBA 画像を返す。目の位置は差分から自動で見つける。
    顔の上半分で基準画像と差のある画素を左右2つの塊に分け、塊ごとに楕円でぼかして切り取る。"""
    from PIL import Image
    base = np.asarray(Image.open(base_path).convert("RGB")).astype(np.int32)
    blk = key_green(blink_path)
    if blk.size != (base.shape[1], base.shape[0]):  # チャットに貼った画像は縮んで届くことがある
        blk = blk.resize((base.shape[1], base.shape[0]), Image.LANCZOS)
    o = np.asarray(blk).astype(np.int32)
    h, w = base.shape[:2]
    diff = (np.abs(base - o[..., :3]).sum(2) > 150) & (o[..., 3] > 200)  # 背景の緑かぶり除去による差を除く
    y0, y1, x0, x1 = int(h * 0.05), int(h * 0.6), int(w * 0.2), int(w * 0.8)
    ys, xs = np.where(diff[y0:y1, x0:x1])
    if len(ys) < 20:
        raise ValueError(f"目の差が見つからない: {blink_path}")
    ys, xs = ys + y0, xs + x0
    # 左右に分ける（x の最大の隙間で割る。隙間が小さければ1つの塊）
    order = np.sort(xs)
    gaps = np.diff(order)
    clusters = [(ys, xs)]
    if len(gaps) and gaps.max() > w * 0.03:
        cut = order[gaps.argmax()] + gaps.max() / 2
        clusters = [(ys[xs < cut], xs[xs < cut]), (ys[xs >= cut], xs[xs >= cut])]
    yy, xx = np.mgrid[0:h, 0:w]
    m = np.zeros((h, w), np.float32)
    boxes = []
    for cy_, cx_ in clusters:
        if len(cy_) < 10:
            continue
        cx, cy = (np.percentile(cx_, 5) + np.percentile(cx_, 95)) / 2, (np.percentile(cy_, 5) + np.percentile(cy_, 95)) / 2
        rx = (np.percentile(cx_, 95) - np.percentile(cx_, 5)) / 2 * 1.4 + 10
        ry = (np.percentile(cy_, 95) - np.percentile(cy_, 5)) / 2 * 1.5 + 10
        rx, ry = min(rx, w * 0.12), min(ry, h * 0.06)
        dist = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
        m = np.maximum(m, np.clip((1 - dist) / feather, 0, 1))
        boxes.append((cx, cy, rx, ry))
    out = o.copy()
    out[..., 3] = (out[..., 3] * m).astype(np.int32)
    return Image.fromarray(out.astype(np.uint8), "RGBA"), boxes


class Tachie:
    """緑背景の立ち絵。基準画像に、口の差分（半開き・開き）と目閉じの差分を、
    口・目のまわりだけ重ねる。差分がなければその動きはしない。

    使い方
      Tachie(base, open)                              従来どおり（口は閉じ／開き）
      Tachie(base, open, half=..., blink=...)         口3段階＋まばたき
      Tachie({"default": dict(base=.., open=.., half=.., blink=..),
              "angry": dict(base=.., open=..), ...})  表情ごとの組（先頭が既定の表情）
    draw(..., face="angry", t=秒) で表情を選ぶ。t を渡すとまばたきする（数秒おきにランダム。
    seed が同じなら毎回同じ間隔）。口は mouth（tl.mouth の値）で 閉じ(<=0.2)／半開き／開き(>0.8)。"""

    def __init__(self, base_path, open_path=None, half=None, blink=None, seed=None):
        if isinstance(base_path, dict):
            faces = base_path
        else:
            faces = {"default": dict(base=base_path, open=open_path, half=half, blink=blink)}
        self.faces = {}
        for fname, d in faces.items():
            if isinstance(d, str):
                d = dict(base=d)
            self.faces[fname] = self._load(d)
        self.default = next(iter(self.faces))
        f0 = self.faces[self.default]
        self.base, self.mouth, self.w, self.h = f0["base"], f0["open"], f0["w"], f0["h"]
        self.mouth_box = f0.get("mouth_box")
        rng = np.random.default_rng(seed if seed is not None else
                                    int(hashlib.sha1(str(list(faces)[0]).encode()).hexdigest()[:8], 16))
        ts, t = [], rng.uniform(1.0, 3.0)
        while t < 1500:
            ts.append(t)
            t += rng.uniform(2.5, 5.5)
        self.blinks = np.array(ts)
        self.blink_dur = 0.16

    @staticmethod
    def _load(d):
        base_path = latest(d["base"])
        name = os.path.splitext(os.path.basename(base_path))[0]
        stamp = str(int(os.path.getmtime(base_path)))
        out = dict(base=_pil_to_surface(key_green(base_path), f"{name}_{stamp}_key"),
                   open=None, half=None, blink=None)
        for k in ("open", "half"):
            pth = latest(d[k]) if d.get(k) else None
            if pth and os.path.exists(pth):
                patch, box = mouth_patch(base_path, pth)
                out[k] = _pil_to_surface(patch, f"{name}_{stamp}_mouth_{os.path.basename(pth)}_{int(os.path.getmtime(pth))}")
                if k == "open":
                    out["mouth_box"] = box
        pth = latest(d["blink"]) if d.get("blink") else None
        if pth and os.path.exists(pth):
            patch, _ = eye_patch(base_path, pth)
            out["blink"] = _pil_to_surface(patch, f"{name}_{stamp}_eyes_{os.path.basename(pth)}_{int(os.path.getmtime(pth))}")
        out["w"], out["h"] = out["base"].get_width(), out["base"].get_height()
        return out

    def blinking(self, t):
        if t is None:
            return False
        i = np.searchsorted(self.blinks, t, side="right") - 1
        return i >= 0 and t - self.blinks[i] < self.blink_dur

    def draw(self, ctx, x, y, height, mouth=0.0, alpha=1.0, dim=0.0, bob=0.0, flip=False, dim_rgb=(1, 1, 1),
             face=None, t=None):
        """下端中央を (x, y) に合わせ、高さ height で描く。dim は話していない人を薄くする量。
        face は表情名（なければ既定）、t は時刻（まばたき用。None ならまばたきしない）。"""
        f = self.faces.get(face) or self.faces[self.default]
        k = height / f["h"]
        if k <= 1e-3 or alpha <= 0.01:
            return
        ctx.save()
        ctx.translate(x, y - bob)
        ctx.scale(-k if flip else k, k)
        ctx.translate(-f["w"] / 2, -f["h"])
        ctx.push_group()
        ctx.set_source_surface(f["base"], 0, 0)
        ctx.paint()
        if f["blink"] is not None and self.blinking(t):
            ctx.set_source_surface(f["blink"], 0, 0)
            ctx.paint()
        mp = None
        if mouth > 0.2:
            mp = f["half"] if (f["half"] is not None and mouth <= 0.8) else f["open"]
        if mp is not None:
            ctx.set_source_surface(mp, 0, 0)
            ctx.paint()
        if dim > 0:
            ctx.set_source_rgba(*dim_rgb, dim)
            ctx.mask_surface(f["base"], 0, 0)
        ctx.pop_group_to_source()
        ctx.paint_with_alpha(alpha)
        ctx.restore()
