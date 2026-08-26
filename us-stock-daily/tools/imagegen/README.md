# us-stock-daily 文生图工具

为番组提供统一文生图能力。默认使用阿里云 DashScope 的 **qwen-image-3.0-pro**，
不可用（无密钥/网络不可达/内容审核拒绝）时自动回退到本地 Mac 上的 **ComfyUI FLUX2**。

## 用法

```bash
cd us-stock-daily/tools/imagegen
python imagegen.py "NVDA 数据中心 概念图" -o out/nvda.png
python imagegen.py "概念图" -o out/nvda.png --provider comfyui   # 强制走 Mac FLUX2
```

`--out` 为输出 PNG 路径。默认输出统一调整为 768x1024（竖版），符合番组画面规格。

## 环境变量

复制 `tools/imagegen/.env.template` 到项目根 `us-stock-daily/.env`（已 gitignore），
填入实际值。关键项：

- `QWEN_IMAGE_API_KEY`：DashScope API Key（qwen-image 主 provider 必需）
- `COMFYUI_REMOTE_HOST`：Mac 机 SSH 目标（如 `you@192.168.x.x`），需免密 SSH
- `COMFYUI_OUTPUT_DIR`：Mac 上 ComfyUI 输出目录，用于 SCP 取回图片

`IMG_GENERATION_PROVIDER=qwen`（默认）与 `IMG_GENERATION_FALLBACK=1` 组合时，
主 provider 失败自动尝试备选。可设为 `comfyui` 强制走 Mac。

## 依赖

- Python 3.11+
- Pillow
- python-dotenv

## 与 Phase 3 的集成

Phase 3（asset-fetcher-agent）需要「概念图・抽象插画」时，可调用
`imagegen.py` 生成概念图，弥补实景照片/logo 之外的空白（vision-design.md §0.6 允许象征性配图）。
