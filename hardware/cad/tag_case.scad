// タグ用ケース(本体 + 摩擦嵌合フタの 2 部品)
// 内部レイアウト(長手方向 +y): LiPo バッテリー | M5Stamp C5 | FPC 折り返し部 | Stamp UWB F
// - 両ボードとも部品面を上にして置く。背面 FPC コネクタは床の凹みに収まる
// - C5 は USB-C を +x 側壁に突き当て(側壁スロットから充電・書き込み)、VBAT/GND パッドの列が
//   バッテリー側を向く。背面 FPC コネクタのケーブルは -x 端へ出るので、-x 側の空きで立ち上げて
//   C5 の上を +y へ渡し、折り返し部で床に下ろして UWB F のコネクタへ差す
// - UWB F のアンテナ端はケース端の開口(アンテナ窓)に向き、樹脂で覆わない。床の溝は
//   アンテナ部の下まで延ばさない(FPC をアンテナ下に通さない: 公式の注意)
// - C5 の Wi-Fi 用 FPC アンテナはフタ裏の凹み(C5 の上、+x 寄り)に貼る。FPC ケーブル・UWB F・LiPo から離す
// - バッテリー端には ストラップループ
// 印刷: 本体は底面、フタは天面をベッドに向ける(どちらもサポート不要)
// part = "body" | "lid" | "preview"(本体 + 浮かせたフタ)

include <common.scad>

part = "preview";

bat = [25.5, 37, 5.2];  // LiPo 公称 [幅, 長さ, 厚み](例: DPTL-DTP502535 400 mAh)。要実測調整

wall = 2;       // 側壁厚
floor_t = 2.4;  // 底厚
cavity_d = 9;   // 内寸深さ
rib = 2;        // 仕切り壁厚
rail_h = 4;     // 仕切り・レール高さ
chan_d = 1.4;   // 床の FPC/配線溝の深さ
lid_t = 2;      // フタ厚
skirt_h = 2.2;  // フタのスカート(嵌合部)高さ
win_w = 14;     // アンテナ窓の幅
ant_d = 0.6;    // フタ裏の Wi-Fi アンテナ用凹みの深さ
bay = 3;        // FPC 折り返し部(C5 と UWB F の間でケーブルを床へ下ろす)の長さ
usb_w = 13;     // USB-C スロット幅(プラグのモールド部が通る幅)
stop_w = 1.5;   // C5 の -x 側ストッパー厚
uwb_ch_w = uwb_conn_w + 1;  // UWB 側の床溝の幅

iw = bat[0] + 2 * tol;                  // 内寸幅(バッテリー幅で決まる)
bat_l  = bat[1] + 2 * tol;
c5_zone  = c5_w + 2 * tol;              // C5 は長さ(19.06)を幅方向に置く → USB-C が +x 側壁を向く
uwb_zone = uwb_l + 2 * tol;

c5_y0  = bat_l + rib;                   // C5 ゾーン開始 y(内寸座標)
uwb_y0 = c5_y0 + c5_zone + rib + bay + rib;   // UWB ゾーン開始 y
il = uwb_y0 + uwb_zone;                 // 内寸長さ
ol = il + 2 * wall;
ow = iw + 2 * wall;
oh = floor_t + cavity_d;

c5_x0 = iw - (c5_l + 2 * tol);          // C5 ポケット -x 端(USB-C 側は側壁まで)
c5_u0 = c5_x0 + tol;                    // C5 の u=0(PCB 端)の x
c5_v0 = c5_y0 + tol;                    // C5 の v=0(VBAT 側の辺)の y

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
        // C5 背面 FPC コネクタの凹み(-x 側の空きまで延ばし、ケーブルを床面近くで引き出せるようにする)
        translate([c5_x0 - 3, c5_v0 + c5_conn_v[0] - 0.5, floor_t - chan_d])
            cube([c5_u0 + c5_conn_u[1] + 0.5 - (c5_x0 - 3), c5_conn_v[1] - c5_conn_v[0] + 1, chan_d + 0.1]);
        // UWB 側の床溝(折り返し部 → UWB F 背面コネクタ。アンテナ部の下までは延ばさない)
        translate([iw / 2 - uwb_ch_w / 2, c5_y0 + c5_zone, floor_t - chan_d])
            cube([uwb_ch_w, uwb_y0 + tol + uwb_conn_l + 0.5 - (c5_y0 + c5_zone), chan_d + 0.1]);
        // USB-C スロット(+x 側壁、C5 の幅中央)
        translate([iw - 0.1, c5_v0 + c5_w / 2 - usb_w / 2, floor_t])
            cube([wall + 0.2, usb_w, cavity_d + 0.1]);
        // アンテナ窓(UWB 端の壁を全高で開口)
        translate([iw / 2 - win_w / 2, il - 0.1, floor_t])
            cube([win_w, wall + 0.2, cavity_d + 0.1]);
    }
    // 仕切り(側方スタブのみ。中央はバッテリー配線 / FPC の通り道)
    divider(bat_l, gap = 10);
    divider(c5_y0 + c5_zone, gap = 10);
    divider(uwb_y0 - rib, gap = uwb_ch_w + 1);
    // C5 の -x 側ストッパー(FPC の引き出し範囲を避けて 2 か所)
    c5_stop(c5_y0, c5_v0 + c5_conn_v[0] - 1.5);
    c5_stop(c5_v0 + c5_conn_v[1] + 1.5, c5_y0 + c5_zone);
    // UWB センタリングレール(→ ポケット 12.62)
    rails(uwb_y0, uwb_zone, (iw - (uwb_w + 2 * tol)) / 2);
}

module c5_stop(y0, y1) {
    translate([c5_x0 - stop_w, y0, floor_t]) cube([stop_w, y1 - y0, rail_h]);
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
        // Wi-Fi アンテナ用の凹み(フタ裏、C5 の上の +x 寄り。長辺を y 方向に置き、
        // C5 の上を渡る FPC ケーブル(幅中央付近)から離す)
        translate([iw - tol - 1.5 - (wifi_ant_h + 2 * tol),
                   c5_v0 + c5_w / 2 - (wifi_ant_w + 2 * tol) / 2, oh - 0.1])
            cube([wifi_ant_h + 2 * tol, wifi_ant_w + 2 * tol, ant_d + 0.1]);
        // USB スロット上の逃げ(フタを閉めたままケーブルを挿せる)
        translate([iw - 0.1, c5_v0 + c5_w / 2 - usb_w / 2, oh - skirt_h - 0.1])
            cube([wall + 0.2, usb_w, skirt_h + 0.1]);
    }
}

if (part == "body") body();
else if (part == "lid") lid();
else {
    body();
    translate([0, 0, 14]) lid();
}
