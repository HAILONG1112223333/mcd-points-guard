#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
拿到 PAT 后，一条命令完成全部 GitHub 操作 —— 全程走 API，不打开任何网页。

用法:
    python github_setup.py <你的GitHub用户名> ghp_xxxxxxxxxxxx

会依次做：
    1. 创建 PUBLIC 仓库 mcd-points-guard
    2. 上传全部项目文件（走 API contents 端点）
    3. 提交报名 Issue 到官方仓库
"""

import base64, json, os, sys, time, urllib.request, urllib.error, urllib.parse

# Windows 控制台默认 GBK，中文/emoji 会崩，这里兜底
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = "mcd-points-guard"
OFFICIAL = "M-China/mcd-developer-innovation-challenge"
API = "https://api.github.com"

SKIP_DIRS = {".git", "__pycache__", ".idea", ".vscode", "docs"}
SKIP_FILES = {"github_setup.py", "push.sh", ".DS_Store"}

files_cache = []


def req(url, token, method="GET", data=None):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    r = urllib.request.Request(url, data=body, method=method)
    r.add_header("Authorization", "Bearer " + token)
    r.add_header("Accept", "application/vnd.github+json")
    r.add_header("User-Agent", "mcd-points-guard")
    if body:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"message": raw[:400]}


def collect():
    """收集待上传文件（相对路径, 绝对路径）"""
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn in SKIP_FILES:
                continue
            ap = os.path.join(dirpath, fn)
            rel = os.path.relpath(ap, ROOT).replace("\\", "/")
            # 跳过过大的文件
            if os.path.getsize(ap) > 900_000:
                print("  (跳过过大文件) %s" % rel)
                continue
            out.append((rel, ap))
    return sorted(out)


def main():
    """支持两种用法：命令行传参，或直接运行后交互式输入。"""
    if len(sys.argv) >= 3:
        user, token = sys.argv[1], sys.argv[2]
    else:
        print("=" * 58)
        print("  麦麦积分止损官 · 一键上传 GitHub")
        print("=" * 58)
        print("\n下面两项直接粘贴后按回车即可。")
        print("(PAT 是 ghp_ 开头的一整串，粘贴时不要带空格)\n")
        user = input("你的 GitHub 用户名: ").strip()
        token = input("你的 PAT (ghp_ 开头) : ").strip().strip('"').strip("'")
        # 去掉粘贴时可能混入的空白字符
        token = "".join(token.split())
        if not user or not token:
            print("\n✗ 两项都不能为空。")
            sys.exit(1)
        print()

    print("\n[0/3] 验证 PAT 与账号...")
    st, me = req(API + "/user", token)
    if st != 200:
        print("  ✗ PAT 无效 (%s): %s" % (st, me.get("message")))
        sys.exit(1)
    login = me.get("login")
    print("  ✓ 已登录: %s" % login)
    if login.lower() != user.lower():
        print("  ⚠ 用户名不符（你填 %s，PAT 属于 %s），以 PAT 为准" % (user, login))
        user = login
    repo_url = "https://github.com/%s/%s" % (user, REPO)

    print("\n[1/3] 创建 PUBLIC 仓库 %s ..." % REPO)
    st, r = req(API + "/user/repos", token, "POST", {
        "name": REPO,
        "description": "🍟 麦麦积分止损官 — 算出你的麦当劳积分有多少正在过期、每100积分值多少钱、怎样刚好花完不浪费",
        "homepage": "",
        "private": False,
        "has_issues": True,
        "has_wiki": False,
        "auto_init": False,
    })
    if st == 201:
        print("  ✓ 仓库已创建: %s" % repo_url)
    elif st == 422 and "already exists" in json.dumps(r, ensure_ascii=False):
        print("  ✓ 仓库已存在，复用: %s" % repo_url)
    else:
        print("  ✗ 创建失败 (%s): %s" % (st, r.get("message")))
        sys.exit(1)

    print("\n[2/3] 上传文件...")
    files = collect()
    # GitHub 限制 push 上限约 100MB/tree，这里逐文件 PUT
    ok, fail = 0, []
    for rel, ap in files:
        try:
            with open(ap, "rb") as f:
                content = base64.b64encode(f.read()).decode("ascii")
        except Exception as e:
            fail.append((rel, str(e)))
            continue
        rel_q = urllib.parse.quote(rel, safe="/")
        url = "%s/repos/%s/%s/contents/%s" % (API, user, REPO, rel_q)
        # 文件已存在时必须带 sha，否则 422 "sha wasn't supplied"
        _, cur = req(url)
        payload = {"message": "feat: 麦麦积分止损官 - 积分汇率体检与止损凑单", "content": content}
        if isinstance(cur, dict) and cur.get("sha"):
            payload["sha"] = cur["sha"]
        st, r = req(url, token, "PUT", payload)
        if st in (200, 201):
            ok += 1
            print("  ✓ %s" % rel)
        else:
            fail.append((rel, "%s %s" % (st, r.get("message", "")[:80])))
            print("  ✗ %s  (%s)" % (rel, st))
        time.sleep(0.15)   # 温和限速，避免触发 secondary rate limit

    print("\n  上传完成：成功 %d，失败 %d" % (ok, len(fail)))
    for rel, why in fail:
        print("    - %s : %s" % (rel, why))

    print("\n[3/3] 提交报名 Issue 到官方仓库...")
    title = "【参赛申请】麦麦积分止损官"
    body = (
        "项目名称：麦麦积分止损官\n"
        "项目地址：%s\n"
        "项目简介：基于麦当劳官方 MCP，算出你的积分有多少正在过期、每 100 积分到底值多少钱、"
        "以及怎样把积分刚好花完不浪费。实测发现：积分汇率在不同商品间差 5 倍，"
        "积分商城 70%% 的商品其实已过期换不了，同样积分「会换」与「不会换」差 2.44 倍。\n"
        "使用工具：now-time-info / query-my-account / query-nearby-stores / mall-points-products / query-meals\n"
    ) % repo_url
    st, r = req("%s/repos/%s/issues" % (API, OFFICIAL), token, "POST", {"title": title, "body": body})
    if st == 201:
        print("  ✓ 报名 Issue 已提交: %s" % r.get("html_url"))
    else:
        print("  ✗ Issue 提交失败 (%s): %s" % (st, r.get("message", "")[:200]))
        print("    请手动到 https://github.com/%s/issues/new 提交" % OFFICIAL)

    print("\n" + "=" * 58)
    print("  仓库地址: %s" % repo_url)
    print("=" * 58)
    print("\n下一步：")
    print("  1. 打开仓库页面确认 Public + README 渲染正常")
    print("  2. Settings → Pages → Source 选 main / root，开在线试玩页")
    print("  3. 用完后记得去 https://github.com/settings/tokens 删掉这个 PAT")


if __name__ == "__main__":
    main()
