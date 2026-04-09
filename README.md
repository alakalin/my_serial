# 串口助手（Windows）

一个基于 `PySide6 + pyserial` 的 Windows 串口调试工具，支持多标签、多串口、时间戳、HEX 收发、关键字搜索与高亮。

## 功能特性

- 串口参数配置：端口、波特率、数据位、停止位、校验位
- 多标签连接串口：单标签全屏、双标签左右并行
- 文本/HEX 收发模式切换
- 接收/发送时间戳显示（毫秒）
- 中文编码支持（默认 `gbk`，可切 `gb18030` / `utf-8`）
- 接收区关键字搜索（上一个/下一个）
- 关键字高亮与清除高亮
- 自动滚动开关（接收区）
- 定时发送

## 项目结构

- `main.py`：主程序入口
- `requirements.txt`：Python 依赖
- `SerialAssistant.spec`：PyInstaller 打包配置（onefile + 图标）
- `assets/app.png`：原始图标
- `assets/app.ico`：打包图标（由 png 转换）
- `.gitignore`：Git 忽略规则

## 本地开发运行

```bash
pip install -r requirements.txt
python main.py
```

## 打包（onefile）

已在 `SerialAssistant.spec` 中配置：
- 产物名：`SerialAssistant_onefile.exe`
- 图标：`assets/app.ico`
- 模式：`onefile`

执行打包：

```bash
pyinstaller --noconfirm --clean SerialAssistant.spec
```

打包产物：

- `dist/SerialAssistant_onefile.exe`


## 环境信息

- Python 3.11
- PySide6 6.9.1
- pyserial 3.5
- PyInstaller 6.19.0
