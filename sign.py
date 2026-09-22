import requests
from bs4 import BeautifulSoup
import datetime
import os
from urllib.parse import urljoin, urlsplit

def find_sign_links(response):

    soup = BeautifulSoup(
        response.content,
        "html.parser"
    )

    print("🔍 搜索签到入口")

    found = False

    for a in soup.find_all("a"):

        text = a.get_text(" ", strip=True)

        href = a.get("href", "")

        keywords = (
            "签到",
            "qiandao",
            "sign",
            "checkin"
        )

        value = (text + href).lower()

        if any(k in value for k in keywords):

            found = True

            if href:

                full_url = urljoin(
                    response.url,
                    href
                )

                # 只显示本站链接，避免泄漏其他信息
                if urlsplit(full_url).netloc == urlsplit(BASE).netloc:
                    print(
                        f"📌 {text}: "
                        f"{urlsplit(full_url).path}"
                    )

            else:

                print(
                    f"📌 找到可能的签到按钮: {text}"
                )

    if not found:

        print(
            "⚠️ 当前页面没有发现签到链接，"
            "可能使用 JavaScript 或其他页面入口"
        )

BASE = "https://www.haxiaohaios2.com"


USER = os.getenv("VIP_USER")
PWD = os.getenv("VIP_PASS")


if not USER or not PWD:
    print("❌ 未读取到账号密码")
    exit(1)



session = requests.Session()



headers = {

    "User-Agent":
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_7 like Mac OS X) AppleWebKit/605.1.15 MicroMessenger/8.0.67",

    "Accept-Language":
    "zh-CN,zh-Hans;q=0.9",

}



def get_viewstate(url):
    r = session.get(
        url,
        headers=headers,
        timeout=20,
        allow_redirects=True
    )

    soup = BeautifulSoup(
        r.text,
        "html.parser"
    )

    from urllib.parse import urlsplit

    # 只打印路径，避免把 URL 中可能存在的令牌写入日志
    final_path = urlsplit(r.url).path

    title = (
        soup.title.get_text(strip=True)
        if soup.title
        else "无标题"
    )

    print(f"🌐 HTTP状态码: {r.status_code}")
    print(f"🌐 最终路径: {final_path}")
    print(f"📄 页面标题: {title}")

    r.raise_for_status()
    if urlsplit(url).path.lower().endswith("/qiandao.aspx"):

        redirected_to_login = (
            final_path.lower().endswith("/login.aspx")
        )

        login_form = soup.find(
            "input",
            {"name": "txtPwd_sign_in"}
        )

        if redirected_to_login or login_form:
            raise RuntimeError(
                "签到页面返回了登录表单，"
                "登录会话可能没有建立成功"
            )
    vs = soup.find(
        "input",
        {"name": "__VIEWSTATE"}
    )

    vsg = soup.find(
        "input",
        {"name": "__VIEWSTATEGENERATOR"}
    )

    if vs is None or vsg is None:

        # 仅打印表单字段名称，不打印密码、Cookie、
        # VIEWSTATE 的值或完整 HTML
        inputs = [
            tag.get("name")
            for tag in soup.find_all("input")
            if tag.get("name")
        ]

        print(f"🔎 表单字段: {inputs}")

        missing = []

        if vs is None:
            missing.append("__VIEWSTATE")

        if vsg is None:
            missing.append("__VIEWSTATEGENERATOR")

        raise RuntimeError(
            "页面缺少字段: "
            + ", ".join(missing)
            + "；请检查页面是否重定向到登录页、"
              "签到入口是否变更或页面是否被拦截"
        )

    return (
        vs.get("value", ""),
        vsg.get("value", "")
    )


def login():

    print("🔐 登录")


    url=BASE+"/aspx3/mobile/login.aspx"


    vs,vsg=get_viewstate(url)



    data={

        "__EVENTTARGET":
        "btnLogin",

        "__EVENTARGUMENT":
        "",

        "__VIEWSTATE":
        vs,

        "__VIEWSTATEGENERATOR":
        vsg,

        "txtUser_sign_in":
        USER,

        "txtPwd_sign_in":
        PWD

    }


    r=session.post(

        url,

        headers=headers,

        data=data

    )

    find_sign_links(r)
    if "密码错误" in r.text:

        print("❌ 密码错误")

        return False
    r.raise_for_status()

    # 确认登录后能够获取签到页面
    sign_url = BASE + "/aspx3/mobile/qiandao.aspx"

    get_viewstate(sign_url)

    print("✅ 登录成功，已确认签到页面可访问")

    return True





def sign():

    print("📅 开始签到")


    url=BASE+"/aspx3/mobile/qiandao.aspx"


    vs,vsg=get_viewstate(url)



    data={

        "__EVENTTARGET":
        "_lbtqd",

        "__EVENTARGUMENT":
        "",

        "__VIEWSTATE":
        vs,

        "__VIEWSTATEGENERATOR":
        vsg

    }



    r = session.post(
        url,
        headers=headers,
        data=data,
        timeout=20
    )

    r.raise_for_status()

    print("📨 签到请求已发送，等待查询结果确认")


    print("✅ 签到请求完成")





def check():

    print("🔎 查询结果")


    url=BASE+"/ashx/Honor.ashx"


    month=datetime.datetime.now().month



    r=session.post(

        url,

        headers=headers,

        data={

            "control":
            "list2",

            "nowmonth":
            month

        }

    )


    print(r.text)


    if '"signedToday":"True"' in r.text:

        print(
            "🎉 今日签到成功"
        )

    else:

        print(
            "⚠️ 未检测到签到"
        )




if __name__=="__main__":


    if login():

        sign()

        check()
