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
    ("https://about.eastmoney.com/home/conceal",                     "东方财富"),
    ("https://vipmoney.eastmoney.com/collect/min/useragreement/index.html?categoryCode=ysxy_zq", "东方财富证券"),
    ("https://xueqiu.com/law/privacy",                               "雪球"),
    ("https://m.zhangle.com/views/app_agreement/index.html",         "华泰证券涨乐财富通"),
    ("https://www.guosen.com.cn/gs/pages/jty/privacy.html",          "国信证券"),
    ("https://e.bocichina.com/app/html/boci_privacyPolicy.html",     "中银证券"),
    ("https://wx.dxzq.net/dxweixin_client/publich5/protocol/ysxy.html", "东兴证券"),
    ("https://www.shgsec.com/newback/download/201703/01/appyszc.html",  "申港证券"),
    ("https://rules-center.meituan.com/m/detail/2",                  "美团"),
    ("https://www.tenpay.com/v3/helpcenter/low/privacy.shtml",       "财付通"),
    ("https://www.pinduoduo.com/pdd_privacy_policy.pdf",             "拼多多"),   # pdf 会特殊处理
    # 你可以继续在这里添加更多 (url, 名称) 元组
    # 这里有一些示例链接，你可以根据需要替换成你想抓取的隐私政策链接，并给出合适的名称，但是其中有些链接可能需要登录后才能访问，或者内容结构比较复杂，抓取效果可能不太理想，需要你根据实际情况调整抓取逻辑。
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