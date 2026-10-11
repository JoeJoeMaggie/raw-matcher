# RAW原图查找复制工具

根据 JPG 文件夹中的文件名，在 RAW 文件夹中查找同名的 RAW 原图，并复制到 JPG 文件夹下的
`raw原图` 子文件夹中。纯本地运行，不联网、不写数据库。

- 语言：Python 3.10+
- 界面：Tkinter（macOS 系统自带，无需额外安装）
- 依赖：仅 `tkinterdnd2`（拖拽用）；**没装也能启动**，只是拖拽不可用
- 平台：macOS（Ventura / Sonoma / Sequoia 均可用），同时兼容 Windows / Linux

## 一、功能介绍

| 项目 | 说明 |
| --- | --- |
| JPG 识别 | `.jpg` / `.jpeg`，大小写不敏感 |
| RAW 识别 | `.cr2` `.cr3` `.nef` `.arw` `.raf` `.dng` `.rw2` `.orf` `.pef` `.srw`，大小写不敏感 |
| 匹配规则 | 文件名（不含扩展名）转小写后一一对应 |
| 复制方式 | `shutil.copy2`，保留原始修改时间与文件元数据 |
| 同名冲突 | 目标文件已存在时跳过，日志记录「已跳过（已存在）」 |
| 多格式同名 | 同一文件名存在多种 RAW 格式时取排序后的第一个，不会互相覆盖 |
| 中断情况 | 单个文件失败只记日志，不中断整体流程 |
| 性能 | 后台线程处理，界面不卡死；处理中「开始处理」按钮置灰 |
| 日志 | 实时滚动，一键清空；结束时输出统计：共 X 个 JPG，成功复制 Y 个，未找到 Z 个，跳过 W 个 |
| 高 DPI | 启动即声明 DPI 感知并按屏幕缩放全部尺寸，缩放 125%/150%/200% 的屏幕上不糊 |
| 标题栏 | macOS 用系统原生红黄绿三键；Windows/Linux 自绘同款三键 + 拖动移动 + 右下角缩放 |
| 图标 | `icon.icns` 用于 .app，`icon.png`/`icon.ico` 用于运行时窗口图标 |
| 拖拽 | 从 Finder / 资源管理器把文件夹直接拖到路径框；含空格的路径自动去掉 `{}`；无效路径弹窗并清空 |
| 路径保留 | 处理完成后路径不清空，可换一批文件直接再点「开始处理」 |

日志前缀含义：`✓` 已复制 / `✗` 未找到或失败 / `⊘` 已跳过（已存在）。

## 二、如何运行

```bash
# 需要 Python 3.10 或更高版本
python3 --version

# 安装拖拽依赖（可选，不装也能用，只是拖拽不可用）
python3 -m pip install tkinterdnd2

# 直接运行
python3 main.py
```

自检（不需要图形界面，会用临时目录跑一遍完整流程）：

```bash
python3 main.py --selftest
# 输出：selftest ok
```

操作步骤（两种方式任选）：

1. 从 Finder / 资源管理器把**文件夹**直接拖到路径输入框上（输入框上方有小字提示）；或点「浏览...」选择。
2. JPG 文件夹（程序会在其中创建 `raw原图`）和 RAW 文件夹各选一个。
3. 点「开始处理」，等待状态栏变为「完成」。
4. 结果在 `JPG文件夹/raw原图/` 下。路径不会自动清空，可以换一批文件直接再处理。

> 只扫描所选文件夹的顶层文件，不递归子目录，所以输出文件夹 `raw原图` 不会被重复处理。

## 三、打包成单文件可执行程序

PyInstaller **不能跨平台编译**：Windows 上只能打出 `.exe`，macOS 的 `.app` 必须在 Mac 上打。
两个平台的脚本都已备好。

### Windows：`build.bat`

双击 `build.bat`，或在 cmd 里执行：

```bat
build.bat
```

产物：`dist\RAWMatcher.exe`（单文件，约 11MB，双击即用，不弹黑框）。

### macOS：`build.sh`（必须在 Mac 上执行）

```bash
cd 项目目录
bash build.sh
```

产物：`dist/RAWMatcher.app`（单文件，双击即用）。

两个脚本等价于这条命令（注意 `--add-data` 的分隔符：Windows 用 `;`，macOS 用 `:`）：

```bash
python -m PyInstaller --noconfirm --clean --onefile --windowed \
  --name RAWMatcher \
  --collect-all tkinterdnd2 \
  --icon icon.icns \
  --add-data "icon.png:." \
  main.py
```

- `--collect-all tkinterdnd2` 必须加，否则拖拽用的 tkdnd 二进制不会被打进去，一拖就崩。
- 图标：`icon.icns` / `icon.ico` 已随项目提供；改设计只需重新生成：

```bash
python3 make_icon.py     # 需要 pillow，产出 icon.png / icon.ico / icon.icns
```

