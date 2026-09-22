#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import os
import re
import sys
from collections import deque
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

BASE = os.getenv("BASE_URL", "https://www.haxiaohaios2.com").rstrip("/")
LOGIN_URL = os.getenv("LOGIN_URL", BASE + "/aspx3/mobile/login.aspx")
OLD_SIGN_URL = BASE + "/aspx3/mobile/qiandao.aspx"
# 在浏览器确认新地址后可设置 SIGN_URL；不设置时自动搜索。
SIGN_URL = os.getenv("SIGN_URL", "").strip()
TIMEOUT = 20
MAX_PAGES = 18

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
})


def secret(*names):
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def safe_path(url):
    """日志只展示路径；不输出 URL 的查询参数/令牌。"""
    return urlsplit(url).path or "/"


def same_site(url):
    return urlsplit(url).netloc.lower() == urlsplit(BASE).netloc.lower() and urlsplit(url).scheme in ("http", "https")


def absolute(url, current):
    if not url or url.startswith(("javascript:", "#", "mailto:", "tel:")):
        return None
    result = urljoin(current, url)
    return result if same_site(result) else None


def soup_of(response):
    # 使用原始字节解析，防止缺少 charset 时中文标题乱码。
    return BeautifulSoup(response.content, "html.parser")


def is_error(response, soup):
    path = safe_path(response.url).lower()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    return (
        response.status_code >= 400
        or "genericerrorpage" in path
        or "404错误页面" in title
        or "404 錯誤頁面" in title
    )


def report(response, prefix="页面"):
    soup = soup_of(response)
    title = soup.title.get_text(" ", strip=True) if soup.title else "无标题"
    print(f"🌐 {prefix}: HTTP {response.status_code}; 路径 {safe_path(response.url)}; 标题 {title[:70]}", flush=True)
    if is_error(response, soup):
        print("⚠️ 网站返回错误页；即使 HTTP 是 200，也不能当作有效页面", flush=True)
    return soup


def get(url, label):
    response = session.get(url, timeout=TIMEOUT, allow_redirects=True)
    report(response, label)
    return response


def hidden_fields(form):
    result = {}
    for tag in form.select('input[type="hidden"][name], input:not([type])[name]'):
        result[tag["name"]] = tag.get("value", "")
    return result


def find_login_form(soup):
    password = soup.select_one('input[type="password"][name]')
    if not password:
        return None, None
    return password.find_parent("form"), password


