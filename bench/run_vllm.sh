#!/bin/bash

vllm serve google/gemma-3-27b-it \
    --enable-lora \
    --lora-module lora=/home/siamai/llmtune/LLaMA-Factory/MonkeyReasonerExport \
    --tensor-parallel-size 8 \
    --max-model-len 8192 \
    --port 2124
