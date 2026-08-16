// アンカー取付具(壁面・柱用 L ブラケット)
// - 垂直プレートを壁にネジ 3 本(皿 M3)で固定
// - プレート前面のポケットに M5Stamp C5、上部棚の上面ポケットに Stamp UWB F を置く
//   (固定は薄手の両面テープを想定)
// - UWB F のアンテナ端は棚の前縁側(壁と反対)を向き、前方に壁・部材が無い
// - FPC ケーブルはプレート前面の溝 → 棚のスリットを通して両ボードの背面コネクタへ
// 座標系は設置姿勢(y=0 が壁面、+y が壁から離れる向き、+z が上)
// 印刷時は背面(y=0 面)をベッドに向けて水平に寝かせる(サポート不要)

include <common.scad>

preview = false;  // true でプレビュー用に前面(ポケット側)をカメラへ向ける

plate_w = 34;    // プレート幅
plate_h = 78;    // プレート高さ
plate_t = 4;     // プレート厚
shelf_d = 20;    // 棚の奥行き(壁から)
shelf_t = 4;     // 棚厚
pock_wall = 2;   // C5 ポケット壁厚
pock_h = 4.5;    // C5 ポケット壁高さ
uwb_wall = 1.5;  // UWB ポケット壁厚
uwb_wall_h = 3;  // UWB ポケット壁高さ
chan_d = 1.2;    // FPC 溝深さ

c5_px = c5_w + 2 * tol;   // C5 ポケット内寸(幅)
c5_pz = c5_l + 2 * tol;   // C5 ポケット内寸(高さ)
c5_z0 = 36;               // C5 ポケット下端の高さ
uwb_px = uwb_w + 2 * tol;
uwb_py = uwb_l + 2 * tol;
uwb_y0 = 5;               // UWB モジュール後端(壁側)の y 位置

module anchor_mount() {
    difference() {
        union() {
            // 垂直プレート
            cube_c([plate_w, plate_t, plate_h], cx = true);
            // 上部棚
            translate([0, 0, plate_h]) cube_c([plate_w, shelf_d, shelf_t], cx = true);
            // ガセット(棚の補強) x2
            for (sx = [-1, 1])
                translate([sx * plate_w / 2 - (sx < 0 ? 0 : 3), 0, 0])
                    gusset();
            // C5 ポケット壁(上辺なし・下辺は USB 用に中央が開く)
            translate([0, plate_t, 0]) c5_pocket_walls();
            // UWB ポケット壁(前辺なし = アンテナ側オープン)
            translate([0, 0, plate_h + shelf_t]) uwb_pocket_walls();
        }
        // ネジ穴(皿 M3): 下 1 + 上 2。ざぐりは前面(+y)側
        for (p = [[0, 8], [-11, 66], [11, 66]])
            translate([p[0], 0, p[1]]) rotate([-90, 0, 0]) screw_hole(plate_t);
        // FPC 溝(プレート前面、C5 ポケット床から上端まで)
        translate([-fpc_w / 2, plate_t - chan_d, c5_z0]) cube([fpc_w, chan_d + 0.1, plate_h - c5_z0 + 0.1]);
        // FPC スリット(棚を貫通し UWB モジュール後端の下へ)
        translate([-fpc_w / 2, plate_t - chan_d, plate_h - 0.1]) cube([fpc_w, 8 - (plate_t - chan_d), shelf_t + 0.2]);
        // ケーブルタイ用スリット x2(USB ケーブルの張力止め)
        for (sx = [-1, 1])
            translate([sx * 5.5 - 1.1, -0.1, 18]) cube([2.2, plate_t + 0.2, 6]);
    }
}

// 中央下端揃えの cube
module cube_c(size, cx = false) {
    translate([cx ? -size[0] / 2 : 0, 0, 0]) cube(size);
}

module gusset() {
    rotate([90, 0, 90]) linear_extrude(3)
        polygon([[plate_t, plate_h], [16, plate_h], [plate_t, plate_h - 14]]);
}

module c5_pocket_walls() {
    ox = c5_px / 2 + pock_wall;    // 外周半幅
    usb_gap = 13;
    // 側壁
    for (sx = [-1, 1])
        translate([sx * c5_px / 2 - (sx < 0 ? pock_wall : 0), 0, c5_z0 - pock_wall])
            cube([pock_wall, pock_h, c5_pz + pock_wall]);
    // 下壁(中央 usb_gap を開ける)
    for (sx = [-1, 1])
        translate([sx < 0 ? -ox : usb_gap / 2, 0, c5_z0 - pock_wall])
            cube([ox - usb_gap / 2, pock_h, pock_wall]);
}

module uwb_pocket_walls() {
    // 後壁(壁側)
    translate([-uwb_px / 2 - uwb_wall, uwb_y0 - uwb_wall, 0])
        cube([uwb_px + 2 * uwb_wall, uwb_wall, uwb_wall_h]);
    // 側壁(後半のみ。前方 = アンテナ側はオープン)
    for (sx = [-1, 1])
        translate([sx * uwb_px / 2 - (sx < 0 ? uwb_wall : 0), uwb_y0 - uwb_wall, 0])
            cube([uwb_wall, 8 + uwb_wall, uwb_wall_h]);
}

if (preview) rotate([0, 0, 180]) anchor_mount();
else anchor_mount();
