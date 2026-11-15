"""品質校閲用の機械チェック。耳で聞かずに確かめられることを数値で洗い出す。

使い方:
    python3 video/lib/audio_check.py voice video/episodes/<slug>
        台本（script.md）の台詞を音声にして確かめる（G2 の前）。
    python3 video/lib/audio_check.py mix video/episodes/<slug> [--mp4 video/out/<slug>.mp4]
        episode.py の実装と完成音声を確かめる（G4 の前）。

結果は video/out/<slug>_check_<voice|mix>.md に書く。
✗ = 直す必要がある、△ = 品質校閲が判断する、・= 参考情報。
"""
import importlib.util
import json
import os
import re
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from core import SR, Voicevox, caption_pages  # noqa: E402
from voice_preview import load_lines, load_tuning, load_voices  # noqa: E402

OUT = os.path.join(HERE, "..", "out")
END_CHARS = set("。！？!?…」』）)〜♪っッー")
PUNCT = set("、。！？!?…‥・「」『』（）()〜ー　 ")
MAX_SEC, MAX_CPS, LONG_PAUSE = 8.0, 8.0, 0.6

# よくある読み間違い：(台詞の文字列の正規表現, 読み（カナ）に出たら間違いとみなす正規表現, 説明)
# 見つけたら追記していく（ユーザーや校閲が気づいた読み間違いは、次から機械で拾えるようにする）
KNOWN_MISREADINGS = [
    (r"(筋|理屈|話|意見|主張|道理)[はがも、]*、?\s*通(っ|る|ら|り)", r"カヨ", "「筋が通る」などの「通る」を「かよう」と読んでいる（とおる）"),
    (r"碑", r"イシブミ", "「碑」を「いしぶみ」と読んでいる（ひ）"),
    (r"AI", r"(?<![エー])アイ(?!ディア)", "「AI」を「アイ」と読んでいる（エーアイ）"),
    (r"墓穴", r"ハカアナ", "「墓穴」を「はかあな」と読んでいる（ぼけつ）"),
    (r"稟議", r"ヒンギ|リンケ", "「稟議」の読み（りんぎ）"),
    (r"他人事", r"タニンゴト", "「他人事」の読み（ひとごと）"),
    (r"一段落", r"ヒトダンラク", "「一段落」の読み（いちだんらく）"),
]


def db(x):
    return 20 * np.log10(max(x, 1e-9))


def rms(a):
    return float(np.sqrt(np.mean(a ** 2))) if len(a) else 0.0


def silences(a, min_len):
    """発話の途中にある min_len 秒以上の無音区間 [(開始秒, 長さ)]。頭と終わりの無音は除く。"""
    hop = SR // 100
    fr = np.array([rms(a[i:i + hop]) for i in range(0, len(a), hop)])
    if not len(fr) or fr.max() == 0:
        return []
    voiced = fr > fr.max() * 0.03  # ピークから約 -30dB 未満を無音とみなす
    idx = np.where(voiced)[0]
    if len(idx) < 2:
        return []
    out, run = [], 0
    for k in range(idx[0], idx[-1] + 1):
        if not voiced[k]:
            run += 1
        else:
            if run * 0.01 >= min_len:
                out.append(((k - run) * 0.01, run * 0.01))
            run = 0
    return out


def n_chars(s):
    return sum(1 for c in s if c not in PUNCT)


