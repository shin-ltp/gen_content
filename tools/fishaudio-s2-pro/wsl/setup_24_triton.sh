#!/usr/bin/env bash
set -u
export HSA_ENABLE_DXG_DETECTION=1
export HSA_OVERRIDE_GFX_VERSION=11.0.0
export LD_LIBRARY_PATH=/opt/rocm/lib:/opt/rocm-7.2.4/lib
source /root/fish/venv/bin/activate
export TRITON_CACHE_DIR=/root/.triton_cache
export TORCHINDUCTOR_CACHE_DIR=/root/.inductor_cache
cat > /root/triton_check.py <<'PYEOF'
import sys, time
sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
import torch, triton
import triton.language as tl
print("triton", triton.__version__, flush=True)
print("arch:", torch.cuda.get_device_properties(0).gcnArchName, flush=True)

@triton.jit
def _add(x_ptr, y_ptr, n, BLOCK: tl.constexpr):
    pid = tl.program_id(0)
    offs = pid * BLOCK + tl.arange(0, BLOCK)
    m = offs < n
    tl.store(y_ptr + offs, tl.load(x_ptr + offs, mask=m) + 1.0, mask=m)

x = torch.randn(1024, device="cuda")
y = torch.empty_like(x)
_add[(4,)](x, y, 1024, BLOCK=256)
torch.cuda.synchronize()
print("triton kernel ok:", torch.allclose(y, x + 1), flush=True)

def f(a, b):
    return torch.nn.functional.relu(a @ b + 1)
cf = torch.compile(f, backend="inductor", mode="default", fullgraph=True)
a = torch.randn(1024, 1024, device="cuda", dtype=torch.bfloat16)
b = torch.randn(1024, 1024, device="cuda", dtype=torch.bfloat16)
t0 = time.perf_counter()
out = cf(a, b)
out = cf(a, b)
torch.cuda.synchronize()
print("torch.compile ok in %.1fs" % (time.perf_counter() - t0), flush=True)

# decode-like loop timing: eager vs compiled
def loop(fn, iters):
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(iters):
        fn()
    torch.cuda.synchronize()
    return (time.perf_counter() - t0) / iters * 1000

lin = torch.nn.Linear(4096, 4096, bias=False).cuda().to(torch.bfloat16)
def step():
    global x2
    x2 = lin(x2)
def step():
    global x2
    x2 = lin(x2)
x2 = torch.randn(1, 1, 4096, device="cuda", dtype=torch.bfloat16)
step()  # warm
eager_ms = loop(step, 50)
clin = torch.compile(lambda t: lin(t), backend="inductor", fullgraph=True)
x3 = torch.randn(1, 1, 4096, device="cuda", dtype=torch.bfloat16)
for _ in range(3):
    x3 = clin(x3)
comp_ms = loop(lambda: clin(x3), 50)
print(f"tiny-step eager {eager_ms:.2f} ms vs compiled {comp_ms:.2f} ms", flush=True)
print("TRITON_ALL_OK", flush=True)
PYEOF
timeout 900 python /root/triton_check.py
echo "rc=$?"
echo TRITON_DONE
