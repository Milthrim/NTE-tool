# NTE-tool · 异环小游戏助手(记得右键以管理员身份运行，不然可能没效果）

用于异环「甜蜜大摆圈」小游戏的 Windows 桌面工具：识别画面中的方向提示，执行点按、长按和连按；每局达到或超过 **9000 分**后停手，等待结算并按设置重新开始。
<img width="612" height="598" alt="image" src="https://github.com/user-attachments/assets/578cf173-c48b-4de8-9d3c-15b474ac4dc1" />

## 下载与使用

在 [Releases 下载页](https://github.com/pengyingqi2004/Net-tool/releases/latest) 下载 Windows 64 位版本。独立 EXE 已包含运行环境，无需安装 Python。

1. 解压压缩包并双击 `异环小游戏助手.exe`，或直接运行单独下载的 EXE。
2. 进入小游戏的开始或重试界面，按 **F8** 启动。启动后有 3 秒切回游戏。
3. **F8** 暂停或继续，**F9** 停止并释放方向键。
4. 运行局数填 **0** 表示持续循环；填正整数会在对应局数结算后停止。

游戏需保持前台，使用至少 1280×720 的 16:9 画面。自动重开每局消耗界面标示的 500 游戏币。画面卡顿或遮挡可能造成漏判；工具不会修改游戏内存或强制修改分数。

详细说明见 [使用文档](docs/usage.md)。历史两局实测为 9078、9015 分，见 [验证记录](docs/gameplay-validation.txt)；这不保证每局都能达到同样结果。

## 项目结构

```text
src/                    界面、识别、按键状态机与模板
  app.py                程序入口
  vision.py             方向、颜色、分数、按钮识别
  controller.py         按键、目标分数、结算重开逻辑
  native.py             Windows 截图与键鼠输入
  assets.npz            识别模板
build.py                独立 EXE 构建脚本
requirements*.txt       运行与构建依赖
tests/                 状态机回归检查
docs/                  使用与验证文档
third_party_licenses/   第三方依赖许可
.github/workflows/      Windows 构建和发布流程
```

## 从源码运行或构建

使用 Windows 64 位和 Python 3.13，在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe tests/check_controller.py
.\.venv\Scripts\python.exe src/app.py
.\.venv\Scripts\python.exe build.py
```

构建产物：`dist/异环小游戏助手.exe`。正常启动处于待启动状态，不会立即操作游戏。

```powershell
& .\dist\异环小游戏助手.exe --self-test "$PWD\self-test.json"
```

自检仅验证依赖、模板、空白画面识别和 GUI 初始化，不给游戏发送输入。运行日志位于 EXE 同目录。

## 自动发布

修改 `VERSION` 为新的版本号并推送到 `main`，或在 Actions 中手动执行 **Build Windows release**。流程先进行状态机检查、打包和 EXE 自检，再发布单文件 EXE、包含源码的 ZIP 和 SHA256 校验文件到 GitHub Releases。

第三方依赖的许可见 `third_party_licenses/`。
