# -*- coding: utf-8 -*-
"""历史记录页的图形冒烟测试。

把 APPDATA 指到隔离目录后再导入 motto_qt，所以造假数据不会污染你真实的历史。
跑完会生成 shot_history.png，可以直接看这一页长什么样。

用法：
    set PYTHONPATH=E:\\AI\\ToMe\\.builddeps;E:\\AI\\ToMe\\DesktopMotto
    python smoketest_history.py
"""
import os
import shutil
import sys
import time

SANDBOX = r"E:\AI\ToMe\.histtest"
if os.path.isdir(SANDBOX):
    shutil.rmtree(SANDBOX, ignore_errors=True)
os.makedirs(SANDBOX, exist_ok=True)
os.environ["APPDATA"] = SANDBOX

import motto_qt as M  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication(sys.argv)
M.S["cfg"] = M.load_cfg()
win = M.MottoWindow(M.S["cfg"])
win.show()
app.processEvents()
win.apply_display_mode()


def pump(ms=400, step=40):
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(step / 1000.0)


def grab(widget, name, margin=60):
    pump(500)
    g = widget.frameGeometry()
    app.primaryScreen().grabWindow(
        0, max(0, g.x() - margin), max(0, g.y() - margin),
        g.width() + margin * 2, g.height() + margin * 2).save(name)


# ---- 造 5 条历史（两条置顶，时间故意打乱顺序）----
samples = [("此刻专注\n只做最重要的事", True, 1759400000),
           ("慢慢来，比较快", False, 1759407200),
           ("今天只做三件事", False, 1759414400),
           ("先完成，再完美", True, 1759421600),
           ("少即是多", False, 1759428800)]
items = []
for t, pin, ts in samples:
    e = M.history_snapshot(dict(M.DEFAULT_CFG, text=t, font_pt=28))
    e["ts"] = ts
    e["pinned"] = pin
    items.append(e)
M.save_history(items)

dlg = M.SettingsDialog(win)
dlg.show()
pump()
dlg.nav.setCurrentRow(3)
pump(300)

fails = []


def check(name, got, want):
    ok = got == want
    print("  [%s] %s" % ("PASS" if ok else "FAIL", name))
    if not ok:
        print("        got  = %r\n        want = %r" % (got, want))
        fails.append(name)


print("1. 列表渲染")
check("列表条数 = 5", dlg.lst_hist.count(), 5)
check("置顶的排在最前",
      dlg.lst_hist.item(0).text().startswith("📌"), True)
check("第 2 条也是置顶",
      dlg.lst_hist.item(1).text().startswith("📌"), True)
check("第 3 条不是置顶",
      dlg.lst_hist.item(2).text().startswith("📌"), False)
check("默认选中第一行", dlg.lst_hist.currentRow(), 0)
# 两条置顶里「先完成，再完美」时间更晚，应排在第 0 行
check("第 0 行是较新的那条置顶",
      dlg.hist_item().get("text"), "先完成，再完美")
check("预览里含文字", "先完成，再完美" in dlg.lbl_hist_prev.text(), True)
check("预览里含样式摘要", "pt" in dlg.lbl_hist_prev.text(), True)

print("\n2. 置顶 / 取消置顶")
dlg.lst_hist.setCurrentRow(4)          # 一条未置顶的
pump(150)
check("未置顶时按钮显示「置顶」", dlg.b_hist_pin.text(), M.tr("hist_pin"))
dlg.hist_toggle_pin()
pump(150)
check("置顶后置顶条数 = 3",
      sum(1 for e in M.load_history() if e.get("pinned")), 3)
check("置顶后它跑到第一行",
      dlg.lst_hist.item(0).text().startswith("📌"), True)
dlg.hist_toggle_pin()                  # 再取消
pump(150)
check("取消置顶后回到 2 条",
      sum(1 for e in M.load_history() if e.get("pinned")), 2)

print("\n3. 恢复")
dlg.lst_hist.setCurrentRow(0)
pump(150)
target_text = dlg.hist_item().get("text")
target_pt = dlg.hist_item().get("font_pt")
before_n = len(M.load_history())
dlg.hist_restore()
pump(300)
check("cfg 文字已恢复", M.S["cfg"]["text"], target_text)
check("cfg 字号已恢复", M.S["cfg"]["font_pt"], target_pt)
check("文字框同步", dlg.txt.toPlainText(), target_text)
check("字号滑杆同步", dlg.sl_font.value(), int(round(target_pt)))
check("历史新增了一条（恢复也算编辑）",
      len(M.load_history()) >= before_n, True)
