import requests
from bs4 import BeautifulSoup
import datetime
import os


BASE = "https://vip.ioshashiqi.com"


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

    r=session.get(
        url,
        headers=headers
    )


    soup=BeautifulSoup(
        r.text,
        "html.parser"
    )


    return (

        soup.find(
            "input",
            {"name":"__VIEWSTATE"}
        )["value"],


        soup.find(
            "input",
            {"name":"__VIEWSTATEGENERATOR"}
        )["value"]

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


    if "密码错误" in r.text:

        print("❌ 密码错误")

        return False


    print("✅ 登录成功")

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



    session.post(

        url,

        headers=headers,

        data=data

    )


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
