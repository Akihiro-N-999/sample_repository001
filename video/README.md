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

| 役割 | エージェント | モデル | 成果物 |
|---|---|---|---|
| 企画 | video-planner | Opus | plan.md |
| 台本 | video-scriptwriter | Opus | script.md |
| キャラクター設定 | video-character-designer | Sonnet | characters.md |
| 校閲 | video-reviewer | Opus（映像の校閲は Sonnet） | review.md |
| アニメーション制作 | video-animator | Sonnet | episode.py・MP4 |

流れと人の確認（ゲート）：

```
記事取得 → 企画 → [G1 企画]
  → 台本 ∥ キャラ設定 → 校閲 → 音声プレビュー → [G2 台本と声]   ← ここで台本を確定
  → 見本1場面 → [G3 見本場面]
  → 全体制作 → 映像の校閲 → [G4 公開前] → コミット
```

台詞だけを先に音声で聞く：

```bash
python3 video/lib/voice_preview.py video/episodes/<slug>
```
