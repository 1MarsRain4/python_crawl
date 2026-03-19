# =============== 说明 ================
"""
这个是第二次迭代的爬虫，主要改进了以下几点：
1. 增加了官网自动查找隐私政策链接的功能，如果直接链接失效或内容过少，会自动跳转到官网首页尝试寻找隐私政策链接。
2. 优化了文本提取的逻辑，先尝试展开所有折叠内容和滚动页面，确保能获取到完整的文本。
3. 增加了对PDF链接的快速下载支持，直接保存PDF文件而不是尝试解析。
4. 增加了更多的错误处理和重试机制，确保在网络不稳定或页面结构复杂的情况下也能尽量完成抓取。
5. 输出文件命名更规范，避免非法字符，并且区分文本和HTML两种格式，方便后续处理。
总体来说，这个版本的爬虫更智能、更健壮，能够适应更多不同类型的隐私政策页面，尤其是那些需要登录或内容隐藏较深的页面。
"""
import requests
from bs4 import BeautifulSoup
import re
import os
import time
import random
from urllib.parse import urlparse, urljoin

# ================ Selenium 核心 ================
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ================ 配置区 ================
URL_LIST_FILE = "privacy_policy_urls.txt"
OUTPUT_DIR = "隐私政策文本"
SKIP_EXISTING = True
BASE_DELAY = 2.8
MAX_RETRIES = 2

chrome_options = Options()
chrome_options.add_argument("--lang=zh-CN,zh")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
chrome_options.add_experimental_option('useAutomationExtension', False)
# chrome_options.add_argument("--headless=new")   # 需要更快就取消注释

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36'}

def parse_url_line(line: str):
    line = line.strip()
    if not line or line.startswith('#'):
        return "", ""
    parts = re.split(r'\s{2,}|\t+|,', line, maxsplit=1)
    url = parts[0].strip()
    name = parts[1].strip() if len(parts) > 1 else urlparse(url).netloc.replace("www.", "").split(".")[0].capitalize() + " 隐私政策"
    name = re.sub(r'[<>:"/\\|?*]', '_', name).strip()
    return url, name

def load_urls_from_file(filepath):
    if not os.path.exists(filepath):
        print(f"× 文件不存在：{filepath}")
        return []
    pairs = [parse_url_line(line) for line in open(filepath, encoding='utf-8') if parse_url_line(line)[0]]
    print(f"从 {filepath} 读取到 {len(pairs)} 条链接")
    return pairs

def requires_login(driver):
    text_lower = driver.page_source.lower()
    if any(kw in text_lower for kw in ["登录", "请登录", "请先登录", "login", "sign in", "sign up", "auth required"]):
        return True
    if "login" in driver.current_url.lower():
        return True
    return False

def expand_all_collapsible(driver):
    """展开所有折叠内容（<details> + accordion + JS强制）"""
    for summary in driver.find_elements(By.TAG_NAME, "summary"):
        try: driver.execute_script("arguments[0].click();", summary); time.sleep(0.3)
        except: pass
    for btn in driver.find_elements(By.XPATH, "//*[contains(@class,'accordion') or contains(@class,'collapse') or @aria-expanded='false']"):
        try: driver.execute_script("arguments[0].click();", btn); time.sleep(0.3)
        except: pass
    driver.execute_script("""
        document.querySelectorAll('.collapse, .accordion-collapse, [aria-hidden="true"], .hidden').forEach(el => {
            el.style.display = 'block'; el.style.visibility = 'visible';
            el.setAttribute('aria-hidden', 'false'); 
            if(el.hasAttribute('aria-expanded')) el.setAttribute('aria-expanded', 'true');
        });
    """)
    time.sleep(1.2)

def scroll_and_follow_anchors(driver):
    """滚动 + 自动跳转所有内部锚点"""
    for _ in range(6):
        driver.execute_script("window.scrollBy(0, window.innerHeight*0.8);")
        time.sleep(0.7)
    for a in driver.find_elements(By.TAG_NAME, "a"):
        href = a.get_attribute("href") or ""
        if href.startswith("#") and len(href) > 2:
            try: driver.execute_script("arguments[0].scrollIntoView({behavior:'smooth'});", a)
            except: pass
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(1.5)

