// タグ用ケース(本体 + 摩擦嵌合フタの 2 部品)
// 内部レイアウト(長手方向): LiPo バッテリー | M5Stamp C5 | Stamp UWB F
// - UWB F のアンテナ端はケース端の開口(アンテナ窓)に向き、樹脂で覆わない
// - C5 の USB-C は側壁のスロットから充電・書き込み可能
// - 各ボードは背面 FPC コネクタが床の溝に収まる向き(部品面を上)で置く
// - バッテリー端には ストラップループ
// 印刷: 本体は底面、フタは天面をベッドに向ける(どちらもサポート不要)
// part = "body" | "lid" | "preview"(本体 + 浮かせたフタ)

include <common.scad>

part = "preview";

bat = [25, 36, 6.5];  // LiPo 公称 [幅, 長さ, 厚み](例: 602535 500 mAh)。要実測調整

wall = 2;       // 側壁厚
floor_t = 2.4;  // 底厚
cavity_d = 9;   // 内寸深さ
rib = 2;        // 仕切り壁厚
rail_h = 4;     // 仕切り・レール高さ
chan_d = 1.4;   // 床の FPC/配線溝の深さ
lid_t = 2;      // フタ厚
skirt_h = 2.2;  // フタのスカート(嵌合部)高さ
win_w = 14;     // アンテナ窓の幅

iw = bat[0] + 2 * tol;                  // 内寸幅(バッテリー幅で決まる)
bat_l  = bat[1] + 2 * tol;
c5_zone  = c5_w + 2 * tol;              // C5 は長辺(19.1)を幅方向に置く → USB-C が側壁を向く
uwb_zone = uwb_l + 2 * tol;
il = bat_l + rib + c5_zone + rib + uwb_zone;  // 内寸長さ
ol = il + 2 * wall;
ow = iw + 2 * wall;
oh = floor_t + cavity_d;

c5_y0  = bat_l + rib;                   // C5 ゾーン開始 y(内寸座標)
uwb_y0 = c5_y0 + c5_zone + rib;

module rounded_box(size, r = 2) {
    hull() for (x = [r, size[0] - r], y = [r, size[1] - r])
        translate([x, y, 0]) cylinder(r = r, h = size[2]);
}

// 原点: 内寸の左下(x は中央揃えでなく壁内側)。外形は [-wall, -wall] から
module body() {
    difference() {
        union() {
            translate([-wall, -wall, 0]) rounded_box([ow, ol, oh]);
            // ストラップループ(バッテリー端の外側)
            translate([iw / 2 - 7, -wall - 8, 0]) loop_bar();
        }
        // キャビティ
        translate([0, 0, floor_t]) cube([iw, il, cavity_d + 0.1]);
        // 床の FPC/配線溝(C5 ゾーン中央から UWB 端まで)
        translate([iw / 2 - fpc_w / 2, c5_y0 - rib - 6, floor_t - chan_d])
            cube([fpc_w, il - (c5_y0 - rib - 6) + 0.1, chan_d + 0.1]);
        // USB-C スロット(+x 側壁、C5 ゾーン)
        translate([iw - 0.1, c5_y0 + (c5_zone - 11) / 2, floor_t])
            cube([wall + 0.2, 11, cavity_d + 0.1]);
        // アンテナ窓(UWB 端の壁を全高で開口)
        translate([iw / 2 - win_w / 2, il - 0.1, floor_t])
            cube([win_w, wall + 0.2, cavity_d + 0.1]);
    }
    // 仕切り(側方スタブのみ。中央はバッテリー配線 / FPC の通り道)
    divider(bat_l, gap = 10);
    divider(c5_y0 + c5_zone, gap = fpc_w + 1);
    // C5 センタリングレール(内寸幅 25.6 → C5 ポケット 19.7)
    rails(c5_y0, c5_zone, (iw - (c5_l + 2 * tol)) / 2);
    // UWB センタリングレール(→ ポケット 12.1)
    rails(uwb_y0, uwb_zone, (iw - (uwb_w + 2 * tol)) / 2);
}

module divider(y0, gap) {
    for (sx = [0, 1])
        translate([sx == 0 ? 0 : iw / 2 + gap / 2, y0, floor_t])
            cube([iw / 2 - gap / 2, rib, rail_h]);
}

module rails(y0, len, w) {
    for (sx = [0, 1])
        translate([sx == 0 ? 0 : iw - w, y0, floor_t])
            cube([w, len, rail_h]);
}

module loop_bar() {
    difference() {
        rounded_box([14, 9, 4], r = 2);
        translate([3, 2.5, -0.1]) rounded_box([8, 4, 4.2], r = 1.5);
    }
}

module lid() {
    difference() {
        union() {
            translate([-wall, -wall, oh]) rounded_box([ow, ol, lid_t]);
            // スカート(キャビティに摩擦嵌合)
            translate([0, 0, oh - skirt_h]) difference() {
                translate([tol, tol, 0]) cube([iw - 2 * tol, il - 2 * tol, skirt_h]);
                translate([tol + 1.2, tol + 1.2, -0.1]) cube([iw - 2 * tol - 2.4, il - 2 * tol - 2.4, skirt_h + 0.2]);
            }
        }
        // アンテナ窓(UWB アンテナ上面を開放。端の壁開口とつながる)
        translate([iw / 2 - win_w / 2, uwb_y0 + 3, oh - skirt_h - 0.1])
            cube([win_w, il - (uwb_y0 + 3) + wall + 0.1, skirt_h + lid_t + 0.2]);
        // USB スロット上の逃げ(フタを閉めたままケーブルを挿せる)
        translate([iw - 0.1, c5_y0 + (c5_zone - 11) / 2, oh - skirt_h - 0.1])
            cube([wall + 0.2, 11, skirt_h + 0.1]);
    }
}

if (part == "body") body();
else if (part == "lid") lid();
else {
    body();
    translate([0, 0, 14]) lid();
}
