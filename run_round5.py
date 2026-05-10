#!/usr/bin/env python3
import os
import sys
import subprocess

if __name__ == "__main__":
    os.chdir(r"d:\CODE\aitext")
    cmd = [
        "python", "scripts\\evaluation\\run_evaluation_round.py",
        "--round", "5",
        "--num_chapters", "5",
        "--title", "残经录",
        "--output_eval_report", "novelist",
        "--output_eval_report", "guardrails",
        "--llm_provider", "gpt4",
        "--llm_base_url", "https://api.chatfire.cn/v1",
        "--llm_model", "gpt-4",
        "--llm_max_tokens", "4000",
        "--llm_temperature", "0.85",
        "--optimization_mode", "writing"
    ]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    print(f"Exit code: {result.returncode}")