- 想改显示名称：Windows 直接改 exe 名；macOS 用 Finder 把 `RAWMatcher.app` 重命名。
- 只在当前架构生效：Apple Silicon 上打出的包不能直接在 Intel Mac 运行，反之亦然。
- **打包用 Python 3.12 / 3.13 最稳**。Python 3.14 在 Windows 上打包会遇到
  `Tcl data directory ... not found`（PyInstaller 尚未适配），程序跑源码没问题，只是不能打包。

### 没有 Mac？用 GitHub Actions 云端打包

仓库里已放好工作流 `.github/workflows/build-macos.yml`：

1. 把整个项目推到 GitHub 仓库（`.github/` 目录要一起推）。
2. 打开仓库的 **Actions** 标签页 → 左侧选 **Build macOS App** → 点 **Run workflow**。
3. 几分钟后在该次运行的页面底部 **Artifacts** 下载 `macos-build`（zip，内含 `.app`）。
4. 解压后把 `.app` 拖进「应用程序」，首次打开：右键 → 打开，或到
   `系统设置 → 隐私与安全性` 点「仍要打开」。

工作流相比手写命令多做了一件事：**临时签名**（`codesign --force --deep --sign -`）。
Apple Silicon 上完全未签名的 app 会被系统判为「已损坏」，连右键打开都救不回来。

> `macos-latest` 是 Apple Silicon 机器，产物只能在 M 系列 Mac 上运行；
> 想让 Intel Mac 也能用，把 `runs-on` 改成 `macos-13` 再跑一次。
> 想同时出两个包，把 `runs-on` 换成 `${{ matrix.runner }}` 并加一个 `macos-13` / `macos-latest` 的 matrix。

## 四、常见问题

**1. 双击提示「无法验证开发者」/「Apple 无法检查其是否包含恶意软件」**

这是未签名应用的正常提示，二选一：

- 右键（或 Control + 点击）`.app` → 「打开」→ 在弹窗中再点「打开」。只需做一次。
- 或：先尝试打开一次让它被拦截 → 打开 `系统设置` → `隐私与安全性` → 下滑找到
  「已阻止使用 RAWMatcher...」→ 点「仍要打开」→ 输入密码确认。

命令行方式（确认来源可信再用，会移除隔离标记）：

```bash
xattr -dr com.apple.quarantine /path/to/RAWMatcher.app
```

**2. 提示「RAWMatcher 已损坏，无法打开」**

同上，通常是隔离标记导致，执行上面的 `xattr` 命令即可。

**3. 点击「开始处理」没有反应 / 提示请先选择文件夹**

两个文件夹都必须选择，且程序判断的是实际选择结果而不是输入框文字（输入框是只读显示）。

**4. 日志显示「✗ 复制失败」**

多数是权限或磁盘空间问题：RAW 所在磁盘需可读，JPG 所在磁盘需可写且空间足够。
错误原因会写在日志里。

**5. 中文路径乱码**

Python 3 全程用 `pathlib` 处理路径，统一按系统文件系统编码读写，macOS 上为 UTF-8，
无需额外设置。

**6. 想要更快的速度**

复制速度受磁盘限制（RAW 文件通常 20–80MB）。程序已是单线程顺序复制，未做并行，
避免对机械硬盘/存储卡造成随机读写抖动。

**7. Windows / Linux 上窗口没有系统标题栏？**

这是刻意的：为了和 macOS 一致的观感，非 Mac 平台去掉了系统标题栏并自绘红黄绿三键。
拖动标题栏空白处移动窗口，右下角三道斜线处拖动可缩放，双击标题栏最大化。
拖动标题栏时会显示三键符号，和 macOS 的悬停行为一致。
若哪天觉得别扭，把 `main.py` 里 `_build_ui()` 中的 `if not IS_MAC:` 分支去掉即可恢复系统标题栏。

**8. 拖进去没反应？**

- 只能拖**文件夹**，拖文件会弹「无效路径」并清空该框。
- 启动时日志第一行会写明拖拽是否可用：显示「未安装 tkinterdnd2」就说明依赖缺失，
  执行 `pip install tkinterdnd2` 后重启即可；此时仍可用「浏览」按钮。
- 打包版若一拖就崩，说明打包时漏了 `--collect-all tkinterdnd2`。

**9. 拖入路径两侧多了花括号？**

macOS 上路径含空格时 Finder 会传成 `{/Users/me/My Photos}`，程序会自动去掉花括号，
不需要手动处理。

**10. 换了图标，但 exe 显示的还是旧图标？**

换的是同一个文件路径，Windows 用的是图标缓存。任选一种刷新：

- 把 `RAWMatcher.exe` 复制到别的目录，或改个文件名再看（最快）；
- 重启资源管理器：任务管理器里找到「Windows 资源管理器」→ 重新启动；
- 清缓存后重启：删掉 `%LocalAppData%\IconCache.db` 和 `%LocalAppData%\Microsoft\Windows\Explorer\iconcache_*.db`。

macOS 上同理，Finder 缓存旧图标时改一次文件名或 `touch` 一下 .app 即可。
