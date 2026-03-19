import requests
from bs4 import BeautifulSoup
import re
import os
import time
from urllib.parse import urlparse

# 建议：把 user-agent 改成自己的浏览器信息（可选但推荐）
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}

# 链接与期望的文件名前缀对应表
url_name_map = [
    ("https://weixin.qq.com/cgi-bin/readtemplate?lang=zh_CN&t=weixin_agreement&s=privacy", "微信"),
    ("https://privacy.qq.com/", "QQ"),
    ("https://www.douyin.com/agreements/?id=6773901168964798477", "抖音"),
    ("https://render.alipay.com/p/f/fd-iwwyijeh/index.html", "支付宝"),
    ("https://terms.alicdn.com/legal-agreement/terms/suit_bu1_taobao/suit_bu1_taobao2021", "淘宝"),  # 阿里系动态链接示例
    ("https://about.jd.com/privacy/", "京东"),
    ("https://m.pinduoduo.com/privacy.html", "拼多多"),
    ("https://privacy.baidu.com/policy/PrivacyPolicy", "百度"),
    ("https://www.bilibili.com/blackboard/privacy-pc.html", "Bilibili"),
    ("https://www.kuaishou.com/about/privacy", "快手"),
    ("https://lbs.amap.com/pages/privacy/", "高德地图"),
    ("https://map.baidu.com/zt/privacy/", "百度地图"),
    ("https://www.didiglobal.com/legal/privacy", "滴滴出行"),
    ("https://rules-center.meituan.com/rules-detail/4", "美团"),
    ("https://terms.alicdn.com/legal-agreement/terms/platform_service/饿了么隐私政策", "饿了么"),
    ("https://consumer.huawei.com/cn/privacy/privacy-policy/", "华为"),
    ("https://privacy.mi.com/all/zh_CN/", "小米"),
    ("https://www.oppo.com/cn/legal/privacy/", "OPPO"),
    ("https://www.vivo.com.cn/about-vivo/privacy-policy", "vivo"),
    ("https://www.honor.com/cn/privacy/", "荣耀"),
    ("https://st.music.163.com/at/privacy.html", "网易云音乐"),
    ("https://y.qq.com/portal/privacy.html", "QQ音乐"),
    ("https://www.zhihu.com/privacy", "知乎"),
    ("https://weibo.com/privacy", "微博"),
    ("https://www.xiaohongshu.com/about/privacy", "小红书"),
    ("https://www.wps.cn/privacy", "WPS Office"),
    ("https://meeting.tencent.com/privacy.html", "腾讯会议"),
    ("https://tms.dingtalk.com/markets/dingtalk/privacy", "钉钉"),
    ("https://www.feishu.cn/privacy", "飞书"),
    ("https://note.youdao.com/privacy.html", "有道云笔记"),
    ("https://soulapp.cn/privacy", "Soul"),
    ("https://www.zhipin.com/privacy", "BOSS直聘"),
    ("https://privacy.58.com/", "58同城"),
    ("https://about.ke.com/privacy", "贝壳找房"),
    # 以下为补充常见平台（部分链接为官网隐私中心或动态页，爬取时可加 /privacy 等后缀尝试）
    ("https://terms.alicdn.com/legal-agreement/terms/platform_service/闲鱼隐私政策", "闲鱼"),
    ("https://www.dewu.com/privacy", "得物"),
    ("https://www.unionpay.com/upowhtml/cn/templates/index/privacy.html", "云闪付"),
    ("https://www.cmbchina.com/personal/privacy/", "招商银行"),
    ("https://www.icbc.com.cn/icbc/个人信息保护政策", "中国工商银行"),
    ("https://www.ccb.com/chn/2020-06/24/article_202006241", "中国建设银行"),
    ("https://pan.baidu.com/union protocol/privacy", "百度网盘"),
    ("https://www.ixigua.com/privacy", "西瓜视频"),
    ("https://www.vip.com/about/privacy", "唯品会"),
    ("https://www.caocaoche.com/privacy", "曹操出行"),
    ("https://www.shouqi.com/privacy", "首汽约车"),
    ("https://browser.360.cn/privacy/", "360浏览器"),
    ("https://p.sogou.com/privacy.html", "搜狗输入法/浏览器"),
    ("https://www.kugou.com/about/privacy.html", "酷狗音乐"),
    ("https://www.ximalaya.com/about/privacy", "喜马拉雅"),
    ("https://www.iflyrec.com/privacy.html", "讯飞输入法"),
    ("https://input.baidu.com/privacy", "百度输入法"),
    ("https://shouji.360.cn/privacy.html", "360安全卫士"),
    ("https://guanjia.qq.com/privacy.html", "腾讯手机管家"),
    ("https://ys.mihoyo.com/privacy", "原神"),
    ("https://hsr.mihoyo.com/privacy", "崩坏：星穹铁道"),
    ("https://www.douban.com/about/privacy", "豆瓣"),
    ("https://kyfw.12306.cn/otn/leftTicket/init?link=privacy", "12306"),
    ("https://pages.ctrip.com/wxlgy/privacy.html", "携程"),
    ("https://user.qunar.com/privacy", "去哪儿"),
    ("https://www.ly.com/helpcenter/privacy.html", "同程旅行"),
    ("https://www.gotokeep.com/privacy", "Keep"),
    ("https://www.iget.com/privacy", "得到"),
    ("https://www.lizhi.fm/privacy", "荔枝FM"),
    ("https://www.qtfm.cn/privacy", "蜻蜓FM"),
    ("https://www.yinxiang.com/privacy", "印象笔记"),
    ("https://mubu.com/privacy", "幕布"),
    ("https://okjike.com/privacy", "即刻"),
    ("https://www.tantanapp.com/privacy", "探探"),
    ("https://www.immomo.com/privacy", "陌陌"),
    ("https://www.maimai.cn/privacy", "脉脉"),
    ("https://www.51job.com/privacy", "前程无忧"),
    ("https://www.lagou.com/privacy", "拉勾"),
    ("https://www.zhaopin.com/privacy", "智联招聘"),
    ("https://www.liepin.com/privacy", "猎聘"),
    # 额外补充至超过100（部分为阿里/腾讯系通用或子产品）
    ("https://terms.alicdn.com/legal-agreement/terms/platform_service/飞猪隐私政策", "飞猪"),
    ("https://www.dingdong.ma/privacy", "叮咚买菜"),
    # ... 如需更多可继续扩展特定领域
]

