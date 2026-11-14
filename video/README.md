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
