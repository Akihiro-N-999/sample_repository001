"""画像の生成をユーザーに頼むときの「依頼書」を作る。そのとき作る画像だけの指示文と、
その画像だけを名前付きで1つの ZIP にまとめさせる依頼文を、必ず入れる。

    python3 video/lib/image_request.py <エピソードのフォルダ> <依頼の名前> <指示文の番号> [<番号> ...]

例：
    python3 video/lib/image_request.py video/episodes/shovel G3_step1 1-1
    python3 video/lib/image_request.py video/episodes/shovel G3_step2 1-2 1-3 2-1 2-2 2-3 11

- 指示文の番号は、指示書（<エピソード>/image_prompts/*.md）の見出し「### 1-1. …」の先頭の番号。
- 出力：<エピソード>/image_prompts/requests/<依頼の名前>_v番号.md（上書きしない）。
- Gemini の会話ごとにまとめ、会話ごとに「ZIP の依頼文」（その会話で今回作る画像だけ）を置く。
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
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    ep, name, wanted = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3:]
    pdir = os.path.join(ep, "image_prompts")
    allitems = {}
    for f in sorted(os.listdir(pdir)):
        if f.endswith(".md") and not f.startswith("00_"):
            allitems.update(parse(os.path.join(pdir, f)))
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
           "各会話の最後に、その会話の「ZIP の依頼文」を貼って、今回作った画像を1つの ZIP にまとめてもらい、"
           "その ZIP をアップロードしてください（Gemini が ZIP を作れなかったときは、下の予備の方法で）。", ""]
    for gi, ((fname, conv), its) in enumerate(groups.items(), 1):
        out += ["---", "", f"## 会話{gi}：{conv}（指示書 `{fname}`）", "",
                "すでにこの会話を始めていれば、その続きで作ってください（絵柄がそろいやすくなります）。", ""]
        for no, it in its:
            out += [f"### {no}. {it['title']}", ""]
            if it["attach"]:
                out += [f"- 添付：{it['attach']}", ""]
            if "基準画像" in it["title"]:
                out += ["- **この1枚は2〜3案作って、いちばん良い1枚を選んでください。ZIP に入れるのは選んだ1枚だけです。**"
                        "（差分はこの1枚をもとに作るので、ここで顔と服を決めます）", ""]
            out += ["```", it["prompt"], "```", ""]
        out += [f"### この会話の ZIP の依頼文（今回の {len(its)} 枚）", "", "```",
                "この会話で作った画像のうち、次の画像を、それぞれ指定の名前を付けて、1つの ZIP ファイルにまとめ、"
                "ダウンロードできるようにしてください。画像の中身は変えず、名前だけを付けてください。"]
        out += [f"- {it['save']} ： {it['title']}" for _, it in its]
        out += ["```", ""]
    out += ["---", "", "## Gemini が ZIP を作れなかったときの予備",
            "画像を1枚ずつダウンロードし、**名前は変えずに**1つのフォルダに入れて、そのフォルダを ZIP にしてアップロードしてください。"
            "どの画像かは制作側が絵で見分けて名前を付けます。", ""]

    rdir = os.path.join(pdir, "requests")
    os.makedirs(rdir, exist_ok=True)
    path = next_version(os.path.join(rdir, f"{name}.md"))
    open(path, "w", encoding="utf-8").write("\n".join(out))
    print(f"[OK] {len(wanted)}枚・{len(groups)}会話 → {path}（指示書の全体は {len(allitems)}枚）")


if __name__ == "__main__":
    main()
