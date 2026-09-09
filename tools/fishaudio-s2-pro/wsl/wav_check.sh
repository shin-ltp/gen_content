#!/bin/bash
# Quick sanity check of output wavs: rate, duration, RMS.
export PATH=/root/fish/venv/bin:$PATH
python /root/wav_check.py "$@"
