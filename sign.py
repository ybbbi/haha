# -*- coding: utf-8 -*-
"""哈小海网站签到；保留原仓库 VIP_USER / VIP_PASS 和 Honor.ashx 查询方式。"""
import datetime
import os
import re
import sys
from collections import deque
from urllib.parse import urljoin, urlsplit, urldefrag
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BASE = "https://www.haxiaohaios2.com"
LOGIN_URL = BASE + "/aspx3/mobile/login.aspx"
CHECK_URL = BASE + "/ashx/Honor.ashx"
USER = os.getenv("VIP_USER")
PWD = os.getenv("VIP_PASS")

session = requests.Session()
headers = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_7 like Mac OS X) "
        "AppleWebKit/605.1.15 MicroMessenger/8.0.67"
    ),
    "Accept-Language": "zh-CN,zh-Hans;q=0.9",
}

SIGN_WORDS = ("签到", "qiandao", "checkin", "check-in", "每日签到")
SKIP_WORDS = ("login", "logout", "signout", "sign-in", "signin", "register", "reset", "找回", "退出")


def same_site(url):
    return (urlsplit(url).scheme in ("http", "https")
            and urlsplit(url).hostname == urlsplit(BASE).hostname)


def safe_path(url):
    # 不打印查询参数：URL 可能包含令牌或用户信息。
    return urlsplit(url).path


def page_soup(response):
    # 从原始字节检测编码，避免网站未声明编码时中文出现乱码。
    return BeautifulSoup(response.content, "html.parser")


def is_error_page(response, soup=None):
    soup = soup or page_soup(response)
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    path = safe_path(response.url).lower()
    return ("genericerrorpage" in path
            or "404" in title
            or response.status_code == 404)


def report_page(response, name):
    soup = page_soup(response)
    title = soup.title.get_text(" ", strip=True)[:70] if soup.title else "无标题"
    print(f"🌐 {name} HTTP {response.status_code} | {safe_path(response.url)} | {title}", flush=True)
    if is_error_page(response, soup):
        print("⚠️ 服务器返回错误页，即使 HTTP 状态码为 200 也不能视为有效页面", flush=True)
    return soup


def get(url, name="页面"):
    if not same_site(url):
        raise RuntimeError("拒绝访问非本站链接")
    response = session.get(url, headers=headers, timeout=20, allow_redirects=True)
    soup = report_page(response, name)
    response.raise_for_status()
    if not same_site(response.url):
        raise RuntimeError("页面跳转到了非本站地址")
    return response, soup


def hidden_fields(soup):
    # ASP.NET 可能还需要 __EVENTVALIDATION 等隐藏字段，不能只传 VIEWSTATE 两项。
    fields = {}
    for tag in soup.select("input[name]"):
        # 保留 ASP.NET 隐藏表单字段；部分旧站未正确声明 type=hidden。
        name = tag["name"]
        if tag.get("type", "").lower() == "hidden" or name.startswith("__"):
            fields[name] = tag.get("value", "")
    return fields


def login():
    print("🔐 开始登录", flush=True)
    _, soup = get(LOGIN_URL, "登录页")
    fields = hidden_fields(soup)
    if "__VIEWSTATE" not in fields:
        raise RuntimeError("登录页缺少 __VIEWSTATE，页面结构可能已变化")

    # 与最初能完成登录提交的原脚本保持一致：
    # 不依赖 HTML 里能否静态搜索到用户名输入框。
    # 不再动态猜测登录字段名称。
    fields.update({
        "__EVENTTARGET": "btnLogin",
        "__EVENTARGUMENT": "",
        "txtUser_sign_in": USER,
        "txtPwd_sign_in": PWD,
    })
    response = session.post(
        LOGIN_URL, headers=headers, data=fields,
        timeout=20, allow_redirects=True,
    )
    soup = report_page(response, "登录提交结果")
    response.raise_for_status()
    if not same_site(response.url) or is_error_page(response, soup):
        raise RuntimeError("登录请求没有得到有效页面")
    text = soup.get_text(" ", strip=True)
    if any(word in text for word in ("密码错误", "用户名或密码错误", "账号不存在")):
        raise RuntimeError("网站提示登录失败：请检查账号密码")

    # 登录 POST 返回 200 并不代表鉴权成功，后续 Honor 查询 / 签到页再核实。
    print("📨 使用原始字段 txtUser_sign_in / txtPwd_sign_in 提交登录请求（会话待验证）", flush=True)
    return response


