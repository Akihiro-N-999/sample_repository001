"""Web ページの本文を、安全な方法で取得する（証明書の検証は外さない）。

    python3 video/lib/fetch_page.py <URL> [出力ファイル.txt]

手順：
  1. curl で取得する（この環境のプロキシと CA の設定をそのまま使う）。
  2. 本文が短すぎる（JavaScript で中身を描くページ）ときは、ヘッドレスのブラウザ（Playwright の
     Chromium）で表示して本文を取る。プロキシは HTTPS_PROXY を指定するだけ。この環境では
     ブラウザの信頼済み証明書（NSS）にプロキシの CA が登録済みなので、検証を外す必要はない。
  3. 失敗したら、原因と正しい対処を表示して止まる。次のことはしない：
     - 証明書の検証を無効にする（curl の安全でないオプション、ブラウザの証明書エラー無視など）
     - プロキシの設定を外す・迂回する
     - 403/407（許可されていないサイト）を別の経路で取りにいく

終了コード：0 = 取得できた、2 = 許可されていないサイト、3 = 証明書のエラー、4 = その他の失敗。
"""
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse

MIN_TEXT = 400  # これより短ければ、JavaScript で描くページとみなしてブラウザで表示する
README = "/root/.ccr/README.md"


def to_text(s):
    s = re.sub(r"<script.*?</script>|<style.*?</style>|<noscript.*?</noscript>", "", s, flags=re.S | re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", s))
    return re.sub(r"\n\s*\n+", "\n", t).strip()


def proxy_reason():
    """プロキシの状態から、直近の失敗の理由を取る（取れなければ空）。"""
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""
    if not proxy:
        return ""
    try:
        r = subprocess.run(["curl", "-sS", "-m", "5", proxy.rstrip("/") + "/__agentproxy/status"],
                           capture_output=True, text=True)
        return r.stdout[-1500:]
    except Exception:  # noqa: BLE001
        return ""


def fail(code, msg, host):
    advice = {
        2: f"サイト {host} はこのセッションのネットワーク設定で許可されていない。別の経路で取りにいかず、"
           "オーケストレーター（本体）に許可の追加を頼む（get_environment → update_environment）。"
           "許可できない場合は、ユーザーにブラウザで開いて確かめてもらう。",
        3: "証明書の検証で失敗した。検証を外さないこと。/root/.ccr/README.md の「certificate verify failed」の節に"
           "従い、ツールに CA（/root/.ccr/ca-bundle.crt）を指定する。それでも読めなければ、ユーザーにブラウザで"
           "開いて確かめてもらう。",
        4: "取得に失敗した。リダイレクト先のサイトが許可されていない、サイトの障害（503 など）、"
           "ブラウザでしか読めない作り、などが考えられる。時間をおいて1回だけ再試行し、"
           "だめならユーザーにブラウザで開いて確かめてもらう。",
    }[code]
    print(f"[失敗] {msg}\n→ {advice}", file=sys.stderr)
    sys.exit(code)


def curl(url):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as f:
        path = f.name
    r = subprocess.run(["curl", "-sSL", "-m", "30", "-A", "Mozilla/5.0", "-o", path, "-w", "%{http_code}", url],
                       capture_output=True, text=True)
    code = r.stdout.strip()
    body = open(path, encoding="utf-8", errors="ignore").read() if os.path.exists(path) else ""
    os.unlink(path)
    return r.returncode, code, r.stderr, body


def browser(url):
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    js = """
const {chromium}=require('playwright');
(async()=>{
  const url=process.argv[2], proxy=process.argv[3];
  const b=await chromium.launch(proxy?{proxy:{server:proxy}}:{});
  const p=await b.newPage();
  try{
    const res=await p.goto(url,{waitUntil:'networkidle',timeout:45000});
    await p.waitForTimeout(1500);
    const text=await p.evaluate(()=>document.body?document.body.innerText:'');
    console.log(JSON.stringify({status:res?res.status():0,text}));
  }catch(e){console.log(JSON.stringify({error:String(e.message||e)}));}
  await b.close();
})();
"""
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".js") as f:
        f.write(js)
        path = f.name
    r = subprocess.run(["node", path, url, proxy or ""], capture_output=True, text=True, timeout=120)
    os.unlink(path)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        return {"error": (r.stderr or r.stdout)[-800:]}


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    url = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else None
    host = urllib.parse.urlparse(url).hostname or url

    rc, code, err, body = curl(url)
    if "CONNECT tunnel failed" in err or code in ("403", "407"):
        fail(2, f"curl: {err.strip() or code}\n{proxy_reason()}", host)
    if "certificate" in err.lower() or "ssl" in err.lower():
        fail(3, f"curl: {err.strip()}", host)
    text = to_text(body) if rc == 0 and code.startswith("2") else ""
    how = "curl"
    if len(text) < MIN_TEXT:
        res = browser(url)
        if res.get("error"):
            e = res["error"]
            if "ERR_TUNNEL_CONNECTION_FAILED" in e or "403" in e:
                fail(2, f"ブラウザ: {e}\n{proxy_reason()}", host)
            if "CERT" in e.upper():
                fail(3, f"ブラウザ: {e}", host)
            fail(4, f"curl: HTTP {code}、本文 {len(text)} 字／ブラウザ: {e}", host)
        text = (res.get("text") or "").strip()
        how = f"ブラウザ（HTTP {res.get('status')}）"
        if len(text) < 50:
            fail(4, f"ブラウザで表示しても本文がほとんどない（HTTP {res.get('status')}、{len(text)} 字）", host)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(f"# {url}\n# 取得方法: {how}\n\n{text}\n")
        print(f"[OK] {how}で取得、{len(text)} 字 → {out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
