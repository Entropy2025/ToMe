# -*- coding: utf-8 -*-
"""编辑历史逻辑测试（不弹界面，不碰你真实的 %APPDATA%\\ToMe）。

用法：
    set PYTHONPATH=E:\\AI\\ToMe\\.builddeps;E:\\AI\\ToMe\\DesktopMotto
    python test_history.py

它把 APPDATA 指到一个临时目录后再导入 motto_qt，
所以测的是真实代码路径，但不会污染你的真实配置和历史。
"""
import json
import os
import shutil
import sys

SANDBOX = r"E:\AI\ToMe\.histtest"
if os.path.isdir(SANDBOX):
    shutil.rmtree(SANDBOX, ignore_errors=True)
os.makedirs(SANDBOX, exist_ok=True)
os.environ["APPDATA"] = SANDBOX          # 必须在 import motto_qt 之前

import motto_qt as m  # noqa: E402

FAILS = []


def check(name, got, want):
    ok = got == want
    print("  [%s] %s" % ("PASS" if ok else "FAIL", name))
    if not ok:
        print("        got  = %r\n        want = %r" % (got, want))
        FAILS.append(name)


def cfg_of(**kw):
    c = dict(m.DEFAULT_CFG)
    c.update(kw)
    return c


def main():
    print("历史文件: %s" % m.HISTORY_FILE)
    check("历史文件落在 APPDATA 下",
          m.HISTORY_FILE.startswith(SANDBOX), True)

    # ---------- 1. 快照内容 ----------
    print("\n1. 快照字段")
    snap = m.history_snapshot(cfg_of(text="A"))
    check("含文字", "text" in snap, True)
    check("含字号", "font_pt" in snap, True)
    check("含文字颜色", "text_color" in snap, True)
    check("含透明度/投影/行距/对齐",
          all(k in snap for k in ("text_alpha", "shadow_on", "line_gap", "align")),
          True)
    check("不含窗口位置 x", "x" in snap, False)
    check("不含窗口大小 w/h", ("w" in snap) or ("h" in snap), False)

    # ---------- 2. 落一条 + 去重 ----------
    print("\n2. 落一条 / 完全相同不重复记")
    check("首次落一条", m.push_history(cfg_of(text="第一版")), True)
    check("条数 = 1", len(m.load_history()), 1)
    check("完全相同 → 不新增", m.push_history(cfg_of(text="第一版")), False)
    check("条数仍 = 1", len(m.load_history()), 1)
    check("改文字 → 新增", m.push_history(cfg_of(text="第二版")), True)
    check("条数 = 2", len(m.load_history()), 2)
    check("只改样式也算一次编辑",
          m.push_history(cfg_of(text="第二版", font_pt=48.0)), True)
    check("条数 = 3", len(m.load_history()), 3)

    # ---------- 3. 持久化 ----------
    print("\n3. 持久化与损坏容错")
    saved = m.load_history()
    check("文件存在", os.path.exists(m.HISTORY_FILE), True)
    check("落盘内容可读回", [e["text"] for e in m.load_history()],
          [e["text"] for e in saved])
    with open(m.HISTORY_FILE, "w", encoding="utf-8") as f:
        f.write("{ 这不是合法 json")
    check("损坏文件 → 当作空历史", m.load_history(), [])
    m.save_history(saved)                     # 还原

    # ---------- 4. 上限与置顶 ----------
    print("\n4. 100 条上限：只淘汰未置顶，置顶永久保留")
    items = []
    for i in range(105):
        e = m.history_snapshot(cfg_of(text="普通%d" % i))
        e["ts"] = 1000 + i
        e["pinned"] = False
        items.append(e)
    # 两条置顶的，时间最早
    for i, t in enumerate((1, 2)):
        e = m.history_snapshot(cfg_of(text="置顶%d" % i))
        e["ts"] = t
        e["pinned"] = True
        items.append(e)
    trimmed = m.trim_history(items)
    pinned = [e for e in trimmed if e["pinned"]]
    plain = [e for e in trimmed if not e["pinned"]]
    check("未置顶被裁到 100 条", len(plain), 100)
    check("置顶的 2 条都还在", len(pinned), 2)
    check("被淘汰的是最旧的未置顶",
          all(e["text"] != "普通0" for e in trimmed), True)
    check("最新的一条保留", any(e["text"] == "普通104" for e in trimmed), True)

    # ---------- 5. 展示顺序 ----------
    print("\n5. 展示顺序：置顶在前，各自从新到旧")
    order = m.history_display_order(trimmed)
    check("前两条是置顶", [e["pinned"] for e in order[:2]], [True, True])
    check("其余都未置顶", all(not e["pinned"] for e in order[2:]), True)
    check("置顶内部按时间倒序",
          [e["ts"] for e in order[:2]], [2, 1])
    ts_tail = [e["ts"] for e in order[2:]]
    check("未置顶内部按时间倒序", ts_tail == sorted(ts_tail, reverse=True), True)

    # ---------- 6. 导出 ----------
    print("\n6. 导出 txt")
    txt = m.history_export_text(trimmed)
    check("含标题", "念 ToMe" in txt, True)
    check("含最新一条内容", "普通104" in txt, True)
    check("含置顶标记", "[置顶]" in txt, True)
    check("含样式摘要", "pt" in txt, True)
    check("条数正确", "共 %d 条" % len(trimmed) in txt, True)

    # ---------- 7. 真实文件往返 ----------
    print("\n7. 真实文件往返")
    m.save_history(trimmed)
    back = m.load_history()
    check("写盘再读回条数一致", len(back), len(trimmed))
    check("置顶状态保留",
          sorted(e["ts"] for e in back if e["pinned"]), [1, 2])
    check("文字保留", any(e["text"] == "普通104" for e in back), True)

    print("\n%s（%d 项失败）" % ("全部通过" if not FAILS else "存在失败",
                                len(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
