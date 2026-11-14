---
name: video-env
description: 動画制作の環境（VOICEVOX、Docker、フォント、ffmpeg、素材）を確かめて起動する。note-video の工程を始めるとき、セッションを再開したとき、音声の合成や書き出しが失敗したときに必ず使う。
---

# 制作環境の確認と起動

1. `python3 video/lib/env_check.py` を実行する。
2. [NG] があれば、表示された直し方に従う。特に：
   - **Docker デーモンが止まっている**：Bash の `run_in_background: true` で `dockerd` を起動する（通常の Bash で起動すると、コマンドの終了と一緒に止まる）。数秒待って `docker info` で確かめる。
   - **VOICEVOX が止まっている**：`docker start vv`（コンテナがなければ表示された `docker run` のコマンド）。起動に1分ほどかかる。
   - **素材がない**（セッションが新しくなり、リポジトリ外の素材が消えた）：ユーザーにアップロードしてもらい、`video-intake` で取り込む。
   - **Bash の run_in_background には時間の上限（最大2時間）がある**。上限で止まったら通知が来るので、作業がまだ続くなら同じ方法で起動し直す（timeout は最大の 7200000 を指定）。
3. もう一度 `python3 video/lib/env_check.py` を実行し、[NG] が0件になったことを確かめてから作業に入る。

やってはいけないこと：証明書の検証を無効にする（`-k`、`--ignore-certificate-errors` など）、プロキシの設定を外す。
