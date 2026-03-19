"""
相比于前面sec和thd的版本，去除了登录绕过，改为先跳到官网首页自动寻找隐私政策链接（如果直接访问失败），
并且增加了登录窗口的智能检测和绕过尝试（先访问隐私页再判定）。同时增加了对折叠内容的全面展开和内部锚点的自动滚动，
提升爬取完整性的成功率。最后根据内容长度智能选择保存纯文本或完整HTML，确保即使页面结构复杂也能保留信息。
使用前请确保已安装必要的库（requests, beautifulsoup4, selenium, webdriver_manager）并且有稳定的网络环境。
2026-3-19 第一次测试
"""
import requests
from bs4 import BeautifulSoup
import re
import os
import time
import random
from urllib.parse import urlparse

# ================ Selenium 核心 ================
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ================ 配置区 ================
URL_LIST_FILE = "privacy_policy_urls.txt"      # ← 你的链接文件（放在脚本同目录）
OUTPUT_DIR = "隐私政策文本"
SKIP_EXISTING = True
BASE_DELAY = 2.8
MAX_RETRIES = 2

# Selenium 配置（推荐先用有头模式调试，稳定后再改 headless）
chrome_options = Options()
chrome_options.add_argument("--lang=zh-CN,zh")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
chrome_options.add_experimental_option('useAutomationExtension', False)
# chrome_options.add_argument("--headless=new")   # ← 正式运行时取消注释加速

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36'}

# =====================================================================
# 新增：隐私政策关键词（中英文全覆盖）
# =====================================================================
PRIVACY_KEYWORDS = [
    "隐私政策", "隐私声明", "隐私", "用户隐私", "个人信息保护",
    "Privacy Policy", "privacy", "legal", "terms", "agreement", "用户协议"
]

def parse_url_line(line: str):
    line = line.strip()
    if not line or line.startswith('#'):
        return "", ""
    parts = re.split(r'\s{2,}|\t+|,', line, maxsplit=1)
    url = parts[0].strip()
    name = (parts[1].strip() if len(parts) > 1 else 
            urlparse(url).netloc.replace("www.", "").split(".")[0].capitalize() + " 隐私政策")
    name = re.sub(r'[<>:"/\\|?*]', '_', name).strip()
    return url, name

def load_urls_from_file(filepath):
    if not os.path.exists(filepath):
        print(f"× 文件不存在：{filepath}")
        return []
    pairs = [parse_url_line(line) for line in open(filepath, encoding='utf-8') if parse_url_line(line)[0]]
    print(f"从 {filepath} 读取到 {len(pairs)} 条链接")
    return pairs

def get_homepage(url: str) -> str:
    """从任意隐私政策链接自动生成官网首页"""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"

def find_privacy_link(driver):
    """在官网首页自动查找并返回第一个最匹配的隐私政策链接"""
    links = driver.find_elements(By.TAG_NAME, "a")
    candidates = []
    
    for link in links:
        text = (link.text or "").strip()
        href = link.get_attribute("href") or ""
        if not href:
            continue
        
        # 优先级打分
        score = 0
        lower_text = text.lower()
        lower_href = href.lower()
        
        for kw in PRIVACY_KEYWORDS:
            if kw.lower() in lower_text:
                score += 10
            if kw.lower() in lower_href:
                score += 5
        
        if score > 0:
            candidates.append((score, link))
    
    if candidates:
        # 按分数降序，取最高分
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_link = candidates[0][1]
        href = best_link.get_attribute("href")
        print(f"  √ 在官网找到隐私政策链接 → {href}")
        return best_link
    return None

def is_login_blocked(driver):
    """检测是否被登录窗口阻挡（新逻辑：只在内容极短时才判定）"""
    body_text = driver.find_element(By.TAG_NAME, "body").text.strip()
    page_lower = driver.page_source.lower()
    
    login_indicators = ["登录", "请登录", "立即登录", "sign in", "login required", "auth"]
    has_login = any(k in page_lower for k in login_indicators)
    
    # 只有“有登录提示 + 正文极短”才视为被阻挡
    return has_login and len(body_text) < 600

def expand_all_collapsible(driver):
    """模拟鼠标点击展开所有折叠内容 + JS强制显示"""
    for summary in driver.find_elements(By.TAG_NAME, "summary"):
        try:
            driver.execute_script("arguments[0].click();", summary)
            time.sleep(0.3)
        except: pass
    
    for btn in driver.find_elements(By.XPATH, "//*[contains(@class,'accordion') or contains(@class,'collapse') or @aria-expanded='false']"):
        try:
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(0.3)
        except: pass
    
    driver.execute_script("""
        document.querySelectorAll('.collapse, .accordion-collapse, [aria-hidden="true"], .hidden, [style*="display: none"], [style*="visibility: hidden"]')
        .forEach(el => {
            el.style.display = 'block';
            el.style.visibility = 'visible';
            el.setAttribute('aria-hidden', 'false');
            if (el.hasAttribute('aria-expanded')) el.setAttribute('aria-expanded', 'true');
        });
    """)
    time.sleep(1.2)