def signed_today_value(value):
    """从 JSON 的顶层或嵌套结构提取 signedToday；无法判断时返回 None。"""
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() == "signedtoday":
                if isinstance(item, bool):
                    return item
                if isinstance(item, str) and item.strip().lower() in ("true", "false"):
                    return item.strip().lower() == "true"
        for item in value.values():
            result = signed_today_value(item)
            if result is not None:
                return result
    elif isinstance(value, list):
        for item in value:
            result = signed_today_value(item)
            if result is not None:
                return result
    return None


def check():
    print("🔎 查询今日签到状态", flush=True)
    month = datetime.datetime.now(ZoneInfo("Asia/Shanghai")).month
    try:
        response = session.post(
            CHECK_URL, headers=headers,
            data={"control": "list2", "nowmonth": month},
            timeout=20, allow_redirects=True,
        )
        soup = report_page(response, "签到查询")
        response.raise_for_status()
        if not same_site(response.url) or is_error_page(response, soup):
            print("⚠️ 查询接口返回了错误页", flush=True)
            return None
        try:
            result = signed_today_value(response.json())
        except ValueError:
            # 与原版的 '"signedToday":"True"' 文本判断兼容。
            match = re.search(
                r'"signedToday"\s*:\s*"?(true|false)"?',
                response.text, flags=re.I,
            )
            result = (match.group(1).lower() == "true") if match else None
        if result is True:
            print("🎉 网站确认：今日已签到", flush=True)
        elif result is False:
            print("📅 网站确认：今日尚未签到", flush=True)
        else:
            print("⚠️ 查询响应中找不到 signedToday，无法确认签到状态", flush=True)
        return result
    except requests.RequestException as exc:
        print(f"⚠️ 签到查询网络异常：{type(exc).__name__}", flush=True)
        return None


def sign_hint(text):
    t = text.lower()
    return any(word in t for word in SIGN_WORDS) and not any(word in t for word in SKIP_WORDS)


def form_has_sign(soup):
    # 只识别原脚本中已知的 ASP.NET 签到事件，或可见的签到提交按钮。
    if soup.find(string=re.compile(r"__doPostBack\s*\(\s*['\"]_lbtqd['\"]")):
        return True
    for el in soup.find_all(["input", "button", "a"]):
        name = el.get("name", "")
        ident = el.get("id", "")
        onclick = el.get("onclick", "")
        href = el.get("href", "")
        label = (el.get("value", "") + " " + el.get_text(" ", strip=True))
        if "_lbtqd" in (name, ident) or "_lbtqd" in (onclick + href):
            return True
        if el.name in ("input", "button") and sign_hint(label):
            return True
    return False