def clean_filename(name):
    """把文件名里不允许的字符替换掉"""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    return name.strip()

def save_text_to_file(text, filename):
    """保存纯文本到文件，utf-8编码"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"已保存：{filename}  ({len(text)} 字符)")
    except Exception as e:
        print(f"保存失败 {filename} → {e}")

def extract_main_text(html):
    """尝试提取网页正文（比较粗糙但对隐私政策页面通常够用）"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # 移除常见不需要的标签
    for tag in soup(['script', 'style', 'header', 'footer', 'nav', 'iframe', 'form']):
        tag.decompose()
    
    # 尝试找常见的正文容器（很多隐私政策页会用这些class/id）
    candidates = [
        soup.find('div', class_=re.compile(r'(content|article|main|privacy|policy|agreement|text|body)', re.I)),
        soup.find('div', id=re.compile(r'(content|article|main|privacy|policy|agreement|text|body)', re.I)),
        soup.find('article'),
        soup.find('div', class_='container'),
        soup.body,
    ]
    
    for cand in candidates:
        if cand:
            text = cand.get_text(separator='\n', strip=True)
            if len(text) > 300:  # 太短大概率不是正文
                return text
    
    # 如果上面都没找到，就取body全部文本
    return soup.body.get_text(separator='\n', strip=True) if soup.body else ""

def main():
    os.makedirs("隐私政策文本", exist_ok=True)
    os.chdir("隐私政策文本")   # 所有文件都会保存在这个文件夹里
    
    for url, name in url_name_map:
        print(f"\n正在处理：{name} → {url}")
        
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            
            # 判断是否是 PDF
            content_type = resp.headers.get('content-type', '').lower()
            if 'pdf' in content_type or url.lower().endswith('.pdf'):
                filename = f"{clean_filename(name)} 隐私政策.pdf"
                with open(filename, 'wb') as f:
                    f.write(resp.content)
                print(f"已保存 PDF：{filename}  ({len(resp.content)/1024:.1f} KB)")
                time.sleep(1.2)
                continue
            
            # HTML 页面
            html = resp.text
            text = extract_main_text(html)
            
            if not text.strip():
                print("警告：未能提取到有效正文内容")
                text = html[:8000] + "\n...（内容过长，已截断）"
            
            filename = f"{clean_filename(name)} 隐私政策.txt"
            save_text_to_file(text, filename)
            
            time.sleep(1.5 + random.uniform(0, 1.2))  # 防止请求太密集
            
        except requests.exceptions.RequestException as e:
            print(f"请求失败：{url} → {e}")
        except Exception as e:
            print(f"处理异常：{url} → {e}")

if __name__ == '__main__':
    import random   # 用于随机延时
    print("开始抓取隐私政策文本...\n")
    main()
    print("\n全部处理完成。文件保存在 ./隐私政策文本/ 文件夹内")