def scroll_and_follow_anchors(driver):
    """滚动到底 + 自动跳转所有内部锚点链接"""
    for _ in range(8):
        driver.execute_script("window.scrollBy(0, window.innerHeight * 0.85);")
        time.sleep(0.6)
    
    for a in driver.find_elements(By.TAG_NAME, "a"):
        href = a.get_attribute("href") or ""
        if href.startswith("#") and len(href) > 2:
            try:
                driver.execute_script("document.querySelector(arguments[0]).scrollIntoView({behavior: 'smooth'});", href)
                time.sleep(0.4)
            except: pass
    
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(1.5)

def download_privacy_policy(driver, url: str, name: str):
    filename_base = name
    print(f"\n→ {name}\n  原始链接：{url}")
    
    if SKIP_EXISTING and (os.path.exists(f"{filename_base} 隐私政策.txt") or os.path.exists(f"{filename_base} 隐私政策.html")):
        print("  已存在，跳过")
        return True
    
    success = False
    current_url = url
    
    for attempt in range(MAX_RETRIES):
        try:
            driver.get(current_url)
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(2)   # 等待动态加载
            
            # ==================== 新功能1：无法直接进入 → 自动 fallback 到官网找链接 ====================
            body_text = driver.find_element(By.TAG_NAME, "body").text.strip()
            title = driver.title.lower()
            
            if len(body_text) < 400 or "404" in title or "not found" in title or "无法访问" in title:
                print("  × 直接隐私页面加载异常（内容过短/404），尝试 fallback 到官网...")
                homepage = get_homepage(current_url)
                driver.get(homepage)
                WebDriverWait(driver, 12).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                time.sleep(2)
                
                privacy_link = find_privacy_link(driver)
                if privacy_link:
                    privacy_link.click()
                    WebDriverWait(driver, 12).until(lambda d: d.current_url != homepage)
                    current_url = driver.current_url
                    print(f"  → 已跳转到找到的隐私政策页：{current_url}")
                    time.sleep(2)
                else:
                    print("  × 官网也未找到隐私政策链接，放弃该平台")
                    break
            
            # ==================== 新功能2：登录窗口处理（先尝试跳转隐私页，再判定） ====================
            if is_login_blocked(driver):
                print("  ! 检测到登录窗口，先尝试再次跳转隐私政策页...")
                # 强制再访问一次当前隐私URL（很多站点从官网点击后可绕过弹窗）
                driver.get(current_url)
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                time.sleep(2)
                
                if is_login_blocked(driver):
                    print("  × 登录窗口仍存在，无法绕过，跳过该URL")
                    break
                else:
                    print("  √ 登录窗口已消失，继续爬取")
            
            # ==================== 正常爬取流程 ====================
            expand_all_collapsible(driver)
            scroll_and_follow_anchors(driver)
            
            visible_text = driver.find_element(By.TAG_NAME, "body").text.strip()
            
            if len(visible_text) > 800:
                with open(f"{filename_base} 隐私政策.txt", 'w', encoding='utf-8') as f:
                    f.write(visible_text)
                print(f"  √ 保存可视化展开文本 ({len(visible_text):,} 字符)")
                success = True
            else:
                full_html = driver.page_source
                with open(f"{filename_base} 隐私政策.html", 'w', encoding='utf-8') as f:
                    f.write(full_html)
                print(f"  √ 文本不足 → 保存完整HTML ({len(full_html):,} 字符)")
                success = True
            
            break
            
        except Exception as e:
            print(f"  尝试 {attempt+1} 失败 → {str(e)[:120]}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(4)
    
    if not success:
        print("  × 所有尝试失败（含 fallback），放弃该URL")
    
    return success

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.chdir(OUTPUT_DIR)
    
    url_pairs = load_urls_from_file("../" + URL_LIST_FILE)
    if not url_pairs:
        return
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.set_page_load_timeout(35)
    
    print(f"\n=== 开始增强版 Selenium 爬取（支持官网自动查找 + 登录窗口智能绕过） ===\n")
    
    for i, (url, name) in enumerate(url_pairs, 1):
        print(f"[{i:3d}/{len(url_pairs)}]")
        download_privacy_policy(driver, url, name)
        time.sleep(BASE_DELAY + random.uniform(0, 2.0))
    
    driver.quit()
    print("\n=== 全部处理完成！文件保存在 ./隐私政策文本/ 文件夹 ===")

if __name__ == '__main__':
    main()