"""ゲート（人の確認）に出す前の機械的な検査。手順書や STYLE.md の決まりのうち、
文章で書いただけでは見落とされやすいものを、ここで確かめる。

    python3 video/lib/gate_check.py G1 video/episodes/<slug>
    python3 video/lib/gate_check.py G2 video/episodes/<slug>
    python3 video/lib/gate_check.py G3 video/episodes/<slug>
    python3 video/lib/gate_check.py G4 video/episodes/<slug>

[NG] が1つでもあれば終了コード 1。NG を直すか、直さない理由をユーザーに伝えてからゲートに出す。
[注意] は人に伝えるべき点（ゲートには出してよい）。
"""
import glob
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from core import latest  # noqa: E402

MIN_SEC, MAX_SEC = 510, 600  # 8分30秒〜10分（video/STYLE.md）
OUT = os.path.join(HERE, "..", "out")
rows = []


def ok(msg):
    rows.append(("OK", msg))


def ng(msg):
    rows.append(("NG", msg))


def warn(msg):
    rows.append(("注意", msg))


def read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else None


def git_clean():
    r = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if r.stdout.strip():
        warn("未コミットの変更がある：作業途中でもコミット・プッシュしてからゲートに出す\n        "
             + r.stdout.strip().replace("\n", "\n        "))
    else:
        ok("未コミットの変更なし")


def versions_copy(ep, name):
    """作業用の md と同じ中身の写しが versions/ にあるか（渡す md は写しで渡す決まり）。"""
    src = os.path.join(ep, name + ".md")
    if not os.path.exists(src):
        return
    vs = sorted(glob.glob(os.path.join(ep, "versions", name + "_v*.md")),
                key=lambda p: int(re.search(r"_v(\d+)\.md$", p).group(1)))
    if vs and open(vs[-1], "rb").read() == open(src, "rb").read():
        ok(f"{name}.md の写しが最新（{os.path.basename(vs[-1])}）")
    else:
        ng(f"{name}.md の番号付きの写しがない／古い：python3 video/lib/handoff.py {src}")


def plan_total_seconds(plan):
    m = re.search(r"\|\s*\*\*合計\*\*.*?\*\*(\d+)秒", plan)
    return int(m.group(1)) if m else None


def g1(ep):
    plan = read(os.path.join(ep, "plan.md"))
    if plan is None:
        return ng("plan.md がない")
    sec = plan_total_seconds(plan)
    if sec is None:
        ng("plan.md の尺の見積もりに「**合計**」の行（**○○秒**）が見つからない")
    elif sec < MIN_SEC:
        ng(f"尺の見積もりが {sec} 秒で、標準の 8分30秒（{MIN_SEC}秒）に足りない")
    elif sec > MAX_SEC:
        warn(f"尺の見積もりが {sec} 秒で、10分を超える")
    else:
        ok(f"尺の見積もり {sec} 秒（{sec // 60}分{sec % 60:02d}秒）")
    for key, label in (("つかみ", "冒頭のつかみ"), ("仮タイトル", "仮タイトル"), ("サムネイル", "サムネイルの方向"),
                       ("校閲への申し送り", "校閲への申し送り")):
        (ok if key in plan else ng)(f"plan.md に「{label}」がある" if key in plan else f"plan.md に「{label}」がない")
    rc = read(os.path.join(ep, "review_content.md"))
    if rc and "台本で言える範囲" in rc:
        ok("事実確認（review_content.md の「台本で言える範囲」）が済んでいる")
    else:
        ng("事実確認が済んでいない：企画の前に内容校閲担当に事実確認をさせる（教訓）")
    if os.path.exists(os.path.join(ep, "research.md")):
        ok("research.md がある")
    else:
        warn("research.md がない（リサーチ担当を動かしていない）")
    versions_copy(ep, "plan")


