# -*- coding: utf-8 -*-
"""编辑历史「恢复」的全字段往返测试。

用户反馈：恢复历史时应该把位置、行距、阴影一起恢复，不能只恢复文字和字体。
这个测试把 HISTORY_FIELDS 里的每一个字段都设成有区分度的值，全部改掉，
再点「恢复到桌面」，逐个核对是否原样回来。

隔离 APPDATA，不碰真实数据。
"""
import json
import os
import shutil
import sys
import time

SANDBOX = r"E:\AI\ToMe\.fields-tmp"
if os.path.isdir(SANDBOX):
    shutil.rmtree(SANDBOX, ignore_errors=True)
os.makedirs(SANDBOX, exist_ok=True)
os.environ["APPDATA"] = SANDBOX

import motto_qt as M  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
FAILS = []


def check(name, got, want):
    ok = got == want
    print("  [%s] %-28s got=%r want=%r" % ("PASS" if ok else "FAIL", name,
                                           got, want))
    if not ok:
        FAILS.append(name)


def pump(ms=350, step=40):
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(step / 1000.0)


# ---- A：原始状态，每个字段都给一个独特值 ----
# 位置故意贴着屏幕底部 + 大字号多行文字：这样「恢复后窗口比屏幕还低」，
# 正好命中 auto_fit 里那段「底部出屏就整体上移」的逻辑。
# 修复前 win.y() 会被挪到 ~743 而不是 800，这个用例就是拿来钉死它的。
A = dict(M.DEFAULT_CFG)
A.update({
    "text": "原始文字甲\n第二行乙\n第三行丙",
    "font_family": "Microsoft YaHei",
    "font_pt": 72.0,
    "bold": True,
    "italic": True,
    "text_color": 0xFF3300,
    "text_alpha": 55,
    "shadow_on": False,
    "border_color": 0x00FF66,
    "border_alpha": 37,
    "line_gap": 12,
    "align": 2,
    "x": 250, "y": 800, "w": 640, "h": 336,
    "theme": "light", "first_run": True,
})

# ---- B：全改一遍（每项都和 A 不同）----
B = dict(A)
B.update({
    "text": "改动后的文字丙",
    "font_family": "SimSun",
    "font_pt": 18.0,
    "bold": False,
    "italic": False,
    "text_color": 0x0000FF,
    "text_alpha": 90,
    "shadow_on": True,
    "border_color": 0xFF00FF,
    "border_alpha": 80,
    "line_gap": 5,
    "align": 0,
    "x": 900, "y": 700, "w": 400, "h": 120,
})

M.S["cfg"] = dict(A)
M.save_cfg(M.S["cfg"])

# 用 A 建窗口（窗口位置 = A 的位置）
win = M.MottoWindow(M.S["cfg"])
win.show()
app.processEvents()
win.apply_display_mode()
win.set_edit_mode(True)
pump(200)

# 把 A 落成一条历史
M.push_history(M.S["cfg"])
entry = M.load_history()[-1]
pump(100)

# 再把当前状态整个改成 B（含窗口位置）
for k, v in B.items():
    M.S["cfg"][k] = v
win.setGeometry(B["x"], B["y"], B["w"], B["h"])
M.save_cfg(M.S["cfg"])
win.repaint()
pump(200)

print("=" * 64)
print("A（要恢复成的样子）:", {k: A[k] for k in M.HISTORY_FIELDS})
print("B（恢复前的样子）  :", {k: B[k] for k in M.HISTORY_FIELDS})
print("=" * 64)

# ---- 打开设置窗 → 历史页 → 选中 A → 点「恢复到桌面」----
dlg = M.SettingsDialog(win)
dlg.show()
pump()
dlg.nav.setCurrentRow(3)
pump(300)

row = next(i for i, e in enumerate(dlg.hist_view)
           if e.get("ts") == entry.get("ts"))
dlg.lst_hist.setCurrentRow(row)
pump(200)
dlg.b_hist_restore.click()
pump(500)

print("\n逐个字段核对：")
for k in M.HISTORY_FIELDS:
    check(k, M.S["cfg"].get(k), entry.get(k))

print("\n窗口几何（位置必须原样回来 —— 这次真正要钉死的点）：")
check("win.x()", win.x(), A["x"])
check("win.y()", win.y(), A["y"])
check("win.width()", win.width(), A["w"])
check("win.height()", win.height(), A["h"])
from PySide6.QtWidgets import QApplication as _QA  # noqa: E402
_scr = _QA.primaryScreen().availableGeometry()
print("      （屏幕可用区 y=%d..%d；A.y=%d + 高=%d 已超出底部，"
      "修复前会被 auto_fit 上移）" % (_scr.top(), _scr.bottom(),
                                      A["y"], A["h"]))

print("\n磁盘 config.json：")
with open(M.CONFIG_FILE, "r", encoding="utf-8") as f:
    disk = json.load(f)
for k in M.HISTORY_FIELDS:
    check("disk." + k, disk.get(k), entry.get(k))

print("\n" + ("全部通过" if not FAILS else "存在失败：%s" % FAILS))

# ---- 对照实验：证明「修复前」位置是怎么丢的 ----
print("\n对照：放开 auto_fit 再跑一次（等价于修复前的行为）")
_y0 = win.y()
win.suppress_autofit = False
win.auto_fit()
pump(200)
if win.y() != _y0:
    print("  auto_fit 把窗口从 y=%d 挪到了 y=%d" % (_y0, win.y()))
    print("  ↑ 这就是修复前「恢复了历史，位置却不对」的原因")
else:
    print("  本次未触发移动（y 仍为 %d）" % _y0)

dlg.close()
win.finish_edit()
sys.exit(1 if FAILS else 0)
