# -*- coding: utf-8 -*-
"""开机自启功能测试：直接验证注册表 Run 键的写入 / 读取 / 自愈 / 删除。

用法（需要 PySide6，源码目录与依赖目录都要在 PYTHONPATH 上）：
    set PYTHONPATH=E:\\AI\\ToMe\\.builddeps;E:\\AI\\ToMe\\DesktopMotto
    python test_autostart.py

测试前会保存用户原有的 Run\\ToMe 值，测试结束后原样还原，
所以不会改变用户「开机自启」的真实状态。
"""
import os
import sys

import motto_qt as m


def read_run_value():
    """绕过被测代码，独立读一遍注册表，避免用同一份逻辑自证。"""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, m.RUN_KEY) as k:
            v, _ = winreg.QueryValueEx(k, m.RUN_VALUE)
            return v
    except OSError:
        return None


def main():
    failures = []

    def check(name, got, want):
        ok = got == want
        print("  [%s] %s" % ("PASS" if ok else "FAIL", name))
        if not ok:
            print("        got  = %r\n        want = %r" % (got, want))
            failures.append(name)

    original = read_run_value()
    print("原有 Run\\ToMe = %r" % original)

    try:
        # --- 1. 关闭自启 ---
        print("\n1. 关闭开机自启")
        check("set_autorun(False) 返回 True", m.set_autorun(False), True)
        check("is_autorun() == False", m.is_autorun(), False)
        check("注册表里确实没有该项", read_run_value(), None)

        # --- 2. 开启自启 ---
        print("\n2. 开启开机自启")
        check("set_autorun(True) 返回 True", m.set_autorun(True), True)
        check("is_autorun() == True", m.is_autorun(), True)
        check("注册表值 == autorun_command()",
              read_run_value(), m.autorun_command())
        cmd = read_run_value()
        print("     登记的启动命令 = %s" % cmd)
        check("命令带引号包裹 exe 路径",
              cmd.startswith('"') and cmd.rstrip().endswith('"'), True)
        if getattr(sys, "frozen", False):
            check("冻结态登记的就是 exe 自身", cmd.strip('"'), sys.executable)
        else:
            check("源码态登记的是 python.exe + 脚本路径",
                  m.__file__ in cmd.replace('"', ""), True)

        # --- 3. 路径自愈：模拟程序被移动/重装后登记的旧路径 ---
        print("\n3. 旧路径自愈")
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, m.RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, m.RUN_VALUE, 0, winreg.REG_SZ,
                              '"C:\\Old\\Gone\\ToMe.exe"')
        check("已写入陈旧的旧路径",
              read_run_value(), '"C:\\Old\\Gone\\ToMe.exe"')
        m.sync_autorun()
        check("sync_autorun() 改写为当前路径",
              read_run_value(), m.autorun_command())

        # --- 4. 幂等：sync_autorun 不应无谓改动 ---
        before = read_run_value()
        m.sync_autorun()
        check("已是当前路径时 sync_autorun 不动它",
              read_run_value(), before)

        # --- 4b. 登记的路径存在、但指向另一个副本 → 不许抢走 ---
        # （安装版 + 便携版共存时，谁后启动谁抢自启项 —— 这是真实踩过的坑）
        print("\n3b. 指向别的副本时不抢")
        import winreg
        other = os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                             "notepad.exe")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, m.RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, m.RUN_VALUE, 0, winreg.REG_SZ,
                              '"%s"' % other)
        m.sync_autorun()
        check("目标文件存在 → 保持原样",
              read_run_value(), '"%s"' % other)
        check("确实没被改成本程序",
              read_run_value() != m.autorun_command(), True)

        # --- 5. 再关一次 ---
        print("\n4. 再次关闭")
        check("set_autorun(False) 返回 True", m.set_autorun(False), True)
        check("is_autorun() == False", m.is_autorun(), False)
        check("注册表项已删除", read_run_value(), None)

    finally:
        # 还原用户原来状态
        if original is None:
            m.set_autorun(False)
        else:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, m.RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, m.RUN_VALUE, 0, winreg.REG_SZ, original)
        print("\n已还原 Run\\ToMe = %r" % read_run_value())

    print("\n%s（%d 项失败）" %
          ("全部通过" if not failures else "存在失败", len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
