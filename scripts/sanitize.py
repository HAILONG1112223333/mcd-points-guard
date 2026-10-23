#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脱敏工具 —— 公开仓库前必跑。

清洗手机号、详细地址、Token、邮箱、订单号、经纬度精度。

用法:
    python scripts/sanitize.py data/sample            # 原地脱敏整个目录
    python scripts/sanitize.py data/sample/account.json  # 单文件
"""

import json
import os
import re
import sys

RULES = [
    (r"1[3-9]\d{9}", "<PHONE>"),                      # 手机号
    (r"\b\d{6}\b(?=\D*?[市区])", "<ADDR_CODE>"),        # 邮编
    (r"Bearer\s+[A-Za-z0-9._\-]{8,}", "Bearer <TOKEN>"),
    (r"(?i)\b(token|access[_-]?token)\b\s*[:=]\s*[\"']?[A-Za-z0-9._\-]{8,}[\"']?", r"\1: <REDACTED>"),
    (r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "<EMAIL>"),
    (r"\b\d{16,}\b", "<ORDER_NO>"),                    # 长订单号
]

# 这些字段值直接替换（不依赖正则）
FIELD_RULES = {
    "address": "<ADDRESS>", "addressDetail": "<ADDRESS>", "detailAddress": "<ADDRESS>",
    "receiverName": "<NAME>", "contactName": "<NAME>", "userName": "<NAME>",
    "phone": "<PHONE>", "mobile": "<PHONE>", "phoneNumber": "<PHONE>",
    "latitude": 0.0, "longitude": 0.0, "lat": 0.0, "lng": 0.0,
}


def scrub_text(s):
    if not isinstance(s, str):
        return s
    for pat, rep in RULES:
        s = re.sub(pat, rep, s)
    return s


def scrub(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in FIELD_RULES and v not in (None, "", 0):
                out[k] = FIELD_RULES[k]
            else:
                out[k] = scrub(v)
        return out
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    if isinstance(obj, str):
        return scrub_text(obj)
    return obj


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    target = sys.argv[1]
    targets = []
    if os.path.isdir(target):
        for root, _, files in os.walk(target):
            for fn in files:
                if fn.endswith(".json"):
                    targets.append(os.path.join(root, fn))
    else:
        targets = [target]

    for p in targets:
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print("跳过 %s (%s)" % (p, e))
            continue
        cleaned = scrub(data)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)
        print("脱敏完成: %s" % p)

    print("\n⚠ 脱敏只覆盖常见模式。发布前请再人工 grep 一遍：")
    print("   grep -rEn '1[3-9][0-9]{9}|Bearer |token' data/ *.md")


if __name__ == "__main__":
    main()
