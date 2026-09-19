# us-stock-daily 文生图工具

为番组提供统一文生图能力。默认使用阿里云 DashScope 的 **qwen-image-3.0-pro**，
默认 provider 是 `qwen`；`IMG_GENERATION_FALLBACK=0` 时必须禁用 Mac ComfyUI FLUX2 回退。

## 用法

```bash
cd us-stock-daily/tools/imagegen
python imagegen.py "NVDA 数据中心 主题图" -o out/nvda.png
```

`--out` 为输出 PNG 路径。默认输出统一调整为 768x1024（竖版），符合番组画面规格。

## 环境变量

复制 `tools/imagegen/.env.template` 到项目根 `us-stock-daily/.env`（已 gitignore），
填入实际值。关键项：

- `QWEN_IMAGE_API_KEY`：DashScope API Key（qwen-image 主 provider 必需）
`COMFYUI_REMOTE_HOST` / `COMFYUI_OUTPUT_DIR` 仅在显式允许 Mac fallback 的旧流程中使用；
当前日常任务禁止给 Mac 发送生成任务。

`IMG_GENERATION_FALLBACK=1` 时，主 provider 失败才尝试备选；当前日常任务必须设为 `0`。

## 依赖

- Python 3.11+
- Pillow
- python-dotenv

## 与 Phase 3 的集成

Phase 3（asset-fetcher-agent）需要「テーマ画像・抽象插画」时，可调用
`imagegen.py` 生成主题图，弥补实景照片/logo 之外的空白（vision-design.md §0.6 允许象征性配图）。
