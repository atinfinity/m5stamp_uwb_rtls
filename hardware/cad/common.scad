// 共通パラメータ: M5Stamp C5 / M5Stamp UWB F の公称寸法(mm)
// 出典: shop.m5stack.com 製品ページ(2026-08 時点)
//   M5Stamp C5:     17.6 x 19.1 x 3.4 mm
//   M5Stamp UWB F:  11.5 x 12.0 x 2.8 mm(PCB アンテナ内蔵・背面 FPC コネクタ)
// 注意: 公称値ベースの v1 モデル。印刷後に実機でフィット確認し、tol を調整すること。

c5_w = 17.6;   // C5 幅
c5_l = 19.1;   // C5 長さ(USB-C は短辺側と想定)
c5_t = 3.4;    // C5 厚み

uwb_w = 11.5;  // UWB F 幅
uwb_l = 12.0;  // UWB F 長さ(片端がアンテナ部)
uwb_t = 2.8;   // UWB F 厚み

tol = 0.3;     // 片側クリアランス(ポケット寸法 = 部品寸法 + 2*tol)

fpc_w = 12.5;  // FPC ケーブル幅(0.5mm-12P + 余裕)

$fn = 48;

// ざぐり付きネジ穴(皿ネジ M3 想定)。h = 板厚
module screw_hole(h, d = 3.6, head_d = 7, head_h = 2) {
    translate([0, 0, -0.1]) cylinder(d = d, h = h + 0.2);
    translate([0, 0, h - head_h]) cylinder(d1 = d, d2 = head_d, h = head_h + 0.1);
}