def login(username, password):
    print("🔐 获取登录表单", flush=True)
    response = get(LOGIN_URL, "登录页")
    soup = soup_of(response)
    if is_error(response, soup):
        raise RuntimeError("登录页已经失效，请确认 LOGIN_URL")
    form, pwd_input = find_login_form(soup)
    if form is None:
        raise RuntimeError("登录页面找不到密码表单，可能改为 JavaScript 登录；不能猜测接口")

    user_field = os.getenv("LOGIN_USER_FIELD", "").strip()
    pass_field = os.getenv("LOGIN_PASS_FIELD", "").strip() or pwd_input["name"]
    if not user_field:
        candidates = [tag for tag in form.find_all("input") if tag.get("name") and tag.get("type", "text").lower() in ("text", "email", "tel")]
        # 优先匹配用户名/手机号字段，避免把验证码识别成账号。
        candidates.sort(key=lambda tag: 0 if re.search(r"user|account|name|phone|mobile|login|txtname", tag["name"], re.I) else 1)
        if not candidates:
            raise RuntimeError("未发现用户名输入框，可在 Actions 中设置 LOGIN_USER_FIELD")
        user_field = candidates[0]["name"]

    data = hidden_fields(form)
    data[user_field] = username
    data[pass_field] = password
    # ASP.NET 普通提交按钮通常需要发送按钮字段。
    submits = [tag for tag in form.find_all(["input", "button"]) if tag.get("name") and tag.get("type", "submit").lower() in ("submit", "image")]
    if submits:
        button = submits[0]
        data[button["name"]] = button.get("value", "登录")
    else:
        # LinkButton 常用 __doPostBack('控件ID','')。
        for tag in form.find_all(["a", "button", "input"]):
            if re.search(r"登录|登\s*录|log\s*in", tag.get_text(" ", strip=True), re.I):
                match = re.search(r"__doPostBack\(['\"]([^'\"]+)['\"],\s*['\"]([^'\"]*)['\"]\)", tag.get("onclick", "") or tag.get("href", ""), re.I)
                if match:
                    data["__EVENTTARGET"], data["__EVENTARGUMENT"] = match.groups()
                    break
    action = absolute(form.get("action") or response.url, response.url)
    if not action:
        raise RuntimeError("登录表单 action 指向站外或无效 URL，已停止")
    print("📨 提交登录表单（不记录账号、密码及隐藏字段值）", flush=True)
    posted = session.post(action, data=data, timeout=TIMEOUT, allow_redirects=True,
                          headers={"Referer": response.url})
    posted_soup = report(posted, "登录提交后")
    if is_error(posted, posted_soup):
        raise RuntimeError("登录提交后网站返回错误页面")
    page_text = posted_soup.get_text(" ", strip=True)
    if re.search(r"用户名或密码错误|账号或密码错误|密码不正确|登录失败|验证码错误", page_text):
        raise RuntimeError("网站提示登录失败，请检查账号、密码或验证码")
    print("ℹ️ 登录请求已经提交；是否真正登录成功仍需签到页面验证", flush=True)
    return posted


SIGN_WORDS = ("签到", "qiandao", "checkin", "check-in", "lbtqd", "btnqd")

def is_sign_text(value):
    text = (value or "").lower()
    return any(word in text for word in SIGN_WORDS)


def links(soup, current):
    """收集站内页面与显式签到链接，不跟随 javascript。"""
    found = []
    for tag in soup.find_all("a", href=True):
        text = tag.get_text(" ", strip=True)
        href = tag["href"]
        url = absolute(href, current)
        if url:
            found.append((url, is_sign_text(text + " " + safe_path(url)), text))
    return found


def sign_control(form):
    for tag in form.find_all(["input", "button", "a"]):
        if tag.name == "input" and tag.get("type", "").lower() not in ("submit", "button", "image"):
            continue
        label = " ".join((tag.get("name", ""), tag.get("id", ""), tag.get("value", ""), tag.get_text(" ", strip=True)))
        if is_sign_text(label) and not re.search(r"已签到|已簽到", label):
            return tag
    return None


def sign_form(soup):
    for form in soup.find_all("form"):
        button = sign_control(form)
        if button:
            return form, button
    return None, None


def get_sign_page(posted):
    """有界搜索：优先签到相关链接，不把旧 404 当作有效入口。"""
    queue = deque([(posted, 0)])
    visited = {posted.url.split("#", 1)[0]}
    for url in (BASE + "/aspx3/mobile/", BASE + "/"):
        if url not in visited:
            queue.append((url, 0))
    if SIGN_URL:
        target = absolute(SIGN_URL, BASE + "/")
        if not target:
            raise RuntimeError("SIGN_URL 必须是本站地址")
        queue.appendleft((target, 0))
    checked = 0
    candidates = []
    print("🔍 从登录后的页面开始搜索签到入口", flush=True)

    while queue and checked < MAX_PAGES:
        item, depth = queue.popleft()
        if isinstance(item, requests.Response):
            response = item
        else:
            if item in visited:
                continue
            try:
                response = get(item, "搜索")
            except requests.RequestException as exc:
                print(f"⚠️ 页面读取失败: {safe_path(item)} ({type(exc).__name__})", flush=True)
                continue
        visited.add(response.url.split("#", 1)[0])
        checked += 1
        soup = soup_of(response)
        if is_error(response, soup):
            continue
        form, button = sign_form(soup)
        if form:
            print(f"✅ 找到包含签到按钮的表单: {safe_path(response.url)}", flush=True)
            return response, form, button
        for url, is_sign, text in links(soup, response.url):
            if is_sign and url not in candidates:
                candidates.append(url)
                print(f"📌 发现签到线索: {safe_path(url)} ({text[:25]})", flush=True)
            if url in visited or depth >= 2:
                continue
            path = safe_path(url).lower()
            useful = is_sign or any(w in path for w in ("index", "default", "home", "user", "member", "center", "mobile", "qiandao"))
            if useful and all(not (isinstance(x, str) and x == url) for x, _ in queue):
                if is_sign:
                    queue.appendleft((url, depth + 1))
                else:
                    queue.append((url, depth + 1))

    print(f"🔎 已检查 {checked} 个页面；发现 {len(candidates)} 个签到链接线索", flush=True)
    if not candidates:
        print("⚠️ 未发现静态签到表单；网站可能通过 JavaScript 请求接口", flush=True)
    print(f"⚠️ 旧签到地址 {safe_path(OLD_SIGN_URL)} 在之前的 Actions 日志中返回了错误页", flush=True)
    raise RuntimeError("未找到可确认的签到表单。请从浏览器 Network 获取新的签到 Request URL/Method/Payload")


