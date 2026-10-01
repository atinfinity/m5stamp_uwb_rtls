// 共通パラメータ: M5Stamp C5 DIP / M5Stamp UWB F の寸法(mm)
// 出典: 公式ドキュメントの寸法図(Model Size)
//   docs.m5stack.com/en/core/Stamp-C5_DIP   (S016-DIP-Stamp-C5_DIP_model_size)
//   docs.m5stack.com/en/stamp/stamp_uwb_f    (S017-F-Stamp_UWB_F_model_size)
// ストア公称値(C5: 17.6 x 19.1 x 3.4 / UWB F: 11.5 x 12.0 x 2.8)とも一致。
// 部品内の位置(コネクタ等)は寸法図からの読み取り値(±0.3 程度)。
// 注意: 実機でのフィット確認は未実施。印刷後に確認し、tol を調整すること。
// C5 は DIP 版付属のピンヘッダをはんだ付けしない前提(付けると厚みが増して収まらない)。

// --- M5Stamp C5 DIP ---
// 座標 u: USB-C と反対の端(PCB 端)から USB-C 方向、v: VBAT 側の長辺から反対側の長辺方向(部品面から見る)
c5_w = 17.6;    // 幅(v 方向)
c5_l = 19.06;   // 長さ(u 方向)。PCB 18.0 + USB-C の突き出し 1.06
c5_t = 3.36;    // PCB 下面から部品面シールド上面まで
c5_conn_h = 1.0;            // 背面 FPC コネクタの PCB 下面からの突き出し
c5_conn_u = [1.7, 5.8];     // 背面 FPC コネクタの u 範囲。ケーブルは u=0 側(USB と反対の端)へ出る
c5_conn_v = [2.4, 10.3];    // 同 v 範囲(VBAT 側へ寄っている)
c5_ipex = [2.1, 13.3];      // 部品面の IPEX-1(Wi-Fi アンテナ)中心 [u, v]
c5_vbat_u = 11.6;           // VBAT パッド(v=1.05 の列)の u。GND は 16.75

// --- M5Stamp UWB F ---
// アンテナ(PCB アンテナ、シールドなし部分)は長さ方向の片端。FPC コネクタは反対端の背面
uwb_w = 12.02;  // 幅
uwb_l = 11.53;  // 長さ(片端がアンテナ部)
uwb_t = 1.62;   // PCB 下面からシールド上面まで
uwb_conn_h = 1.2;    // 背面 FPC コネクタの突き出し
uwb_conn_w = 8.0;    // 同 幅(幅方向中央)
uwb_conn_l = 3.8;    // 同 長さ(アンテナと反対端から)。ケーブルはこの端から出る
uwb_ant_l = 3.7;     // アンテナ部の長さ(アンテナ端から)。FPC をこの下に通さない(公式の注意)

// C5 同梱の Wi-Fi 用 FPC アンテナ(2.4/5 GHz、IPEX-1、ケーブル長 50 mm)
// 出典: docs.m5stack.com/en/core/Stamp-C5
wifi_ant_w = 14.3;  // 長さ
wifi_ant_h = 5.3;   // 幅

tol = 0.3;     // 片側クリアランス(ポケット寸法 = 部品寸法 + 2*tol)

fpc_w = 12.5;  // FPC 溝・スリットの幅(ケーブル幅 約 6.5 + コネクタ位置の振れ代)

$fn = 48;

// ざぐり付きネジ穴(皿ネジ M3 想定)。h = 板厚
module screw_hole(h, d = 3.6, head_d = 7, head_h = 2) {
    translate([0, 0, -0.1]) cylinder(d = d, h = h + 0.2);
    translate([0, 0, h - head_h]) cylinder(d1 = d, d2 = head_d, h = head_h + 0.1);
}
