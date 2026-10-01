# 3D CADモデル(アンカー取付具・タグ用ケース)

[docs/hardware.md](../../docs/hardware.md)のハードウェアリストにある「アンカー取付具」「タグ用ケース」の3Dプリント用モデル。OpenSCADのパラメトリックソースと、書き出し済みSTLを置いている。

> **注意**: ボード寸法・背面FPCコネクタ/IPEXの位置は公式ドキュメントの寸法図([Stamp-C5 DIP](https://docs.m5stack.com/en/core/Stamp-C5_DIP) / [Stamp UWB F](https://docs.m5stack.com/en/stamp/stamp_uwb_f)の Model Size)から読み取った値(C5: 17.6×19.06×3.36 mm、うちUSB-C突き出し1.06 mm / UWB F: 幅12.02×長さ11.53×2.82 mm)。**実機でのフィット確認は未実施**。C5はDIP版付属のピンヘッダを**はんだ付けしない**前提(付けると収まらない)。印刷後に合わなければ`common.scad`の`tol`(片側クリアランス)や各パラメータを調整すること。

## ファイル

| ファイル | 内容 |
|---|---|
| `common.scad` | ボード公称寸法・公差などの共通パラメータ |
| `anchor_mount.scad` | アンカー取付具(壁面・柱用Lブラケット) |
| `tag_case.scad` | タグ用ケース(本体 + フタ。`part`で切替) |
| `stl/*.stl` | 書き出し済みSTL(`anchor_mount` / `tag_case_body` / `tag_case_lid`) |
| `Makefile` | STLとdocs用プレビューPNGの再生成 |

## 設計の要点

**アンカー取付具**(`anchor_mount.scad`)

![アンカー取付具3Dモデル](../../docs/assets/cad-anchor-mount.png)

- 垂直プレートを皿ネジM3×3本で壁・柱に固定。プレート前面のポケットにC5、上部棚の上面ポケットにUWB Fを置く(固定は薄手の両面テープを想定)
- アンカーはWi-Fiを使わないため、C5付属のWi-Fiアンテナは取り付けなくてよい(取付具にも収納場所はない)
- UWB Fの**アンテナ端は棚の前縁(壁と反対側)を向き、周囲に樹脂・壁が無い**(基本設計 §3.3の「金属・壁から離して突き出す」要求に対応)
- FPCはプレート前面の溝 → 棚のスリット経由で両ボードの背面コネクタへ(ボードは部品面が表)
- USB給電ケーブルは下方へ引き出し、ケーブルタイ用スリットで張力止め

**タグ用ケース**(`tag_case.scad`)

![タグ用ケース3Dモデル(本体とフタ)](../../docs/assets/cad-tag-case.png)

- 内部は長手方向にLiPo | C5 | FPC折り返し部 | UWB F。両ボードとも部品面を上にして置き、背面FPCコネクタは床の凹みに収まる
- C5はUSB-Cを+x側壁に突き当てて置く(VBAT/GNDパッドの列がバッテリー側を向く)。C5の背面FPCコネクタはUSB-Cと反対の端寄りにあり、ケーブルはその端へ出るため、-x側の空きで立ち上げてC5の上を渡し、折り返し部で床に下ろしてUWB Fのコネクタへ差す
- UWB F側の床溝はアンテナ部の下まで延ばさない(公式の注意: FPCをPCBアンテナの下に通さない)
- UWB Fの**アンテナ端はケース端・フタの開口(アンテナ窓)で樹脂に覆われない**
- C5のUSB-Cは側壁スロットから充電・書き込み可能。バッテリー端にストラップループ
- C5同梱のWi-Fi用FPCアンテナ(14.3×5.3 mm、IPEX-1)は**フタ裏の凹み(C5の上、+x寄り)に貼る**。C5の上を渡るFPCケーブル・UWB F・LiPoから離して配置し、ケーブル(50 mm)はキャビティ内で余らせる
- フタはスカートによる摩擦嵌合。LiPo寸法は`bat`パラメータ(既定25.5×37×5.2 mm = [docs/hardware.md](../../docs/hardware.md) §1.4の候補例 DPTL-DTP502535 400 mAh)で変更

## 印刷設定の目安

- PLA / PETG、レイヤー0.2 mm、インフィル20% 程度
- 向き: 取付具は背面(壁側)をベッドへ、ケース本体は底面、フタは天面をベッドへ → **いずれもサポート不要**

## 再生成

macOSで[OpenSCAD](https://openscad.org/)をインストール(`brew install --cask openscad`)して:

```bash
cd hardware/cad
make          # stl/ と docs/assets/cad-*.png を再生成
# OpenSCAD のパスが違う場合: make OPENSCAD=/path/to/OpenSCAD
```
