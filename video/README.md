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
| 音声・BGM | video-sound-designer | Sonnet | sound.md |
| 内容校閲（何を言っているか・言ってよいか） | video-content-reviewer | Opus | review_content.md |
| 品質校閲（どう聞こえるか・見えるか・台本どおりか） | video-quality-reviewer | Sonnet | review_quality.md |
| アニメーション制作 | video-animator | Sonnet | episode.py・MP4 |

流れと人の確認（ゲート）：

```
記事取得 → 企画 → [G1 企画]
  → 台本 ∥ キャラ設定 → 内容校閲 → 声の演出 → 音声プレビュー → 品質校閲 → [G2 台本と声]   ← ここで台本を確定
  → 効果音・BGM → 内容校閲（音源の権利）→ 見本1場面 → 品質校閲 → [G3 見本場面]
  → 全体制作 → 品質校閲 → 内容校閲（クレジット・説明欄）→ [G4 公開前] → コミット
```

台詞だけを先に音声で聞く：

```bash
python3 video/lib/voice_preview.py video/episodes/<slug>
```

## 読み上げと字幕

- 台本の1行は1回の合成で読み上げます。字幕の改行やページの切り替えは表示だけで行い、読み上げを途中で切りません。
- 長い台詞の字幕は、話している時間を文字数の割合で配分してページを切り替えます。行は読点・句点の位置で折り、行頭に「、」「。」などが来ないようにしています。

## BGM・効果音

- 音源は `video/assets/bgm/` と `video/assets/se/` に置きます（リポジトリには入れません。出どころと利用条件は sound.md に記録します）。
- BGMは台詞の間だけ自動で音量が下がり、書き出し時に全体の音量を YouTube の基準（約 -14 LUFS）にそろえます。

## 品質チェック（品質校閲が使う）

```bash
python3 video/lib/audio_check.py voice video/episodes/<slug>                                 # 台詞の音声（G2 の前）
python3 video/lib/audio_check.py mix video/episodes/<slug> --mp4 video/out/<slug>.mp4      # 完成音声と実装（G4 の前）
```

文の途中での行の分け方、数字・英字の読み、台詞の長さと速さ、台詞中の無音、音割れ、台本と実装の一致、台詞の重なり、声とBGM・効果音の音量差、字幕のページ送り、MP4の音量を測り、`video/out/<slug>_check_*.md` に書き出します。

## ファイル名と画像の受け取り

- 生成する画像・動画・音声は `名前_v番号` で保存し、上書きしません。プログラムは最新の版を使います（詳しくは `video/STYLE.md`）。
- Gemini の画像は、名前を変えずに ZIP でアップロードしてもらい、受け取る側で名前を付けます。

```bash
python3 video/lib/intake.py list <ZIP>                                   # 番号付きの一覧画像と対応表のひな形
python3 video/lib/intake.py apply video/out/intake/<日時>/mapping.json   # 対応表どおり 名前_v番号 で保存
```