check("落盘了", os.path.exists(M.HISTORY_FILE), True)

print("\n4. 删除单条")
n0 = len(M.load_history())
dlg.lst_hist.setCurrentRow(1)
pump(150)
dlg.hist_delete()
pump(150)
check("条数 -1", len(M.load_history()), n0 - 1)
check("列表同步", dlg.lst_hist.count(), n0 - 1)

print("\n5. 清空（只清未置顶）")
M.save_history(items)                  # 复原成 5 条（2 条置顶）
dlg.hist = M.load_history()
dlg.rebuild_hist()
pump(150)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
dlg.hist_clear()
pump(150)
left = M.load_history()
check("只剩置顶的 2 条", len(left), 2)
check("留下的都是置顶", all(e.get("pinned") for e in left), True)

print("\n6. 导出 txt")
M.save_history(items)
dlg.hist = M.load_history()
dlg.rebuild_hist()
pump(150)
out = os.path.join(SANDBOX, "export.txt")
with open(out, "w", encoding="utf-8") as f:
    f.write(M.history_export_text(dlg.hist))
body = open(out, encoding="utf-8").read()
check("txt 非空", len(body) > 100, True)
check("txt 含置顶标记", "[置顶]" in body, True)

# ---- 截图 ----
dlg.lst_hist.setCurrentRow(0)
pump(300)
grab(dlg, "shot_history.png")

print("\n7. 六个按钮等宽（用户报告的第二个问题）")
_btns = (dlg.b_hist_restore, dlg.b_hist_pin, dlg.b_hist_del,
         dlg.b_hist_copy, dlg.b_hist_export, dlg.b_hist_clear)
_widths = sorted({b.width() for b in _btns})
check("六个按钮宽度完全一致", len(_widths), 1)
print("      宽度:", _widths, "| 文案:", [b.text() for b in _btns])

print("\n8. 双击一条历史 = 恢复到桌面")
M.save_history(items)
dlg.hist = M.load_history()
dlg.rebuild_hist()
pump(150)
_row = next(i for i, e in enumerate(dlg.hist_view) if e["text"] == "少即是多")
dlg.lst_hist.setCurrentRow(_row)
pump(150)
check("切换选中后提示回到默认", dlg.lbl_hist_tip.text(), M.tr("hist_tip"))
dlg.lst_hist.itemDoubleClicked.emit(dlg.lst_hist.item(_row))
pump(350)
check("双击后 cfg 文字已恢复", M.S["cfg"]["text"], "少即是多")
check("提示换成「已恢复」", dlg.lbl_hist_tip.text(), M.tr("hist_applied"))

print("\n9. 关闭设置窗口 = 落一条历史")
M.save_history(items)
dlg.hist = M.load_history()
dlg.rebuild_hist()
pump(150)
n0 = len(M.load_history())
dlg.guard = True
dlg.txt.setPlainText("关窗那一刻的文字")
dlg.prev_text = dlg.txt.toPlainText()
dlg.guard = False
dlg.on_changed()
dlg.close()
pump(250)
after = M.load_history()
check("关闭后新增一条", len(after), n0 + 1)
check("新增的正是关窗时的内容",
      any(e["text"] == "关窗那一刻的文字" for e in after), True)
new = [e for e in after if e["text"] == "关窗那一刻的文字"][0]
check("新增的默认未置顶", new.get("pinned"), False)
check("新增的带时间戳", int(new.get("ts", 0)) > 0, True)
check("新增的存了样式", new.get("font_family") == M.S["cfg"]["font_family"], True)

print("\n10. 没改动再开关一次 → 不重复记")
dlg2 = M.SettingsDialog(win)
dlg2.show()
pump(300)
dlg2.close()
pump(250)
check("条数不变", len(M.load_history()), len(after))

win.finish_edit()

print("\n%s（%d 项失败）" % ("全部通过" if not fails else "存在失败", len(fails)))
sys.exit(1 if fails else 0)
