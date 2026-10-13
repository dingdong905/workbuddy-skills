---
name: rapidocr-image-ocr
description: 本地图片文字识别（RapidOCR + onnxruntime，PP-OCR 模型，纯本地推理）。**用户发送/粘贴图片即触发，无需明说 OCR**——尤其当读图报错 "Current model does not support reading images"（如 yicloud 中转的 custom-local:GLM）时必须立即降级到本 skill 完成识别；也用于离线/批量/带置信度 OCR，或 ocr-extractor-zh 的 vision/winrt/tesseract 引擎均不可用的兜底。适用于截图、照片、扫描件的中英文识别。
triggers:
  - 发送图片
  - 粘贴图片
  - 图片
  - 截图
  - OCR
  - 识别图片
  - 读图
  - 图片转文字
  - 截图文字
  - 看不了图片
  - 识别文字
agent_created: true
---

# RapidOCR 本地图片文字识别

纯本地 OCR（onnxruntime CPU 推理，PP-OCR 检测+识别模型内置于 wheel），不依赖任何模型的多模态能力，不联网、不出域。

## 零、触发时机（重要）

1. **用户发送/粘贴图片即触发**：会话中出现图片（剪贴板粘贴、@引用、本地路径），无需用户说"识别/OCR"，直接识别并返回文字
2. **模型读图失败自动降级**：Read 图片报 `Current model ... does not support reading images` 时，不要回复"看不了图"，立即改用本 skill 识别
3. 模型能直读图片时，仍可选用本 skill（需要置信度/批量/离线时）

## 一、环境

专用 venv + 12 个依赖包（本机路径、版本清单、离线重建方法见 `example/env.md`）。

## 二、用法

```bash
# <OCR_PY> = 专用 venv 的 python 解释器，路径见 example/env.md
"<OCR_PY>" "${CODEBUDDY_SKILL_DIR}/scripts/run_rapidocr.py" 图片路径

# 只输出纯文本
"<OCR_PY>" "${CODEBUDDY_SKILL_DIR}/scripts/run_rapidocr.py" 图片路径 --lines
```

- 首次调用加载模型约 5~15 秒，之后同进程复用
- 结果按版面从上到下排序；置信度 < 0.7 的行建议人工核对
- 大图（> 4000px）会自动按长边缩放，无需预处理
- 实测样例见 `example/case-2026-10-08.md`

## 三、与 ocr-extractor-zh 的分工

| | ocr-extractor-zh | 本 skill |
|---|---|---|
| 引擎 | vision / winrt / tesseract | RapidOCR (PP-OCR) |
| 本机状态（2026-10-08） | 三引擎均不可用（winrt 缺 zh-CN 语言包） | 已实测可用 |
| 适用 | 装好语言包/tesseract 后的 macOS/Windows | 本机兜底首选 |

winrt 语言包补装（需管理员）：`Add-WindowsCapability -Online -Name "Language.OCR~~~zh-CN~0.0.1.0"`

## 四、限制

- 单张图识别，批量请循环调用或改造脚本
- 不还原表格结构，按文本行输出
- 手写体识别效果一般；印刷体/屏幕字体效果好