# ---------------------------------------------------------------- voice モード
def check_voice(ep):
    slug = os.path.basename(ep.rstrip("/"))
    voices = load_voices(os.path.join(ep, "characters.md"))
    lines = load_lines(os.path.join(ep, "script.md"))
    tuning = load_tuning(os.path.join(ep, "sound.md"))
    vv = Voicevox(cache_dir=os.path.join(OUT, "cache"))
    rep, n_x, n_t = [], 0, 0
    total = 0.0
    for i, ln in enumerate(lines):
        tu = tuning.get(ln["no"], {})
        items = []
        text = ln["text"]
        if "<br>" in text or "\n" in text:
            items.append("✗ 台詞に改行（<br>）がある：読み上げは切れないが、字幕の改行はエンジンに任せる")
        last = text.rstrip()[-1:] if text.strip() else ""
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        if last in ("、", ",", "，"):
            items.append("✗ 読点で終わっている：文の途中で台詞（行）が分かれている")
        elif last not in END_CHARS:
            items.append("△ 文末に句点などがない：文の途中で分かれていないか確かめる")
        if nxt and nxt["who"] == ln["who"] and last in ("、", ",", "，"):
            items.append(f"✗ 次の台詞 #{nxt['no']} と同じ話者で、1つの文を2行に分けている可能性が高い")
        speak = (ln["yomi"] or text).replace("<br>", "")
        if not ln["yomi"] and re.search(r"[0-9０-９A-Za-zＡ-Ｚａ-ｚ%％]", text):
            items.append("△ 数字・英字・記号を含む：読み（カナ）を確かめる")
        who = ln["who"].replace(" ", "").split("+")[0]
        v = voices.get(who)
        if not v:
            items.append(f"✗ 話者「{who}」が characters.md の声の割り当てにない")
            rep.append((ln, items, None, None))
            n_x += 1
            continue
        sid = tu.get("id") or next((k2 for k, k2 in v["styles"].items() if k in ln["tone"]), v["id"])
        kw = {k: tu[k] for k in ("pitch", "intonation", "pause") if tu.get(k) is not None}
        a = vv.synth(speak, sid, speed=tu.get("speed") or v["speed"], **kw)
        dur = len(a) / SR
        total += dur + (tu.get("pre") or 0) + (tu.get("gap") if tu.get("gap") is not None else 0.3)
        cps = n_chars(text) / max(dur, 0.1)
        if dur > MAX_SEC:
            items.append(f"△ 長い台詞（{dur:.1f}秒）：句点で分けるか、話速を見直す")
        if cps > MAX_CPS:
            items.append(f"△ 速い（1秒あたり{cps:.1f}文字）：聞き取りにくい可能性")
        for s0, ln_s in silences(a, LONG_PAUSE):
            items.append(f"△ 台詞の途中に {ln_s:.2f}秒の無音（{s0:.1f}秒あたり）：意図した間か確かめる")
        if np.abs(a).max() >= 0.99:
            items.append("✗ 音割れのおそれ（ピークが上限）：音量か抑揚を下げる")
        q = json.loads(vv._post("/audio_query", {"text": speak, "speaker": sid}))
        for tpat, kpat, why in KNOWN_MISREADINGS:
            if re.search(tpat, text) and re.search(kpat, q.get("kana", "")):
                items.append(f"✗ 読み間違いのおそれ：{why}。読み欄で直す")
        n_x += sum(x.startswith("✗") for x in items)
        n_t += sum(x.startswith("△") for x in items)
        rep.append((ln, items, dur, q.get("kana", "")))

    md = [f"# 品質チェック（台詞の音声）：{slug}", "",
          f"- 台詞 {len(lines)} / 合計およそ {total:.0f} 秒 / ✗ {n_x} 件 / △ {n_t} 件", ""]
    md.append("## 指摘")
    for ln, items, dur, kana in rep:
        for x in items:
            md.append(f"- [#{ln['no']} {ln['who']}] {x}  \n  「{ln['text']}」")
    if not any(items for _, items, _, _ in rep):
        md.append("- なし")
    md += ["", "## 読みの一覧（アクセント記号つき。' がアクセントの位置、/ が区切り、_ が無声化）", "",
           "| # | 話者 | 秒 | 台詞 | 読み |", "|---|---|---|---|---|"]
    for ln, _, dur, kana in rep:
        md.append(f"| {ln['no']} | {ln['who']} | {dur or 0:.1f} | {ln['text']} | {kana or ''} |")
    return slug, "voice", md, n_x