def links_on_page(response, soup):
    """从已登录页面提取站内导航；优先搜索页面明确标注的签到链接。"""
    priority, other = [], []
    for a in soup.select("a[href]"):
        href = a.get("href", "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        url = urldefrag(urljoin(response.url, href)).url
        if not same_site(url):
            continue
        path = safe_path(url).lower()
        if any(x in path for x in ("logout", "signout", "delete", "remove")):
            continue
        if re.search(r"\.(?:jpg|png|gif|svg|css|js|zip|pdf|ico)(?:$|/)", path):
            continue
        label = a.get_text(" ", strip=True)
        if sign_hint(label + " " + path):
            print(f"📌 发现疑似签到入口：{safe_path(url)}", flush=True)
            priority.append(url)
        elif path.endswith((".aspx", "/", ".htm", ".html")):
            other.append(url)
    # 识别写在 JS 字符串里的显式 .aspx 签到路径，不猜测不存在的接口。
    for match in re.finditer(
        r"['\"]([^'\"<>\s]*(?:qiandao|checkin)[^'\"<>\s]*\.aspx(?:\?[^'\"<>\s]*)?)['\"]",
        response.text, flags=re.I,
    ):
        url = urldefrag(urljoin(response.url, match.group(1))).url
        if same_site(url):
            print(f"📌 在页面源码发现疑似签到路径：{safe_path(url)}", flush=True)
            priority.append(url)
    return priority, other


def discover_sign_page(login_response, max_pages=14):
    print("🔍 搜索真正的签到页面", flush=True)
    # 已知旧地址已被证明会返回 GenericErrorPage.htm，不能作为默认签到目标。
    queue = deque([login_response, BASE + "/"])
    visited = set()
    count = 0
    while queue and count < max_pages:
        item = queue.popleft()
        try:
            if isinstance(item, requests.Response):
                response = item
                if not same_site(response.url):
                    continue
            else:
                if item in visited or not same_site(item):
                    continue
                response, _ = get(item, "候选页面")
            visited.add(response.url)
            count += 1
            soup = page_soup(response)
            if is_error_page(response, soup):
                continue
            path = safe_path(response.url).lower()
            if form_has_sign(soup) and "login.aspx" not in path:
                print(f"✅ 找到签到表单：{safe_path(response.url)}", flush=True)
                return response
            priority, other = links_on_page(response, soup)
            # 优先访问页面明确提供的签到入口，再看其他站内导航。
            queued = set(x for x in queue if isinstance(x, str))
            for url in reversed(priority):
                if url not in visited and url not in queued:
                    queue.appendleft(url)
                    queued.add(url)
            for url in other:
                if url not in visited and url not in queued:
                    queue.append(url)
                    queued.add(url)
        except requests.RequestException as exc:
            print(f"⚠️ 页面访问失败：{type(exc).__name__}", flush=True)
            continue
    raise RuntimeError(
        "未在已访问的本站页面中发现可识别的签到表单；"
        "旧 qiandao.aspx 已返回错误页。请在浏览器 F12/Network 中确认新签到请求地址和参数。"
    )


def sign(page_response):
    print("📅 开始签到", flush=True)
    soup = page_soup(page_response)
    if is_error_page(page_response, soup):
        raise RuntimeError("当前页面是网站错误页，拒绝发送签到请求")
    if not form_has_sign(soup):
        raise RuntimeError("页面没有可识别的签到按钮，拒绝盲目 POST")
    forms = soup.find_all("form")
    if not forms:
        raise RuntimeError("签到页没有 HTML 表单；可能已改为 AJAX 签到，需要实际请求参数")
    form = next((f for f in forms if "_lbtqd" in str(f)), forms[0])
    data = hidden_fields(form)
    if "__VIEWSTATE" not in data:
        raise RuntimeError("签到表单缺少 __VIEWSTATE，可能不是原来的 ASP.NET 签到机制")
    submit = None
    target = None
    for el in form.find_all(["input", "button", "a"]):
        text = (el.get("value", "") + " " + el.get_text(" ", strip=True))
        identity = (el.get("name", ""), el.get("id", ""))
        js = el.get("onclick", "") + el.get("href", "")
        match = re.search(r"__doPostBack\s*\(\s*['\"]([^'\"]+)['\"]", js)
        if match and ("_lbtqd" in match.group(1) or sign_hint(text)):
            target = match.group(1)
            break
        if "_lbtqd" in identity:
            target = next(x for x in identity if "_lbtqd" in x)
            break
        if el.name in ("input", "button") and sign_hint(text) and el.get("name"):
            submit = (el["name"], el.get("value", ""))
    if target:
        data.update({"__EVENTTARGET": target, "__EVENTARGUMENT": ""})
    elif submit:
        data[submit[0]] = submit[1]
    else:
        raise RuntimeError("没有找到可提交的签到事件参数，拒绝猜测")

    action = form.get("action", "")
    post_url = urljoin(page_response.url, action) if action else page_response.url
    if not same_site(post_url):
        raise RuntimeError("签到表单指向非本站，已停止")
    print(f"📨 提交签到表单：{safe_path(post_url)}", flush=True)
    response = session.post(
        post_url, headers=headers, data=data,
        timeout=20, allow_redirects=True,
    )
    result = report_page(response, "签到提交结果")
    response.raise_for_status()
    if not same_site(response.url) or is_error_page(response, result):
        raise RuntimeError("签到提交后返回错误页或跳转到非本站")
    print("📨 签到请求已提交，最终以状态查询为准", flush=True)


def main():
    if not USER or not PWD:
        raise RuntimeError("未读取到 VIP_USER 或 VIP_PASS，请检查 GitHub Actions Secrets")
    login_response = login()
    before = check()
    if before is True:
        return
    page = discover_sign_page(login_response)
    sign(page)
    after = check()
    if after is not True:
        raise RuntimeError("签到请求已提交，但网站未确认今日签到成功；请查看上述日志")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"❌ {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
