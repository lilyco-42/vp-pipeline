#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""列出 OpenRouter 免费模型，并实测中文写作可用性，给出推荐 slug。"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HIST = os.path.expanduser("~/.bash_history")
CANDIDATES = [
    "z-ai/glm-5.2:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "inclusionai/ling-3.0-flash-vl:free",
    "inclusionai/ling-3.0-flash-fin:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "thinkingmachines/inkling:free",
    "nex-agi/nex-n2.5-pro:free",
    "dots-studio/dots-3-note-preview:free",
]


def get_key():
    text = open(HIST, "r", errors="replace").read()
    keys = re.findall(r"sk-or-v1-[A-Za-z0-9]{16,}", text)
    if not keys:
        sys.exit("history 中无 key")
    return keys[-1]


def api(path, key, payload=None, timeout=60):
    url = "https://openrouter.ai/api/v1/" + path
    headers = {"Authorization": "Bearer " + key}
    if payload is None:
        req = urllib.request.Request(url, headers=headers)
    else:
        headers["Content-Type"] = "application/json"
        headers["HTTP-Referer"] = "https://github.com/"
        headers["X-Title"] = "vp-pipeline"
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return False, "HTTP %s %s" % (e.code, e.read().decode("utf-8", "replace")[:160])
    except Exception as e:
        return False, str(e)


def try_chat(key, model, prompt, max_tokens=80):
    ok, data = api(
        "chat/completions",
        key,
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.8,
        },
        timeout=90,
    )
    if not ok:
        return False, data
    if isinstance(data, dict) and "error" in data:
        return False, str(data["error"])[:160]
    try:
        message = data["choices"][0]["message"]
    except Exception:
        return False, "结构异常 " + json.dumps(data)[:160]
    msg = message.get("content") or message.get("reasoning") or ""
    if not msg.strip():
        return False, "空内容 finish_reason=%s" % data["choices"][0].get("finish_reason")
    return True, msg.strip().replace("\n", " ")[:70]


def main():
    key = get_key()
    print("key: sk-or-v1-...%s\n" % key[-4:])

    ok, data = api("models", key, timeout=45)
    if not ok:
        sys.exit("取模型列表失败: %s" % data)
    free = []
    for m in data.get("data", []):
        p = m.get("pricing", {})
        try:
            if float(p.get("prompt", "1")) == 0.0 and float(p.get("completion", "1")) == 0.0:
                free.append(m["id"])
        except Exception:
            continue
    print("免费模型 %d 个:" % len(free))
    for m in sorted(free):
        print("   ", m)

    prompt = "用一句中文口播开场白介绍主题「单板机自托管」，20字以内，只输出这句话。"
    print("\n中文写作实测:")
    results = []
    for m in CANDIDATES:
        if m not in free:
            print("    %-52s SKIP(不在免费列表)" % m)
            continue
        ok, info = try_chat(key, m, prompt)
        print("    %-52s %s %s" % (m, "OK" if ok else "FAIL", info))
        if ok:
            results.append(m)
        time.sleep(1)

    print("\n==== 可用模型（按候选优先级） ====")
    for m in results:
        print("   ", m)
    if results:
        print("\n推荐:", results[0])


if __name__ == "__main__":
    main()