def try_fallback_to_homepage(driver, original_url, name):
    """新功能：官网自动查找隐私政策链接"""
    parsed = urlparse(original_url)
    netloc = parsed.netloc
    # 智能去掉 privacy./legal. 等子域名
    if netloc.startswith(('privacy.', 'legal.', 'terms.', 'policy.')):
        main_netloc = '.'.join(netloc.split('.')[1:])
    else:
        main_netloc = netloc
    homepage = f"{parsed.scheme}://{main_netloc}"
    
    print(f"  → 直接链接失效，自动跳转官网查找: {homepage}")
    try:
        driver.get(homepage)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)
        # 滚动到底部加载页脚
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.8)

        keywords = ["隐私政策", "隐私协议", "用户隐私", "Privacy Policy", "隐私", "政策", "legal", "terms", "privacy policy"]
        candidates = []
        for a in driver.find_elements(By.TAG_NAME, "a"):
            link_text = (a.text or "").strip()
            href = a.get_attribute("href") or ""
            full = (link_text + href).lower()
            if any(kw.lower() in full for kw in keywords):
                score = 0 if any(p in (href or "").lower() for p in ["privacy", "隐私政策", "隐私协议", "legal"]) else 1
                if href.startswith("http"):
                    full_href = href
                elif href.startswith("/"):
                    full_href = urljoin(homepage, href)
                else:
                    continue
                candidates.append((score, full_href, link_text))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            best_url = candidates[0][1]
            print(f"  √ 找到最佳隐私政策链接 → {best_url}")
            driver.get(best_url)
            WebDriverWait(driver, 12).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(2)
            if requires_login(driver):
                print("  × 官网隐私页面仍需登录，放弃")
                return False
            return True
        else:
            print("  × 官网未找到隐私政策链接")
            return False
    except Exception as e:
        print(f"  × 官网查找异常 → {str(e)[:100]}")
        return False

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.chdir(OUTPUT_DIR)
    
    url_pairs = load_urls_from_file("../" + URL_LIST_FILE)
    if not url_pairs: return

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.set_page_load_timeout(30)

    print(f"\n=== 开始智能爬取（含官网自动查找）{len(url_pairs)} 个隐私政策 ===\n")

    for i, (url, name) in enumerate(url_pairs, 1):
        filename_base = name
        print(f"[{i:3d}/{len(url_pairs)}] {name}")

        if SKIP_EXISTING and (os.path.exists(f"{filename_base} 隐私政策.txt") or os.path.exists(f"{filename_base} 隐私政策.html")):
            print("  已存在，跳过")
            continue

        if url.lower().endswith('.pdf'):
            # PDF 快速下载
            try:
                r = requests.get(url, headers=HEADERS, timeout=15)
                with open(f"{filename_base}.pdf", 'wb') as f: f.write(r.content)
                print(f"  √ PDF 已保存")
            except: print("  × PDF 下载失败")
            continue

        success = False
        for attempt in range(MAX_RETRIES):
            try:
                driver.get(url)
                WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

                # ==================== 判断是否需要官网 fallback ====================
                body_text_sample = driver.find_element(By.TAG_NAME, "body").text[:1500].lower()
                page_title = driver.title.lower()
                is_bad = (requires_login(driver) or
                          len(driver.find_element(By.TAG_NAME, "body").text) < 400 or
                          any(k in page_title or body_text_sample for k in ["404", "not found", "无法找到", "页面不存在", "访问受限", "403", "forbidden"]))

                if is_bad:
                    print("  ! 直接链接失效 → 触发官网自动查找")
                    if not try_fallback_to_homepage(driver, url, name):
                        print("  × 官网查找失败，放弃该平台")
                        break
                    # fallback成功后重新获取文本长度判断
                    body_text_sample = driver.find_element(By.TAG_NAME, "body").text[:1500].lower()

                # ==================== 正常展开 & 抓取 ====================
                expand_all_collapsible(driver)
                scroll_and_follow_anchors(driver)

                visible_text = driver.find_element(By.TAG_NAME, "body").text.strip()

                if len(visible_text) > 800:
                    with open(f"{filename_base} 隐私政策.txt", 'w', encoding='utf-8') as f:
                        f.write(visible_text)
                    print(f"  √ 保存展开后的可视化文本 ({len(visible_text):,} 字符)")
                    success = True
                else:
                    full_html = driver.page_source
                    with open(f"{filename_base} 隐私政策.html", 'w', encoding='utf-8') as f:
                        f.write(full_html)
                    print(f"  √ 文本过短 → 保存完整HTML ({len(full_html):,} 字符)")
                    success = True
                break

            except Exception as e:
                print(f"  尝试 {attempt+1} 失败 → {str(e)[:120]}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(4)

        if not success:
            print("  × 该平台完全抓取失败（已尝试官网查找）")

        time.sleep(BASE_DELAY + random.uniform(0, 1.8))

    driver.quit()
    print("\n=== 全部处理完成！文件保存在 ./隐私政策文本/ ===")

if __name__ == '__main__':
    main()