def g2(ep):
    script = os.path.join(ep, "script.md")
    chars = os.path.join(ep, "characters.md")
    if not os.path.exists(script) or not os.path.exists(chars):
        return ng("script.md か characters.md がない")
    from voice_preview import load_lines, load_voices
    try:
        voices = load_voices(chars)
        lines = load_lines(script)
    except SystemExit as e:
        return ng(str(e))
    speakers = {w for ln in lines for w in ln["who"].replace(" ", "").split("+")}
    missing = speakers - set(voices)
    (ng(f"声の割り当てがない話者: {sorted(missing)}") if missing else ok("台本の話者すべてに声の割り当てがある"))
    # 文の途中での分割・改行などの機械チェック（audio_check voice の ✗）
    slug = os.path.basename(ep.rstrip("/"))
    r = subprocess.run([sys.executable, os.path.join(HERE, "audio_check.py"), "voice", ep],
                       capture_output=True, text=True)
    m = re.search(r"✗ (\d+) 件", r.stdout)
    if m is None:
        ng("audio_check voice が実行できない（VOICEVOX が動いているか video/lib/env_check.py で確かめる）\n        "
           + (r.stderr.strip().splitlines() or [""])[-1])
    elif int(m.group(1)) > 0:
        ng(f"台詞の機械チェックで ✗ {m.group(1)} 件：video/out/{slug}_check_voice.md")
    else:
        ok("台詞の機械チェック ✗ 0 件")
    # 音声プレビューが台本より新しいか
    mp3 = latest(os.path.join(OUT, f"{slug}_voice.mp3"))
    if not os.path.exists(mp3):
        ng("音声プレビューがない：python3 video/lib/voice_preview.py " + ep)
    else:
        newer = os.path.getmtime(mp3) >= max(os.path.getmtime(script), os.path.getmtime(chars),
                                            os.path.getmtime(os.path.join(ep, "sound.md"))
                                            if os.path.exists(os.path.join(ep, "sound.md")) else 0)
        (ok(f"音声プレビューが最新（{os.path.basename(mp3)}）") if newer
         else ng("音声プレビューが台本・キャラ設定・sound.md より古い：作り直す"))
        txt = mp3[:-4] + ".txt"
        if os.path.exists(txt):
            secs = sum(float(x) for x in re.findall(r"\t([0-9.]+)秒\t", open(txt, encoding="utf-8").read()))
            est = secs + 0.3 * len(lines) + 30  # 台詞の間と場面の切り替えのおおよそ
            (ok if est >= MIN_SEC else ng)(f"実測からの尺の見込み 約{int(est)}秒（台詞のみ {int(secs)}秒）")
    for name, label in (("review_content.md", "内容校閲"), ("review_quality.md", "品質校閲"), ("sound.md", "声の演出")):
        (ok if os.path.exists(os.path.join(ep, name)) else ng)(
            f"{label}（{name}）がある" if os.path.exists(os.path.join(ep, name)) else f"{label}（{name}）がない")
    for name in ("script", "characters"):
        versions_copy(ep, name)


def g3(ep):
    slug = os.path.basename(ep.rstrip("/"))
    sample = latest(os.path.join(OUT, f"{slug}_sample.mp4"))
    (ok(f"見本の動画がある（{os.path.basename(sample)}）") if os.path.exists(sample)
     else ng(f"見本の動画 video/out/{slug}_sample_v番号.mp4 がない"))
    rq = read(os.path.join(ep, "review_quality.md")) or ""
    (ok if "見本" in rq else warn)("品質校閲が見本場面を見ている" if "見本" in rq else "品質校閲の記録に見本場面の確認が見当たらない")


def g4(ep):
    slug = os.path.basename(ep.rstrip("/"))
    mp4 = latest(os.path.join(OUT, f"{slug}.mp4"))
    if not os.path.exists(mp4):
        return ng(f"完成動画 video/out/{slug}_v番号.mp4 がない")
    ok(f"完成動画 {os.path.basename(mp4)}")
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp4],
                       capture_output=True, text=True)
    dur = float(r.stdout.strip() or 0)
    (ok if MIN_SEC <= dur <= MAX_SEC + 30 else ng)(f"動画の長さ {int(dur)}秒")
    r = subprocess.run([sys.executable, os.path.join(HERE, "audio_check.py"), "mix", ep, "--mp4", mp4],
                       capture_output=True, text=True)
    m = re.search(r"✗ (\d+) 件", r.stdout)
    (ok("完成音声の機械チェック ✗ 0 件") if m and m.group(1) == "0"
     else ng(f"完成音声の機械チェックで問題：video/out/{slug}_check_mix.md"))
    pub = read(os.path.join(ep, "publish.md")) or ""
    for key in ("タイトル", "サムネイル", "説明欄", "チャプター", "タグ", "字幕", "投稿設定"):
        (ok if key in pub else ng)(f"publish.md に「{key}」" + ("がある" if key in pub else "がない"))
    if "VOICEVOX:" not in pub:
        ng("説明欄に VOICEVOX のクレジットがない")
    srt = latest(os.path.join(OUT, f"{slug}.srt"))
    (ok if os.path.exists(srt) else ng)("字幕ファイルがある" if os.path.exists(srt) else "字幕ファイルがない")
    versions_copy(ep, "publish")


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("G1", "G2", "G3", "G4"):
        raise SystemExit(__doc__)
    gate, ep = sys.argv[1], sys.argv[2].rstrip("/")
    {"G1": g1, "G2": g2, "G3": g3, "G4": g4}[gate](ep)
    git_clean()
    print(f"# {gate} の前の検査：{ep}")
    for k, m in rows:
        print(f"[{k}] {m}")
    n = sum(k == "NG" for k, _ in rows)
    print(f"\nNG: {n} 件" + ("（直すか、直さない理由をユーザーに伝えてからゲートに出す）" if n else ""))
    sys.exit(1 if n else 0)


if __name__ == "__main__":
    main()
