"""画像の生成をユーザーに頼むときの「依頼書」を作る。そのとき作る画像だけの指示文と、
保存名（参考）を入れる。ZIP（アーカイブ）にまとめる指示はユーザー本人が Gemini に出すので、依頼書には書かない。

    python3 video/lib/image_request.py <エピソードのフォルダ> <依頼の名前> <指示文の番号> [<番号> ...]
        [--also <ほかの指示書.md>]   … シリーズ共通の人物の指示書。番号は「フォルダ名:番号」（例 akihiro:1-1）
        [--note <番号>=<注意書き>]   … その指示文の前に出す注意（作り直しの理由など）

例：
    python3 video/lib/image_request.py video/episodes/shovel G3_step1 1-1
    python3 video/lib/image_request.py video/episodes/shovel G3_step2 1-2 1-3 2-1 2-2 2-3 11

- 指示文の番号は、指示書（<エピソード>/image_prompts/*.md）の見出し「### 1-1. …」の先頭の番号。
- 出力：<エピソード>/image_prompts/requests/<依頼の名前>_v番号.md（上書きしない）。
- Gemini の会話ごとにまとめ、会話ごとに今回作る画像の保存名（参考）の一覧を置く。
- 足りない番号があれば止まる（終了コード 1）。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from core import next_version  # noqa: E402


def parse(path):
    """指示書を {番号: dict(title, save, attach, prompt)} にする。"""
    text = open(path, encoding="utf-8").read()
    conv = re.search(r"^## (会話.*)$", text, re.M)
    conv = conv.group(1).strip() if conv else os.path.basename(path)
    items = {}
    for m in re.finditer(r"^### (\S+?)\.\s*(.*?)\n(.*?)(?=^### |\Z)", text, re.M | re.S):
        no, title, body = m.group(1), m.group(2).strip(), m.group(3)
        save = re.search(r"保存名[^`\n]*`([^`]+)`", body)
        attach = re.search(r"^- 添付：(.*)$", body, re.M)
        prompt = re.search(r"- 指示文：\s*```\n(.*?)```", body, re.S)
        if save and prompt:
            items[no] = dict(title=title, save=save.group(1), attach=attach.group(1).strip() if attach else "",
                             prompt=prompt.group(1).rstrip(), conv=conv, file=os.path.basename(path))
    return items


def main():
    args = sys.argv[1:]
    also, notes, rest = [], {}, []
    i = 0
    while i < len(args):
        if args[i] == "--also":
            also.append(args[i + 1]); i += 2
        elif args[i] == "--note":
            k, v = args[i + 1].split("=", 1); notes[k] = v; i += 2
        else:
            rest.append(args[i]); i += 1
    if len(rest) < 3:
        raise SystemExit(__doc__)
    ep, name, wanted = rest[0].rstrip("/"), rest[1], rest[2:]
    pdir = os.path.join(ep, "image_prompts")
    allitems = {}
    for f in sorted(os.listdir(pdir)):
        if f.endswith(".md") and not f.startswith("00_"):
            allitems.update(parse(os.path.join(pdir, f)))
    for f in also:  # シリーズ共通の人物の指示書など。番号は「フォルダ名:番号」（例 akihiro:1-1）
        prefix = os.path.basename(os.path.dirname(os.path.abspath(f)))
        for k, v in parse(f).items():
            v["file"] = os.path.relpath(f)
            allitems[f"{prefix}:{k}"] = v
    missing = [w for w in wanted if w not in allitems]
    if missing:
        raise SystemExit(f"[NG] 指示書に見つからない番号: {missing}（見出し「### 番号. …」と、保存名・指示文の書き方を確かめる）")

    groups = {}
    for w in wanted:
        it = allitems[w]
        groups.setdefault((it["file"], it["conv"]), []).append((w, it))

    out = [f"# 画像の依頼：{name}", "",
           f"今回作るのは **{len(wanted)}枚** です。会話ごとに、上から順に指示文を1つずつ貼ってください。",
           "**どの指示文にも、アキヒロの基準画像（akihiro_base_v2.png）を画風の参考として添付してください。**",
           "**Gemini の設定：モデルは 4 Hydrogen、思考レベルは「標準」。**（「高」はすぐに1日の上限に達します）", "",
           "できた画像はアップロードしてください。各会話の最後に、保存名（参考）の一覧があります。", ""]
    for gi, ((fname, conv), its) in enumerate(groups.items(), 1):
        out += ["---", "", f"## 会話{gi}：{conv}（指示書 `{fname}`）", "",
                "すでにこの会話を始めていれば、その続きで作ってください（絵柄がそろいやすくなります）。", ""]
        for no, it in its:
            out += [f"### {no}. {it['title']}", "", f"- **ダウンロード後のファイル名：`{it['save']}`**", ""]
            if it["attach"]:
                out += [f"- 添付：{it['attach']}", ""]
            if no in notes:
                out += [f"- **{notes[no]}**", ""]
            if "基準画像" in it["title"]:
                out += ["- **この1枚は2〜3案作って、いちばん良い1枚を選んでください。送るのは選んだ1枚だけです。**"
                        "（差分はこの1枚をもとに作るので、ここで顔と服を決めます）", ""]
            # 指示文の最後にもファイル名を入れる（Gemini が画像に名前を付けられるように。ユーザーの指示 2026-11-17）
            out += ["```", it["prompt"], "", f"できた画像のファイル名は「{it['save']}」にしてください。", "```", ""]
        out += [f"### この会話の保存名（参考。今回の {len(its)} 枚）", ""]
        out += [f"- {it['save']} ： {it['title']}" for _, it in its]
        out += [""]

    # 添付する画像を集めて ZIP にする（ユーザーが探さずに済むように。2026-11-18 のユーザーの希望）
    # 名前が完全に一致する画像、なければ同じ名前の最新の版を、指示文に書いてある名前で入れる。
    root = os.path.normpath(os.path.join(HERE, ".."))
    pool = {}
    for d in [os.path.join(root, "assets", "images"), os.path.join(root, "characters")]:
        for r, _, fs in os.walk(d):
            for fn in fs:
                if fn.lower().endswith((".png", ".jpg")):
                    pool.setdefault(fn, os.path.join(r, fn))
    def find(nm):
        if nm in pool:
            return pool[nm]
        stem = re.sub(r"_v\d+\.(png|jpg)$", "", nm)
        cands = [(int(m.group(1)), path) for fn, path in pool.items()
                 for m in [re.match(re.escape(stem) + r"_v(\d+)\.(?:png|jpg)$", fn)] if m]
        return max(cands)[1] if cands else None
    attach_names = []
    for w in wanted:
        for nm in re.findall(r"`([^`]+\.(?:png|jpg))`", allitems[w]["attach"]):
            if nm not in attach_names:
                attach_names.append(nm)
    made = {allitems[w]["save"] for w in wanted}
    have = {nm: find(nm) for nm in attach_names if nm not in made}
    have = {k: v for k, v in have.items() if v}
    missing_att = [nm for nm in attach_names if nm not in have]
    out += ["---", "", "## 添付する画像", ""]
    if have:
        out += ["次の画像は、添付用の画像の ZIP にまとめてお送りします（名前は指示文のとおり）。", ""]
        out += [f"- `{nm}`" for nm in have]
        out += [""]
    if missing_att:
        out += ["次の画像は ZIP に入っていません。この依頼の中で作る画像か、まだ届いていない画像です。", ""]
        out += [f"- `{nm}`" + ("（この依頼の中で作ります）" if nm in made else "") for nm in missing_att]
        out += [""]

    rdir = os.path.join(pdir, "requests")
    os.makedirs(rdir, exist_ok=True)
    path = next_version(os.path.join(rdir, f"{name}.md"))
    open(path, "w", encoding="utf-8").write("\n".join(out))
    if have:
        import zipfile
        zdir = os.path.join(root, "out", "requests")
        os.makedirs(zdir, exist_ok=True)
        zpath = next_version(os.path.join(zdir, f"{name}_添付.zip"))
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for nm, src in have.items():
                z.write(src, nm)
        print(f"[OK] 添付用の画像 {len(have)}枚 → {zpath}")
    print(f"[OK] {len(wanted)}枚・{len(groups)}会話 → {path}（指示書の全体は {len(allitems)}枚）")


if __name__ == "__main__":
    main()