# ---------------------------------------------------------------- mix モード
def load_episode(ep):
    spec = importlib.util.spec_from_file_location("episode", os.path.join(ep, "episode.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def loudness(mp4):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", mp4, "-af",
                        "loudnorm=I=-14:TP=-1.5:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    return json.loads(m.group(0)) if m else None


def check_mix(ep, mp4=None):
    import cairo
    slug = os.path.basename(ep.rstrip("/"))
    mod = load_episode(ep)
    tl = mod.build(Voicevox(cache_dir=os.path.join(OUT, "cache")))
    total = tl.t
    md = [f"# 品質チェック（完成音声と実装）：{slug}", "", f"- 長さ {total:.1f} 秒 / 台詞 {len(tl.lines)}", ""]
    n_x = 0

    # 1. 台本と実装の一致
    md.append("## 台本と実装の一致")
    sp = os.path.join(ep, "script.md")
    if os.path.exists(sp):
        rows = load_lines(sp)
        impl = [("+".join(ln.who), ln.text.replace("\n", "")) for ln in tl.lines]
        want = [(r["who"].replace(" ", ""), r["text"].replace("<br>", "")) for r in rows]
        bad = []
        for k in range(max(len(impl), len(want))):
            w = want[k] if k < len(want) else None
            g = impl[k] if k < len(impl) else None
            if w != g:
                bad.append(f"- ✗ {k + 1}番目：台本 {w} ／ 実装 {g}")
        if len(impl) > len(want):
            bad.append(f"- ✗ 実装の台詞が台本より {len(impl) - len(want)} 個多い：台本の1行を複数の tl.say() に分けていないか")
        md += bad[:30] or ["- 一致（台詞の数・話者・文言）"]
        n_x += len(bad)
    else:
        md.append("・script.md がないため照合しない")

    # 2. 台詞の重なり・間
    md += ["", "## 台詞のタイミング"]
    items = []
    for a, b in zip(tl.lines, tl.lines[1:]):
        if b.t0 < a.t1 - 0.01:
            items.append(f"- ✗ 台詞が重なっている（{a.t1 - b.t0:.2f}秒）：「{a.text[:15]}」と「{b.text[:15]}」")
        elif b.t0 - a.t1 > 3.0 and tl.scene_at(a.t1) == tl.scene_at(b.t0):
            items.append(f"- △ 同じ場面で {b.t0 - a.t1:.1f}秒 台詞がない（{a.t1:.1f}秒〜）：意図した間か")
    n_x += sum("✗" in x for x in items)
    md += items or ["- 問題なし"]

    # 3. 声と効果音・BGMのバランス（台詞ごと）
    md += ["", "## 声と効果音・BGMのバランス"]
    voice = tl.audio(total, parts=("voice",), normalize=False)
    sfx = tl.audio(total, parts=("sfx",), normalize=False)
    bgm = tl.audio(total, parts=("bgm",), normalize=False) if tl.bgms else None
    items = []
    for ln in tl.lines:
        s, e = int(ln.t0 * SR), int(ln.t1 * SR)
        v = rms(voice[s:e])
        if bgm is not None:
            ratio = db(v) - db(rms(bgm[s:e]))
            if ratio < 6:
                items.append(f"- ✗ BGM が大きい（声との差 {ratio:.0f}dB）：「{ln.text[:20]}」")
            elif ratio < 12:
                items.append(f"- △ BGM がやや大きい（声との差 {ratio:.0f}dB）：「{ln.text[:20]}」")
        sv = rms(sfx[s:e])
        if sv > 0 and db(sv) > db(v) - 6:
            items.append(f"- △ 効果音が台詞にかぶって大きい（{ln.t0:.1f}秒〜）：「{ln.text[:20]}」")
    if bgm is None:
        items.append("・BGM なし")
    n_x += sum("✗" in x for x in items)
    md += items or ["- 問題なし（声と BGM の差 12dB 以上、効果音のかぶりなし）"]

    # 4. 字幕のページ送り
    md += ["", "## 字幕のページ送り"]
    ctx = cairo.Context(cairo.ImageSurface(cairo.FORMAT_RGB24, 10, 10))
    items = []
    for ln in tl.lines:
        pages, ratios = caption_pages(ctx, ln.text, 52, 1340)
        dur = ln.t1 - ln.t0
        if len(pages) > 1:
            short = [r * dur for r in ratios if r * dur < 1.2]
            if short:
                items.append(f"- △ 字幕のページが {min(short):.1f}秒で切り替わる（読み切れないおそれ）：「{ln.text[:20]}」")
            else:
                items.append(f"・{len(pages)}ページに分けて表示：「{ln.text[:20]}」")
    md += items or ["- すべて1ページに収まる"]

    # 5. 書き出した MP4 の音量
    md += ["", "## 書き出した MP4 の音量"]
    if mp4 and os.path.exists(mp4):
        L = loudness(mp4)
        if L:
            i, tp = float(L["input_i"]), float(L["input_tp"])
            ok = -16 <= i <= -12 and tp <= -1.0
            md.append(f"- {'問題なし' if ok else '✗ 基準外'}：ラウドネス {i:.1f} LUFS（目安 -14）、トゥルーピーク {tp:.1f} dBTP（目安 -1 以下）")
            n_x += 0 if ok else 1
        else:
            md.append("・測定できなかった")
    else:
        md.append("・MP4 の指定なし（--mp4 で指定すると測る）")
    return slug, "mix", md, n_x


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("voice", "mix"):
        raise SystemExit(__doc__)
    mode, ep = sys.argv[1], sys.argv[2]
    mp4 = sys.argv[sys.argv.index("--mp4") + 1] if "--mp4" in sys.argv else None
    os.makedirs(OUT, exist_ok=True)
    slug, kind, md, n_x = check_voice(ep) if mode == "voice" else check_mix(ep, mp4)
    path = os.path.join(OUT, f"{slug}_check_{kind}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print(f"✗ {n_x} 件 → {path}")


if __name__ == "__main__":
    main()
