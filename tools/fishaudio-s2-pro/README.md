# fish-speech S2-Pro — Radeon 780M (gfx1103) Windows 原生 GPU 服务

mac fishaudio 的本地备份。两条路线均已端到端跑通：

- **Windows 原生 ROCm（eager）**：下文「快速启动」，稳态 1346 ms/tok，零额外配置。
- **WSL2 + torch.compile + 真 int8 权重（推荐，快 4.2 倍）**：稳态 **317-338 ms/tok**，见「WSL2 + compile 加速路线」。需一次性配置 `.wslconfig`，新计算图首请求有编译等待（缓存命中后 ~143s，同会话内第 2 个请求即回稳态）。

> **us-stock-daily 已默认接入本 WSL2 链路**：`us-stock-daily/tools/tts/generate_audio.py <日期>` 的
> `auto` 模式会自动探测 `http://127.0.0.1:8080/v1/tts`，可达即走本地（需本 README 的 WSL2 服务器在跑），
> 不可达自动回落 Mac MLX SSH。详见 [us-stock-daily/tools/tts/README.md](</C:/my_project/gen-contents/us-stock-daily/tools/tts/README.md:1>)。

## 快速启动

```powershell
cd fish-speech
.\start_server_gpu.ps1        # 监听 127.0.0.1:8080，启动约 3 分钟
```

测试：`.\test_tts.ps1`（约 110s 出 3-4s 日语语音）。CPU 备份版仍可用 `start_server.ps1`。

## 关键设计（针对 780M + 32GB 内存）

- **int8 ckpt 加载后 dequant 为 bf16 常驻 GPU**（201 层）：decode 5.7s/tok(CPU) → 3.2(int8 原生) → **1.32-1.36 s/tok**。
- **GPU_RESIDENT=1（默认）**：LLM(~11GB) 常驻 GPU，DAC 解码器跑 CPU（90 token 仅 3-7s）。避免了 LLM↔DAC 各 41s 的 PCIe 乒乓——32GB 机器上桌面程序占内存后，11GB 的 offload 会掉进 pagefile（实测 0.26 GB/s）。
- **MAX_SEQ_LEN=2048 + VRAM_FRACTION=0.98**：KV cache 因无 triton int4 kernel 回退 16bit，需压缩序列预算；13.83/14.1GB 实测稳定。
- **LLM_TIMEOUT=1200（默认）**：130 字符日文 ≈ 500-550 audio token ≈ 700s decode，旧值 600 会中途 500（已实测踩中）。
- 控制台日志设 PYTHONIOENCODING=utf-8:replace，否则 cp932 主机上 prompt 可视化会崩。
- **gfx1103 补丁**（`fish_speech/utils/rocm_gfx1103.py`）：eager snake 激活 + 膨胀 Conv1d 逐 tap addmm，绕开 HIPRTC JIT 与 MIOpen conv 缺陷。
- COMPILE=1 在 Windows ROCm 上不可用（torch 2.9 无 win triton wheel），脚本会警告并回退 eager。

## 性能（稳态，两次复测一致）

| 阶段 | 耗时 |
|---|---|
| prefill (37 tok) | 1.3-2.9s |
| decode | 1324-1361 ms/tok（有效带宽 3.4 GB/s） |
| DAC 解码 (CPU, 74-79 tok) | 2.3-3.1s |
| **端到端（~3.5s 音频）** | **105-111s** |
| 长文实测（122 字，510 tok） | 706s → 23.7s 音频，decode 1346ms/tok |

RTF ≈ 28-30x。130 字符上限的单段合成约需 12-13 分钟；建议按句拆成多个短句请求排队跑，总时长不变但可边出边验。

## WSL2 + compile 加速路线（int8 直用 4.2x）

librocdxg 1.2 起 780M(gfx11.0.3) 进入 WSL2 ROCm 支持列表，且 WSL 侧可用 triton → `--compile` 生效（Windows 原生无 win triton wheel，做不到）。实测对比（同为 xiaomei、同一 122 字日语文本）：

| 路线 | 稳态 decode | GPU 显存 | 首请求等待 |
|---|---|---|---|
| Windows 原生 eager（bf16 常驻） | 1346 ms/tok | ~14.1 GB | ~3 min 启动 |
| WSL2 eager（bf16 常驻） | 2023 ms/tok | — | ~3 min 启动（不推荐） |
| WSL2 compile + bf16 常驻 | 595-621 ms/tok | 14.39 GB | 冷编译 ~400s；磁盘缓存命中后 ~143s |
| **WSL2 compile + int8 直用**（`SKIP_GFX1103_FIX=1`） | **317-338 ms/tok** | **6.74 GB** | 换图需重新编译 ~475s；之后第 2 个请求即 36.5s 稳态 |