def sign(response, form, button):
    action = absolute(form.get("action") or response.url, response.url)
    if not action:
        raise RuntimeError("签到表单 action 不安全或无效，已停止")
    data = hidden_fields(form)
    for field in form.find_all("input"):
        typ = field.get("type", "text").lower()
        if field.get("name") and typ in ("checkbox", "radio") and field.has_attr("checked"):
            data[field["name"]] = field.get("value", "on")
    js = button.get("onclick", "") or button.get("href", "")
    match = re.search(r"__doPostBack\(['\"]([^'\"]+)['\"],\s*['\"]([^'\"]*)['\"]\)", js, re.I)
    if match:
        data["__EVENTTARGET"], data["__EVENTARGUMENT"] = match.groups()
    elif button.get("name"):
        data[button["name"]] = button.get("value", "签到")
    else:
        raise RuntimeError("签到按钮由 JavaScript 控制，未确认请求参数；拒绝盲目提交")

    print(f"📅 向确认的签到表单提交: {safe_path(action)}", flush=True)
    result = session.post(action, data=data, headers={"Referer": response.url},
                          timeout=TIMEOUT, allow_redirects=True)
    soup = report(result, "签到返回")
    if is_error(result, soup):
        raise RuntimeError("签到请求被网站错误页面响应，未能确认成功")
    message = soup.get_text(" ", strip=True)
    if re.search(r"签到成功|簽到成功|今日已签到|今天已签到|今天已经签到|已经签到过", message):
        print("✅ 网页明确提示签到成功或今日已签到", flush=True)
    elif re.search(r"签到失败|簽到失敗|请先登录|請先登錄", message):
        raise RuntimeError("网页提示签到失败或会话失效")
    else:
        raise RuntimeError("签到请求已发送，但未找到明确成功提示；请按网站实际响应调整成功判定")


def main():
    username = secret("HAXIAOHAI_USERNAME", "USERNAME", "USER", "ACCOUNT", "EMAIL")
    password = secret("HAXIAOHAI_PASSWORD", "PASSWORD", "PASS", "PWD")
    if not username or not password:
        raise RuntimeError("没有读取到账号/密码：请检查 Actions Secrets 和工作流 env 映射")
    posted = login(username, password)
    response, form, button = get_sign_page(posted)
    sign(response, form, button)


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as exc:
        # requests 异常可能包含带令牌的 URL，避免直接写入公开 Actions 日志。
        print(f"❌ 网络请求失败: {type(exc).__name__}（已隐藏异常中可能的敏感 URL）", flush=True)
        sys.exit(1)
    except RuntimeError as exc:
        print(f"❌ {type(exc).__name__}: {exc}", flush=True)
        sys.exit(1)
