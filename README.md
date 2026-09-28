# 寄己 ToMe — 桌面座右铭挂件

**版本 0.8** · Windows

在桌面上放一段只属于自己的话。文字贴在壁纸层之上、所有窗口之下，点击穿透，不挡任何操作；托盘右键即可编辑。

## 功能

- 桌面常驻座右铭：贴底（贴壁纸层）+ 鼠标点击穿透 + 心跳自愈（20s 重申沉底与穿透）
- 编辑模式：虚线框可视化，可拖动位置、右下角拖拽缩放，间隔期间实时渲染、实时保存
- 文字设置：字体（自研字体选择器，每项用自身字体渲染 + 实时预览）、字号滑杆、粗斜体、行距、对齐、文字/边框颜色（自研取色器：SV 面板 + 色相条 + 预设色板 + HEX）
- 界面：Win11 Fluent 设计语言，无边框窗口，深浅色跟随系统，中文/English 可切换
- 其他：开机自启动（Fluent 开关）、单实例运行、配置存于 `%APPDATA%\ToMe`

## 环境与运行

- Windows 10 19041+
- Python 3.10+，PySide6

```bash
pip install PySide6
python motto_qt.py
```

## 打包单文件 exe

```bash
pyinstaller --onefile --noconsole \
  --exclude-module PySide6.QtNetwork --exclude-module PySide6.QtSvg \
  motto_qt.py -n ToMe.exe
```

## 目录说明

| 文件 | 说明 |
| --- | --- |
| `motto_qt.py` | 主程序（全部逻辑，约 1300 行） |
| `smoketest.py` | 冒烟测试：实例化各窗口并截图 |
| `kill_tome.py` | 终止 ToMe.exe 实例（含提权进程处理） |
| `docs/` | 界面截图 |

## 实现要点

- 沉底方案：`SetWindowPos(HWND_BOTTOM)` + `WS_EX_TRANSPARENT`（桌面歌词式，放弃 WorkerW 挂靠——Qt 透明窗口挂入 WorkerW 不渲染）
- 全代码绘制：托盘图标、开关、取色面板均由 QPainter 绘制，无任何资源文件
- 单实例：命名 Mutex；每版本更换避免旧实例阻塞新版本自检

## License

MIT
