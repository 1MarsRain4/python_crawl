"""
和未更新前的第一版相比，这个版本做了以下改进：
1. 更智能的正文提取：新增了多个优先级较高的 CSS选择器，特别针对隐私政策页面常见的结构进行优化。
2. 增加了对 PDF 文件的识别和保存功能。
"""
import requests
from bs4 import BeautifulSoup
import re
import os
import time
import random
from urllib.parse import urlparse

# =====================================================================
# 配置区
# =====================================================================

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}

# 你希望从哪个文件读取链接列表
URL_LIST_FILE = "E:\\main files\\毕设-隐私政策模糊性评价方法研究与实现(综合型)\\python crawl\\privacy_policy_urls.txt"          # ← 修改成你实际的文件名

# 输出文件夹
OUTPUT_DIR = "隐私政策文本"

# 是否跳过已存在的文件（推荐开启）
SKIP_EXISTING = True

# 每个请求之间的基础延时（秒）
BASE_DELAY = 1.8
RANDOM_DELAY_RANGE = (0, 1.6)

# 请求失败时的重试次数
MAX_RETRIES = 2

# =====================================================================

def parse_url_line(line: str) -> tuple[str, str]:
    """从一行文本中解析出 (url, name)"""
    line = line.strip()
    if not line or line.startswith('#') or line.startswith('//'):
        return "", ""

    # 常见分隔符：空格、制表符、逗号
    parts = re.split(r'\s{2,}|\t+|,|\s+', line.strip(), maxsplit=1)

    if len(parts) >= 2:
        url, name = parts[0].strip(), " ".join(parts[1:]).strip()
    else:
        url = parts[0].strip()
        # 没有名称 → 尝试从域名提取
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "").split(".")[0].capitalize()
        name = f"{domain} 隐私政策"

    # 清理名称
    name = re.sub(r'[<>:"/\\|?*]', '_', name).strip()

    return url, name


def load_urls_from_file(filepath: str) -> list[tuple[str, str]]:
    """从 txt 文件读取 url 和名称对"""
    if not os.path.exists(filepath):
        print(f"× 文件不存在：{filepath}")
        return []

    pairs = []
    with open(filepath, encoding='utf-8') as f:
        for line in f:
            url, name = parse_url_line(line)
            if url:
                pairs.append((url, name))

    print(f"从 {filepath} 读取到 {len(pairs)} 条有效链接")
    return pairs


def get_preferred_container(soup):
    """更智能的正文容器选择（隐私政策页面常用结构）"""
    priority_selectors = [
        # class 优先
        ('div', {'class': re.compile(r'(privacy|policy|legal|terms|agreement|content|main|article|body|text|entry-content|page-content|legal-text)', re.I)}),
        ('div', {'id': re.compile(r'(privacy|policy|legal|terms|agreement|content|main|article|body|text)', re.I)}),
        ('main', {}),
        ('article', {}),
        ('div', {'class': re.compile(r'(container|wrapper|content-wrapper|legal-container)', re.I)}),
        ('section', {'class': re.compile(r'(privacy|legal|content)', re.I)}),
        # 兜底
        ('div', {}),
        ('body', {}),
    ]

    for tag_name, attrs in priority_selectors:
        if attrs:
            element = soup.find(tag_name, attrs)
        else:
            element = soup.find(tag_name)

        if element:
            # 过滤掉过短的内容
            text = element.get_text(separator='\n', strip=True)
            if len(text) > 400:
                return text

    # 实在找不到，返回整个 body
    if soup.body:
        return soup.body.get_text(separator='\n', strip=True)
    return ""


def clean_and_save_text(text: str, filename: str):
    if not text.strip():
        print("  × 提取到的正文为空，跳过保存")
        return

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"  √ 已保存：{filename}  ({len(text):,} 字符)")
    except Exception as e:
        print(f"  × 保存失败 {filename} → {e}")


def download_privacy_policy(url: str, name: str):
    print(f"\n→ {name}\n  {url}")

    filename = f"{name}.txt"
    if SKIP_EXISTING and os.path.exists(filename):
        print(f"  已存在，跳过：{filename}")
        return

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()

            content_type = resp.headers.get('content-type', '').lower()

            # 处理 PDF
            if 'pdf' in content_type or url.lower().endswith('.pdf'):
                pdf_name = f"{name}.pdf"
                with open(pdf_name, 'wb') as f:
                    f.write(resp.content)
                print(f"  √ 保存 PDF：{pdf_name}  ({len(resp.content)/1024:.1f} KB)")
                return

            # HTML
            soup = BeautifulSoup(resp.text, 'html.parser')
            text = get_preferred_container(soup)

            if len(text) < 300:
                print("  ! 正文过短，可能抓取失败，保存原始 HTML 供检查")
                text = resp.text[:12000] + "\n\n...（原始 HTML 已截断）"

            clean_and_save_text(text, filename)
            return

        except requests.exceptions.RequestException as e:
            print(f"  请求失败 (尝试 {attempt}/{MAX_RETRIES}) → {e}")
            if attempt < MAX_RETRIES:
                time.sleep(3 + random.uniform(0, 3))
            else:
                print(f"  × 达到最大重试次数，放弃：{url}")

        except Exception as e:
            print(f"  × 处理异常 → {e}")
            break


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.chdir(OUTPUT_DIR)

    url_name_pairs = load_urls_from_file(URL_LIST_FILE)

    if not url_name_pairs:
        print("没有读取到任何有效链接，程序退出。")
        return

    print(f"\n开始处理 {len(url_name_pairs)} 个隐私政策页面 ...\n")

    for i, (url, name) in enumerate(url_name_pairs, 1):
        print(f"[{i:3d}/{len(url_name_pairs)}]")
        download_privacy_policy(url, name)

        # 延时
        delay = BASE_DELAY + random.uniform(*RANDOM_DELAY_RANGE)
        time.sleep(delay)

    print("\n全部处理完成。")
    print(f"文件保存在：{os.path.abspath('.')}")


if __name__ == '__main__':
    main()