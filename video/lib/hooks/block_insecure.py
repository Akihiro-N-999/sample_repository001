"""PreToolUse フック：証明書の検証を外す・プロキシを外す操作を、実行前に止める。

対象：
  - Bash のコマンド
  - Write / Edit で保存するスクリプト（.py .js .mjs .cjs .ts .sh）

止めたときは、safe-web-fetch スキル（video/lib/fetch_page.py）を使うよう伝える。
このファイル自身が止められないよう、検出する文字列は分割して組み立てている。
"""
import json
import re
import sys

J = "".join
PATTERNS = [
    (J([r"(^|\s)--", "inse", r"cure(\s|$)"]), "curl の安全でないオプション"),
    (J([r"\bcurl\b[^\n|;&]*\s-", r"[a-zA-Z]*k[a-zA-Z]*(\s|$)"]), "curl の -k（証明書の検証を外す）"),
    (J(["--no-check-", "certificate"]), "wget の証明書の検証を外すオプション"),
    (J(["ignore-certificate-", "errors"]), "ブラウザの証明書エラーを無視するオプション"),
    (J(["ignoreHTTPS", "Errors"]), "Playwright の証明書エラーを無視する設定"),
    (J([r"verify\s*=\s*", "False"]), "Python の証明書の検証を外す設定"),
    (J(["_create_unverified", "_context"]), "Python の検証しない SSL の設定"),
    (J([r"NODE_TLS_REJECT_", r"UNAUTHORIZED\s*=\s*['\"]?0"]), "Node.js の証明書の検証を外す設定"),
    (J([r"rejectUnauthorized\s*:\s*", "false"]), "Node.js の証明書の検証を外す設定"),
    (J([r"PYTHONHTTPS", r"VERIFY\s*=\s*0"]), "Python の証明書の検証を外す設定"),
    (J([r"sslVerify\s*(=|\s)\s*", "false"]), "git の証明書の検証を外す設定"),
    (J([r"\bunset\s+[^\n;&|]*\bHTTPS", "_PROXY"]), "プロキシの設定を外す操作"),
    (J([r"\bHTTPS_PROXY\s*=\s*(''|\"\"|\s|$)"]), "プロキシの設定を空にする操作"),
    (J(["--no", r"proxy\b"]), "プロキシを使わない設定"),
]
SCRIPT_EXT = (".py", ".js", ".mjs", ".cjs", ".ts", ".sh")

data = json.load(sys.stdin)
tool = data.get("tool_name", "")
inp = data.get("tool_input") or {}
if tool == "Bash":
    text = inp.get("command", "")
elif tool in ("Write", "Edit"):
    path = inp.get("file_path", "")
    if not path.endswith(SCRIPT_EXT):
        sys.exit(0)
    text = inp.get("content", "") if tool == "Write" else inp.get("new_string", "")
else:
    sys.exit(0)

hits = [label for pat, label in PATTERNS if re.search(pat, text)]
if hits:
    print("止めました：" + "、".join(sorted(set(hits))) + " が含まれています。\n"
          "証明書の検証を外す・プロキシを外す方法は使いません（このセッションの決まり）。\n"
          "→ Web ページは safe-web-fetch スキル（python3 video/lib/fetch_page.py <URL>）で取得してください。"
          "証明書のエラーは /root/.ccr/README.md の手順で CA（/root/.ccr/ca-bundle.crt）を指定して直し、"
          "許可されていないサイトは本体に許可の追加を頼むか、ユーザーにブラウザで確かめてもらってください。",
          file=sys.stderr)
    sys.exit(2)
sys.exit(0)
