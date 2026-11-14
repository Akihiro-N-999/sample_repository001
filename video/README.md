# note記事 → 寸劇アニメ動画

note記事を題材に、VOICEVOXの声で掛け合う寸劇アニメ（1920×1080 / 30fps の MP4）を作ります。

## 準備（初回のみ）

```bash
pip install pycairo numpy
apt-get install -y fonts-noto-cjk ffmpeg
docker run -d --name vv -p 50021:50021 voicevox/voicevox_engine:cpu-latest
```

## 書き出し

```bash
python3 video/episodes/shovel/episode.py            # video/out/shovel_pilot.mp4
python3 video/episodes/shovel/episode.py --stills   # 確認用の静止画
```

- `video/lib/core.py`：音声合成・効果音・タイムライン・人物や字幕の描画・書き出し
- `video/episodes/<名前>/episode.py`：配役・台本（`build`）と場面の描画

## クレジット

VOICEVOXの音声を使う動画には、使った話者ごとに「VOICEVOX:話者名」を表記します（エンドカードに入れています）。

## 役割分担での制作（サブエージェント）

`/note-video <記事URL>` で、本体（オーケストレーター）が次の担当を順に動かします。手順は `.claude/skills/note-video/SKILL.md`、各担当の指示は `.claude/agents/` にあります。

| 役割 | エージェント | 成果物 |
|---|---|---|
| 企画 | video-planner | plan.md |
| 台本 | video-scriptwriter | script.md |
| キャラクター設定 | video-character-designer | characters.md |
| 校閲 | video-reviewer | review.md |
| アニメーション制作 | video-animator | episode.py・MP4 |

流れ：記事取得 → 企画 →（ユーザー確認）→ 台本とキャラ設定を並行 → 校閲 →（ユーザー確認）→ アニメーション制作 → 映像の校閲 → 納品