int8 直用长文实测：122 字 → 430 tok，decode 140.7s（**327 ms/tok**），e2e **163.9s**（含 VQ decode 21.9s）。130 字符上限 ≈550 tok ≈ **3 分钟**出成品。int8 输出音频规格与 bf16 一致（44.1kHz mono 16bit、RMS 相当），A/B 样音在 `out/xiaomei_*_int8_compile.wav`，主观音质待人工确认后再全面切产。

### 配置要点

- `C:\Users\<user>\.wslconfig`（**必需**，默认 WSL 内存配额不够会 OOM）：
  ```ini
  [wsl2]
  memory=24GB
  processors=16
  swap=8GB
  ```
  改后 `wsl --shutdown` 生效。生成脚本：`wsl/write_wslconfig.ps1`。
- WSL 内仓库 `/root/fish/fish-speech`（与 Windows 侧补丁同步，含 `rocm_gfx1103.py`），ckpt 同为 int8。
- 关键环境变量：`HSA_OVERRIDE_GFX_VERSION=11.0.0`（ROCm 7 官方列表暂无 11.0.3，走 gfx1100 通用 kernel + triton 融合，仍能赢原生）、`TRITON_CACHE_DIR=/root/.triton_cache`、`TORCHINDUCTOR_CACHE_DIR=/root/.inductor_cache`（跨重启复用，勿删）。
- 当前生产配置：`SKIP_GFX1103_FIX=1 COMPILE=1 bash /root/setup_28.sh`（int8 直用，显存仅 6.74GB；含防自杀 pkill）。就绪探测 `bash /root/wait_up.sh`，bench `bash /root/run_bench.sh <smoke|long>`；int8 A/B 脚本 `run_int8_ab.sh`。
- `SKIP_GFX1103_FIX=1`：跳过 pre-dequant，int8 权重直接进 triton 融合图（等价 mac MLX INT8 思路）。与 bf16 常驻是**两张不同的编译图**，切换后首请求重新编译（~475s），各自的磁盘缓存独立。
- 注意：日志里的 `Bandwidth achieved` 是按 ckpt 名义大小（INT8 3.6GB）算的，int8 直用路径显示 1.3-1.6 GB/s 并不代表低效，真实每层搬运量≈bf16 路径。
- 注意：日志里的 `Compilation time:` 是该请求总耗时（generate 后无条件打印），不是纯编译时间；真正的编译成本 = 首请求 − 稳态请求。
- 所有跑 python 的脚本必须先 `export PATH="/root/fish/venv/bin:$PATH"`，否则静默失败。

### 采样率与性能（结论：不动采样率）

语言节目降采样率（如 24kHz 广播档）的调研结论：

- **decode 与采样率无关**。LLM 每 token 固定 ~0.44s 音频，降采样率不减少 token 数，而 decode 占 e2e 的 ~90%。
- 唯一受益的是 DAC 声码器（当前 e2e 的 ~13%，21.9s/163.9s），但 modded_dac_vq 的 44.1kHz 是 ckpt 硬约束（`preprocess` 里 `assert sample_rate == self.sample_rate`），接口无输出采样率参数；改成先低采样率生成再重采样既无官方支持又损音质。
- mac 管线同样输出 44.1kHz mono（`tts_config.py` 注明为 Remotion 要求），并未靠降采样率提速。它的速度来自 MLX INT8 权重直用 + Apple 统一内存高带宽——本方案 int8 直用后已对齐该思路。
- 若在意成品分发体积/带宽，应在**最终 mp3 封装环节**降码率，与本服务性能无关。

### 剩余优化方向

- bf16 vs int8 音质人工 A/B（样音已备）；若 int8 可接受则维持现状，省一半显存还更快。
- AMD 后续驱动/ROCm 版本原生支持 11.0.3 后可去掉 `HSA_OVERRIDE_GFX_VERSION` 再测。

## 780M ROCm 支持调研（librocdxg / Phoronix）

- AMD 官方 Windows 驱动经 **librocdxg**（DXG  thunk 层）向 ROCm 暴露集显；v1.2.0 (2026-05) 起 gfx11.0.3 (780M) **正式进入 WSL2 ROCm 支持列表**，最新 1.2.2 (2026-08)。需 ROCm 7.2.x/7.13/7.14 + 对应驱动；ROCm-on-WSL 不支持 profiler/debugger。
- 本机 Windows 原生已用 `torch 2.9.1+rocm7.13` + `amd-torch-device-gfx1103` 多架构包跑通；WSL2 路线（见上节）也已验证可用且因 triton compile 更快，两条路线按需选用。

## 环境

- venv：`rocm-env2`（torch 2.9.1+rocm7.13.0 multi-arch；旧 `rocm-env` ~5GB 已弃用，可手动删除）
- ckpt：`checkpoints/fish-speech-s2-pro-int8`（model.pth 5.1GB int8 + codec.pth 1.9GB）
- 重启/排查：`fish-speech/_restart_gpu.ps1`、日志 `fish-speech/_gpu_server.err.log`、`_grep.py`/`_sed.py`/`_wav_check.py` 为保留的小工具
