"""台本の台詞だけを VOICEVOX で読み上げて1本の音声にする（アニメ制作前の聞き取り確認用）。

使い方:
    python3 video/lib/voice_preview.py video/episodes/<slug>

出力（video/out/）:
    <slug>_voice.mp3  台詞を順に並べた音声（台詞の間に0.6秒の無音）
    <slug>_voice.txt  台詞ごとの話者・声ID・秒数・VOICEVOX が実際に読むカナ

script.md の台本表（| # | 話者 | 台詞（字幕） | 読み | 声の調子 | 演出 |）と、
characters.md の「声の割り当て」表（| 話者ID | 表示名 | VOICEVOX話者 | 基本ID | 話速 | 調子別ID |）を読む。
sound.md があれば「台詞の調整」表（| # | 声ID | 話速 | 高さ | 抑揚 | 句読点の間 | 前の間 | 後の間 | メモ |）も反映する。
空欄はキャラクターの既定値のまま。
"""
import json
import os
import subprocess
import sys
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import SR, Voicevox, next_version  # noqa: E402


def tables(md):
    """Markdown 内の表を [(見出し行のセル, [行のセル, ...]), ...] で返す。"""
    out, cur = [], None
    for raw in md.splitlines():
        line = raw.strip()
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line[1:-1].split("|")]
            if cur is None:
                cur = (cells, [])
            elif all(set(c) <= set("-: ") for c in cells):
                continue
            else:
                cur[1].append(cells)
        else:
            if cur:
                out.append(cur)
            cur = None
    if cur:
        out.append(cur)
    return out


def load_voices(path):
    for head, rows in tables(open(path, encoding="utf-8").read()):
        if head[:1] == ["話者ID"] and "基本ID" in head:
            idx = {h: i for i, h in enumerate(head)}
            voices = {}
            for r in rows:
                styles = {}
                for part in r[idx["調子別ID"]].replace("、", ",").split(","):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        styles[k.strip()] = int(v.strip())
                voices[r[0]] = {
                    "name": r[idx["表示名"]],
                    "id": int(r[idx["基本ID"]]),
                    "speed": float(r[idx["話速"]] or 1.1),
                    "styles": styles,
                }
            return voices
    raise SystemExit(f"{path} に「声の割り当て」の表（話者ID / 基本ID の列）が見つかりません")


def load_lines(path):
    lines = []
    for head, rows in tables(open(path, encoding="utf-8").read()):
        if len(head) >= 5 and head[1] == "話者" and head[2].startswith("台詞"):
            for r in rows:
                if len(r) >= 5 and r[2]:
                    lines.append({"no": r[0], "who": r[1], "text": r[2], "yomi": r[3], "tone": r[4]})
    if not lines:
        raise SystemExit(f"{path} に台本の表（# / 話者 / 台詞 …）が見つかりません")
    return lines


def load_tuning(path):
    """sound.md の「台詞の調整」表を {台詞番号: {...}} で返す。ファイルがなければ空。"""
    if not os.path.exists(path):
        return {}
    for head, rows in tables(open(path, encoding="utf-8").read()):
        if head[:2] == ["#", "声ID"] and "話速" in head:
            idx = {h: i for i, h in enumerate(head)}
            out = {}
            for r in rows:
                def num(col, cast=float):
                    v = r[idx[col]] if col in idx and idx[col] < len(r) else ""
                    return cast(v) if v.strip() else None
                out[r[0]] = {"id": num("声ID", int), "speed": num("話速"), "pitch": num("高さ"),
                             "intonation": num("抑揚"), "pause": num("句読点の間"),
                             "pre": num("前の間"), "gap": num("後の間")}
            return out
    return {}


def main():
    ep = sys.argv[1].rstrip("/")
    slug = os.path.basename(ep)
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    out_dir = os.path.join(root, "out")
    os.makedirs(out_dir, exist_ok=True)
    voices = load_voices(os.path.join(ep, "characters.md"))
    lines = load_lines(os.path.join(ep, "script.md"))
    tuning = load_tuning(os.path.join(ep, "sound.md"))
    vv = Voicevox(cache_dir=os.path.join(out_dir, "cache"))

    chunks, report, problems = [], [], []
    for ln in lines:
        tu = tuning.get(ln["no"], {})
        whos = ln["who"].replace(" ", "").split("+")
        speak = (ln["yomi"] or ln["text"]).replace("<br>", "").replace("\n", "")
        auds, ids = [], []
        for w in whos:
            v = voices.get(w)
            if not v:
                problems.append(f"#{ln['no']} 話者「{w}」が characters.md にありません")
                continue
            sid = tu.get("id") or next((i for k, i in v["styles"].items() if k in ln["tone"]), v["id"])
            ids.append(sid)
            kw = {k: tu[k] for k in ("pitch", "intonation", "pause") if tu.get(k) is not None}
            auds.append(vv.synth(speak, sid, speed=tu.get("speed") or v["speed"], **kw))
        if not auds:
            continue
        n = max(len(a) for a in auds)
        mix = np.zeros(n, np.float32)
        for a in auds:
            mix[:len(a)] += a
        if len(auds) > 1:
            mix *= 0.75
        pre = tu.get("pre") or 0.0
        gap = tu.get("gap") if tu.get("gap") is not None else 0.6
        chunks += [np.zeros(int(pre * SR), np.float32), mix, np.zeros(int(gap * SR), np.float32)]
        q = json.loads(vv._post("/audio_query", {"text": speak, "speaker": ids[0]}))
        report.append(f"#{ln['no']}\t{ln['who']}\tID{','.join(map(str, ids))}\t{n / SR:.1f}秒\t"
                      f"{ln['text']}\n\t読み: {q.get('kana', '')}")

    audio = np.concatenate(chunks)
    peak = np.abs(audio).max()
    if peak > 0.95:
        audio *= 0.95 / peak
    mp3 = next_version(os.path.join(out_dir, f"{slug}_voice.mp3"))  # 例: shovel_voice_v3.mp3
    wav_path = mp3[:-4] + ".wav"
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((audio * 32767).astype(np.int16).tobytes())
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav_path, "-b:a", "160k", mp3], check=True)
    os.remove(wav_path)
    txt = mp3[:-4] + ".txt"  # 音声と同じ版の番号
    with open(txt, "w", encoding="utf-8") as f:
        f.write("\n".join(problems + report) + "\n")
    print(f"{len(report)} 台詞 / {len(audio) / SR:.1f} 秒 → {mp3}")
    print(f"読みの一覧 → {txt}")
    for p in problems:
        print("注意:", p)


if __name__ == "__main__":
    main()
