import requests
from bs4 import BeautifulSoup
import re
import os
import time
import random
import json
from urllib.parse import urlparse, urljoin
from datetime import datetime

# ================ Selenium 核心（防检测升级版） ================
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ================ 配置区（可自行修改） ================
URL_LIST_FILE = "privacy_policy_urls.txt"      # ← 你的链接文件（放脚本同目录）
OUTPUT_DIR = "隐私政策文本"
SKIP_EXISTING = True
BASE_DELAY = 3.2                               # 基础延时（秒）
MAX_RETRIES = 3                                # 最大重试次数（含指数退避）

# User-Agent 池（随机切换，防特征识别）
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]

def get_random_ua():
    return random.choice(USER_AGENTS)

# Selenium 配置（已集成防检测）
chrome_options = Options()
chrome_options.add_argument("--lang=zh-CN,zh")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument(f"user-agent={get_random_ua()}")
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
chrome_options.add_experimental_option('useAutomationExtension', False)

# ================ 工具函数 ================
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

def handle_cookie_banner(driver):
    """自动点击常见 Cookie / 同意弹窗"""
    try:
        accept_btn = WebDriverWait(driver, 6).until(
            EC.element_to_be_clickable((By.XPATH,
                "//button[contains(text(),'同意') or contains(text(),'Accept') or contains(text(),'同意所有') or "
                "contains(text(),'I Accept') or @id='onetrust-accept-btn-handler' or contains(@class,'accept')]"))
        )
        driver.execute_script("arguments[0].click();", accept_btn)
        time.sleep(1.2)
        print("  √ 已自动处理 Cookie 同意弹窗")
    except:
        pass  # 无弹窗正常

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
    """滚动到底 + 自动跳转内部锚点链接"""
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
    """官网自动查找隐私政策链接"""
    parsed = urlparse(original_url)
    netloc = parsed.netloc
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

def save_metadata(name, original_url, final_url, used_fallback, text_length, file_type, status):
    """保存元数据 JSON（强烈推荐，便于后续管理）"""
    metadata = {
        "platform": name,
        "original_url": original_url,
        "final_url": final_url,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "text_length": text_length,
        "used_fallback": used_fallback,
        "file_type": file_type,
        "status": status
    }
    try:
        with open(f"{name}_metadata.json", 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
    except:
        pass

# ================ 主程序 ================
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.chdir(OUTPUT_DIR)
    
    url_pairs = load_urls_from_file("../" + URL_LIST_FILE)
    if not url_pairs:
        return

    # 启动 undetected_chromedriver（最强防检测）
    driver = uc.Chrome(options=chrome_options)
    driver.set_page_load_timeout(35)

    print(f"\n=== 终极版隐私政策爬虫启动（集成所有推荐功能）{len(url_pairs)} 个平台 ===\n")

    for i, (url, name) in enumerate(url_pairs, 1):
        filename_base = name
        print(f"[{i:3d}/{len(url_pairs)}] {name}")

        if SKIP_EXISTING and (os.path.exists(f"{filename_base} 隐私政策.txt") or os.path.exists(f"{filename_base} 隐私政策.html")):
            print("  已存在，跳过")
            continue

        # PDF 快速处理
        if url.lower().endswith('.pdf'):
            try:
                r = requests.get(url, headers={'User-Agent': get_random_ua()}, timeout=15)
                with open(f"{filename_base}.pdf", 'wb') as f: f.write(r.content)
                save_metadata(name, url, url, False, len(r.content), "pdf", "success")
                print(f"  √ PDF 已保存")
            except: 
                print("  × PDF 下载失败")
            continue

        success = False
        used_fallback = False
        final_url = url

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # 指数退避
                if attempt > 1:
                    backoff = (2 ** (attempt - 1)) + random.uniform(0, 3)
                    print(f"  重试等待 {backoff:.1f} 秒...")
                    time.sleep(backoff)

                driver.get(url)
                WebDriverWait(driver, 18).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                handle_cookie_banner(driver)

                # 判断是否需要 fallback
                body_text = driver.find_element(By.TAG_NAME, "body").text
                page_title = driver.title.lower()
                is_bad = (requires_login(driver) or len(body_text) < 400 or 
                         any(k in (page_title + body_text.lower()) for k in ["404", "not found", "无法找到", "页面不存在", "403", "forbidden"]))

                if is_bad:
                    print("  ! 直接链接失效 → 触发官网自动查找")
                    if try_fallback_to_homepage(driver, url, name):
                        used_fallback = True
                        final_url = driver.current_url
                        handle_cookie_banner(driver)
                    else:
                        print("  × 官网查找失败，放弃该平台")
                        break

                # 展开 + 滚动 + 锚点
                expand_all_collapsible(driver)
                scroll_and_follow_anchors(driver)

                visible_text = driver.find_element(By.TAG_NAME, "body").text.strip()
                final_url = driver.current_url

                if len(visible_text) > 800:
                    with open(f"{filename_base} 隐私政策.txt", 'w', encoding='utf-8') as f:
                        f.write(visible_text)
                    print(f"  √ 保存展开后的可视化文本 ({len(visible_text):,} 字符)")
                    save_metadata(name, url, final_url, used_fallback, len(visible_text), "txt", "success")
                    success = True
                else:
                    full_html = driver.page_source
                    with open(f"{filename_base} 隐私政策.html", 'w', encoding='utf-8') as f:
                        f.write(full_html)
                    print(f"  √ 文本过短 → 保存完整HTML ({len(full_html):,} 字符)")
                    save_metadata(name, url, final_url, used_fallback, len(full_html), "html", "success")
                    success = True
                break

            except Exception as e:
                print(f"  尝试 {attempt}/{MAX_RETRIES} 失败 → {str(e)[:150]}")
                if attempt == MAX_RETRIES:
                    save_metadata(name, url, final_url, used_fallback, 0, "none", "failed")

        if not success:
            print("  × 该平台完全抓取失败（已尝试官网查找 + 重试）")

        time.sleep(BASE_DELAY + random.uniform(0, 2.0))

    driver.quit()
    print("\n=== 全部处理完成！所有文件 + metadata.json 已保存在 ./隐私政策文本/ 文件夹 ===")
    print("提示：每个平台都附带 _metadata.json，可用于后续批量分析")

if __name__ == '__main__':
    # 安装依赖提醒（首次运行前执行一次）
    print("首次运行请确保已执行：pip install undetected-chromedriver selenium requests beautifulsoup4")
    main()