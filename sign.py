# -*- coding: utf-8 -*-
"""哈小海自动签到：按浏览器抓到的登录 / 签到 / 查询 URL 和字段执行。

依赖：requests, beautifulsoup4
GitHub Actions Secrets：VIP_USER, VIP_PASS
"""
import datetime
import json
import os
import re
import sys
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BASE = "https://www.haxiaohaios2.com"
# 浏览器 Network 确认：登录 POST 带 action=index&t=；不要退回无查询参数的 URL。
LOGIN_URL = BASE + "/aspx3/mobile/login.aspx?action=index&t="
SIGN_URL = BASE + "/aspx3/mobile/qiandao.aspx"
CHECK_URL = BASE + "/ashx/Honor.ashx"

session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
})


def path(url):
    # 诊断中仅输出路径，不输出查询参数、Cookie 或令牌。
    return urlsplit(url).path


def same_site(url):
    u = urlsplit(url)
    return u.scheme == "https" and u.hostname == urlsplit(BASE).hostname


def parse_page(r):
    return BeautifulSoup(r.content, "html.parser")


def page_error(r, soup=None):
    soup = soup if soup is not None else parse_page(r)
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    return ("genericerrorpage" in path(r.url).lower()
            or "404" in title
            or r.status_code == 404)


def show_page(label, r):
    soup = parse_page(r)
    title = soup.title.get_text(" ", strip=True) if soup.title else "无标题"
    print(f"🌐 {label}: HTTP {r.status_code} | {path(r.url)} | {title[:60]}", flush=True)
    return soup


def checked(r, label):
    soup = show_page(label, r)
    r.raise_for_status()
    if not same_site(r.url):
        raise RuntimeError(f"{label}跳转到非本站地址，停止操作")
    if page_error(r, soup):
        raise RuntimeError(f"{label}实际返回了网站错误页（HTTP 200 也可能是假 404）")
    return soup


def hidden_fields(soup):
    # 保留动态生成的 VIEWSTATE、VIEWSTATEGENERATOR、EVENTVALIDATION 等。
    data = {}
    for tag in soup.select("input[name]"):
        name = tag["name"]
        if tag.get("type", "").lower() == "hidden" or name.startswith("__"):
            data[name] = tag.get("value", "")
    return data


def login():
    user = os.getenv("VIP_USER")
    pwd = os.getenv("VIP_PASS")
    if not user or not pwd:
        raise RuntimeError("未读取到 VIP_USER / VIP_PASS；请检查 GitHub Actions Secrets")

    print("🔐 获取登录表单", flush=True)
    r = session.get(LOGIN_URL, timeout=20)
    soup = checked(r, "登录页")
    data = hidden_fields(soup)
    if "__VIEWSTATE" not in data:
        raise RuntimeError("登录页缺少 __VIEWSTATE；请核对 HTML 是否仍为 ASP.NET 登录页")

    # 以下 4 个字段来自你原来能够提交登录的代码和浏览器的实际 Payload。
    data.update({
        "__EVENTTARGET": "btnLogin",
        "__EVENTARGUMENT": "",
        "txtUser_sign_in": user,
        "txtPwd_sign_in": pwd,
    })
    print("📨 提交登录表单（含 action=index&t=）", flush=True)
    r = session.post(
        LOGIN_URL, data=data,
        headers={"Referer": LOGIN_URL, "Origin": BASE},
        timeout=20, allow_redirects=True,
    )
    # 浏览器抓到的是 302 -> usercenter.aspx?action=index。
    if r.history:
        print("↪️ 登录跳转: " + " → ".join(
            f"{x.status_code} {path(x.url)}" for x in r.history
        ) + f" → {r.status_code} {path(r.url)}", flush=True)
    checked(r, "登录响应")

    # 不把 POST 200 或普通 login/prelogin 页面误判成登录成功。
    if not path(r.url).lower().endswith("/usercenter.aspx"):
        raise RuntimeError(
            "未进入浏览器登录成功时的 usercenter.aspx；"
            "可能是登录失败、验证码/验证要求或服务器根据会话返回了其他页面"
        )
    print("✅ 登录成功：已进入 usercenter.aspx", flush=True)


def signed_today(obj):
    """返回 True / False / None：只有明确字段才能证明签到状态。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() == "signedtoday":
                if isinstance(v, bool):
                    return v
                if str(v).strip().lower() in ("true", "false"):
                    return str(v).strip().lower() == "true"
        for v in obj.values():
            found = signed_today(v)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = signed_today(v)
            if found is not None:
                return found
    return None


def check():
    print("🔎 查询今日签到状态", flush=True)
    month = datetime.datetime.now(ZoneInfo("Asia/Shanghai")).month
    r = session.post(
        CHECK_URL,
        data={"control": "list2", "nowmonth": str(month)},
        headers={
            "Referer": SIGN_URL,
            "Origin": BASE,
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=20,
    )
    checked(r, "签到状态接口")
    try:
        obj = r.json()
        # 兼容 JSON 本身为字符串的情况。
        if isinstance(obj, str):
            try:
                obj = json.loads(obj)
            except ValueError:
                pass
        value = signed_today(obj)
    except ValueError:
        m = re.search(r'"signedToday"\s*:\s*"?(true|false)"?', r.text, re.I)
        value = m.group(1).lower() == "true" if m else None
    if value is True:
        print("🎉 网站确认：今日已签到", flush=True)
    elif value is False:
        print("📅 网站确认：今日尚未签到", flush=True)
    else:
        print("⚠️ 接口未返回可识别的 signedToday，不能断言签到状态", flush=True)
    return value


def sign():
    print("📅 获取签到页", flush=True)
    r = session.get(SIGN_URL, headers={"Referer": BASE + "/aspx3/mobile/usercenter.aspx?action=index"}, timeout=20)
    soup = checked(r, "签到页")
    if not path(r.url).lower().endswith("/qiandao.aspx"):
        raise RuntimeError("签到页未到达 qiandao.aspx，可能是会话过期或被重定向")
    data = hidden_fields(soup)
    if "__VIEWSTATE" not in data:
        raise RuntimeError("签到页缺少 __VIEWSTATE，无法按浏览器抓包提交签到")
    data.update({"__EVENTTARGET": "_lbtqd", "__EVENTARGUMENT": ""})

    print("📨 按浏览器抓包提交 _lbtqd 签到事件", flush=True)
    r = session.post(
        SIGN_URL, data=data,
        headers={"Referer": SIGN_URL, "Origin": BASE},
        timeout=20, allow_redirects=True,
    )
    checked(r, "签到提交响应")
    print("📨 签到已提交，仍需查询结果确认", flush=True)


def main():
    login()
    before = check()
    if before is True:
        return
    sign()
    after = check()
    if after is not True:
        raise RuntimeError("签到请求已经提交，但 Honor.ashx 尚未确认今日签到成功")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        sys.exit(1)
