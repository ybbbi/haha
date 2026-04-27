import requests
import os
import time

# 请求头
headers = {
    "Host": "vip.ioshashiqi.com",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Sec-Fetch-Site": "same-origin",
    "Accept-Language": "zh-CN,zh-Hans;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Mode": "navigate",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://vip.ioshashiqi.com",
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.67(0x18004330) NetType/4G Language/zh_CN",
    "Referer": "https://vip.ioshashiqi.com/aspx3/mobile/qiandao.aspx",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "document"
}

# 从环境变量读取 Cookie
cookie = os.getenv("COOKIE")
if not cookie:
    print("❌ 未配置 COOKIE，请在 GitHub Secrets 中添加")
    exit(1)

headers["Cookie"] = cookie

# POST 地址
url = "https://vip.ioshashiqi.com/aspx3/mobile/qiandao.aspx"

# 表单数据（根据你抓到的真实签到参数填写）
# 示例：data = {"__EVENTTARGET": "", "__EVENTARGUMENT": "", "btnSign": "签到"}
data = {}

print("⏰ 开始签到...")
try:
    resp = requests.post(url, headers=headers, data=data, timeout=10)
    print(f"✅ 状态码: {resp.status_code}")
    print(f"🔍 响应长度: {len(resp.text)}")
    if "成功" in resp.text or "签到" in resp.text:
        print("🎉 签到成功！")
    else:
        print("⚠️ 请检查参数是否正确")
except Exception as e:
    print(f"❌ 请求失败: {str(e)}")
