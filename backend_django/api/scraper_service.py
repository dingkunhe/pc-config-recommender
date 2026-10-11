import requests
from bs4 import BeautifulSoup
import time
import random
import json
import threading
import math
import re
from datetime import datetime
from requests.exceptions import RequestException
from urllib.parse import urlparse
from .models import Hardware, PriceHistory, ScraperRun
from .hardware_cleaner import infer_category_key
from .llm_client import invoke_with_config

# 全局状态，用于前端轮询进度
scrape_status = {
    'is_running': False,
    'total_scraped': 0,
    'current_task': '空闲',
    'logs': [],
    'should_stop': False,
    'current_run_id': None
}

CATEGORIES = [
    {"name": "CPU", "url": "https://detail.zol.com.cn/cpu/"},
    {"name": "显卡", "url": "https://detail.zol.com.cn/vga/"},
    {"name": "主板", "url": "https://detail.zol.com.cn/motherboard/"},
    {"name": "内存", "url": "https://detail.zol.com.cn/memory/"},
    {"name": "硬盘", "url": "https://detail.zol.com.cn/solid_state_drive/"},
    {"name": "电源", "url": "https://detail.zol.com.cn/power/"},
    {"name": "机箱", "url": "https://detail.zol.com.cn/case/"},
    {"name": "散热器", "url": "https://detail.zol.com.cn/cooling_product/"},
    {"name": "笔记本电脑", "url": "https://detail.zol.com.cn/notebook/"},
    {"name": "显示器", "url": "https://detail.zol.com.cn/lcd/"},
    {"name": "键盘", "url": "https://detail.zol.com.cn/keyboard/"},
    {"name": "鼠标", "url": "https://detail.zol.com.cn/mice/"},
    {"name": "耳机", "url": "https://detail.zol.com.cn/headphone/"},
    {"name": "音箱", "url": "https://detail.zol.com.cn/speaker/"}
]

CATEGORY_NAME_TO_KEY = {
    'CPU': 'cpu',
    '显卡': 'gpu',
    '主板': 'motherboard',
    '内存': 'memory',
    '硬盘': 'storage',
    '电源': 'psu',
    '机箱': 'case',
    '散热器': 'cooler',
    '笔记本电脑': 'laptop',
    '显示器': 'monitor',
    '键盘': 'keyboard',
    '鼠标': 'mouse',
    '耳机': 'headphone',
    '音箱': 'speaker',
}

CATEGORY_ALLOWED_PATH_PREFIXES = {
    'CPU': ['/cpu/'],
    '显卡': ['/vga/'],
    '主板': ['/motherboard/'],
    '内存': ['/memory/'],
    '硬盘': ['/solid_state_drive/', '/hard_disk/'],
    '电源': ['/power/'],
    '机箱': ['/case/'],
    '散热器': ['/cooling_product/'],
    '笔记本电脑': ['/notebook/'],
    '显示器': ['/lcd/'],
    '键盘': ['/keyboard/'],
    '鼠标': ['/mice/', '/Ergonomics_mouse/'],
    '耳机': ['/headphone/'],
    '音箱': ['/speaker/'],
}

CATEGORY_PARAMS_SCHEMA = {
    "CPU": "型号、品牌、核心数、线程数、最大频率、热设计功耗、是否集成显卡、适合场景",
    "显卡": "型号、品牌、显存容量、功耗、适合场景",
    "主板": "型号、品牌、芯片组、CPU插槽、内存插槽数量、支持内存类型、最大内存容量、PCIe x16插槽数量、M.2插槽数量、板型",
    "内存": "型号、品牌、类型、容量、频率、CL时序、电压",
    "硬盘": "型号、品牌、类型、容量、接口、顺序读取速度、顺序写入速度",
    "电源": "型号、品牌、额定功率、80Plus认证、模组类型、PCIe接口数量",
    "机箱": "型号、品牌、类型、支持主板板型、显卡限长、CPU散热器限高",
    "散热器": "型号、品牌、类型、热管数量、风扇尺寸、兼容插槽、解热能力",
    "笔记本电脑": "型号、品牌、CPU型号、显卡型号、内存容量、硬盘容量、屏幕尺寸、分辨率、刷新率、重量、电池容量、适合场景",
    "显示器": "型号、品牌、屏幕尺寸、分辨率、面板类型、刷新率、响应时间、亮度、色域、同步技术、接口、适合场景",
    "键盘": "型号、品牌、类型、轴体类型、按键数量、连接方式、背光、续航时间（无线）、人体工学设计、适合场景",
    "鼠标": "型号、品牌、传感器类型、最高DPI、按键数量、连接方式、重量、续航时间（无线）、人体工学设计、适合场景",
    "耳机": "型号、品牌、类型、连接方式、环绕声、是否带麦克风、主动降噪、续航时间（无线）、阻抗、频率响应、适合场景",
    "音箱": "型号、品牌、声道数、总功率、连接方式、蓝牙版本、频率响应、适合场景"
}

SHENLONG_PROXY_API = "http://api.shenlongip.com/ip?key=otn89a85&protocol=2&mr=1&pattern=txt&count=1&sign=7fc17e55b9e19a022fb61874696737ef"
PROXY_VALIDATE_URLS = [
    "https://httpbin.org/ip",
    "https://detail.zol.com.cn/",
]
_proxy_cache = {
    'proxy_url': None,
    'fetched_at': 0,
}


def _fetch_proxy_from_shenlong():
    """从神龙HTTP获取一个代理IP，返回形如 http://ip:port 的URL。"""
    try:
        resp = requests.get(SHENLONG_PROXY_API, timeout=8)
        if resp.status_code != 200:
            return None
        raw = (resp.text or '').strip()
        if not raw:
            return None
        first_line = raw.splitlines()[0].strip()
        if not first_line:
            return None
        if first_line.startswith('http://') or first_line.startswith('https://'):
            return first_line
        return f"http://{first_line}"
    except Exception:
        return None


def _validate_proxy(proxy_url):
    """验证代理是否真正可用：通过代理访问测试URL并确认返回200。"""
    proxies = {'http': proxy_url, 'https': proxy_url}
    test_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36 ProxyValidator/1.0"
    }

    for test_url in PROXY_VALIDATE_URLS:
        try:
            resp = requests.get(test_url, proxies=proxies, headers=test_headers, timeout=6)
            if resp.status_code == 200 and (resp.text or '').strip():
                return True
        except RequestException:
            continue
        except Exception:
            continue

    return False


def _get_proxy(force_refresh=False):
    """获取代理并做短时缓存，避免每个请求都拉取新IP。"""
    cache_ttl = 60
    now = time.time()
    need_refresh = (
        force_refresh
        or not _proxy_cache['proxy_url']
        or (now - _proxy_cache['fetched_at']) > cache_ttl
    )

    if need_refresh:
        proxy_url = None
        for i in range(3):
            candidate = _fetch_proxy_from_shenlong()
            if not candidate:
                continue

            if _validate_proxy(candidate):
                proxy_url = candidate
                break
            else:
                log_msg(f"警告：代理有效性验证失败，丢弃并重试({i+1}/3): {candidate}")
                time.sleep(0.6)

        if proxy_url:
            _proxy_cache['proxy_url'] = proxy_url
            _proxy_cache['fetched_at'] = now
            log_msg(f"代理池已更新可用代理IP: {_proxy_cache['proxy_url']}")
        else:
            log_msg("警告：神龙HTTP代理获取或验证失败，将尝试沿用旧代理或直连")

    if _proxy_cache['proxy_url']:
        return {
            'http': _proxy_cache['proxy_url'],
            'https': _proxy_cache['proxy_url'],
        }
    return None


def _request_get_with_proxy(url, headers=None, timeout=10, max_retries=3, try_direct_first=True):
    """对目标URL执行请求：优先直连，失败/被拦截后切换代理重试。"""
    direct_tried = False

    if try_direct_first:
        direct_tried = True
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                return resp
            if resp.status_code in (403, 429, 503):
                log_msg(f"直连被拦截(状态码 {resp.status_code})，准备切换代理重试: {url}")
        except RequestException as e:
            log_msg(f"直连请求失败，准备切换代理重试: {str(e)[:120]}")

    for attempt in range(1, max_retries + 1):
        proxies = _get_proxy(force_refresh=(attempt > 1))
        try:
            resp = requests.get(url, headers=headers, timeout=timeout, proxies=proxies)
            if resp.status_code == 200:
                return resp

            if resp.status_code in (403, 429, 503):
                log_msg(f"请求被拦截(状态码 {resp.status_code})，准备切换代理重试: {url}")
            else:
                log_msg(f"请求异常状态码 {resp.status_code}，准备重试: {url}")
        except RequestException as e:
            log_msg(f"代理请求失败({attempt}/{max_retries}): {str(e)[:120]}")

        time.sleep(random.uniform(1.0, 2.0))

    # 兜底：若之前未做过直连，则再尝试一次直连
    if not direct_tried:
        try:
            log_msg(f"代理多次失败，兜底直连: {url}")
            return requests.get(url, headers=headers, timeout=timeout)
        except RequestException:
            return None
    return None


def _extract_detail_links_from_soup(soup, allowed_path_prefixes=None):
    """从列表页提取详情链接（去重、去参数、仅保留合法详情页）。"""
    links = []
    seen = set()

    for a in soup.find_all('a', href=True):
        href = (a['href'] or '').strip()
        if not href:
            continue
        if '?' in href:
            continue

        # ZOL 详情页常见形态：.../index123456.shtml
        if not re.search(r'index\d+\.shtml(?:$|[#/].*)?', href):
            continue

        if href.startswith('//'):
            full_link = "https:" + href
        elif href.startswith('/'):
            full_link = "https://detail.zol.com.cn" + href
        elif href.startswith('http'):
            full_link = href
        else:
            continue

        parsed = urlparse(full_link)
        if parsed.netloc != 'detail.zol.com.cn':
            continue

        if allowed_path_prefixes:
            if not any(parsed.path.startswith(prefix) for prefix in allowed_path_prefixes):
                continue

        normalized = f"https://{parsed.netloc}{parsed.path}"
        if normalized not in seen:
            seen.add(normalized)
            links.append(normalized)

    return links


def _estimate_category_capacity(base_url, soup, html_text, page_size_hint):
    """估算分类可抓取规模，返回 (estimated_total_items, detected_total_pages)。"""
    estimated_total = 0
    detected_total_pages = 0

    # 1) 从文本或脚本中提取总数
    text = soup.get_text(" ", strip=True)
    total_patterns = [
        r'共\s*([\d,]+)\s*款',
        r'([\d,]+)\s*款产品',
        r'"total(?:Num|Count)"\s*[:=]\s*(\d+)',
        r'pageData\.total\s*=\s*(\d+)',
    ]
    for p in total_patterns:
        m = re.search(p, text) or re.search(p, html_text)
        if m:
            try:
                estimated_total = int(m.group(1).replace(',', ''))
                if estimated_total > 0:
                    break
            except Exception:
                pass

    # 2) 从分页链接中提取最大页码
    base_path = (urlparse(base_url).path or '/').rstrip('/') + '/'
    page_nums = []
    for a in soup.find_all('a', href=True):
        href = (a.get('href') or '').strip()
        if not href:
            continue

        # 兼容绝对/相对两种页码链接
        if href.startswith('http'):
            p = urlparse(href).path
        else:
            p = href

        m = re.search(r'/(\d+)\.html$', p)
        if not m:
            continue
        if base_path and base_path not in p:
            continue
        try:
            page_nums.append(int(m.group(1)))
        except Exception:
            pass

    if page_nums:
        detected_total_pages = max(page_nums)

    # 3) 若无总数，按页数 * 每页商品数估算
    if estimated_total <= 0 and detected_total_pages > 0 and page_size_hint > 0:
        estimated_total = detected_total_pages * page_size_hint

    return estimated_total, detected_total_pages

def log_msg(msg):
    time_str = datetime.now().strftime('%H:%M:%S')
    log_line = f"[{time_str}] {msg}"
    print(log_line)
    scrape_status['logs'].append(log_line)
    # 仅保留最近的50条日志
    if len(scrape_status['logs']) > 50:
        scrape_status['logs'].pop(0)
    
    # 写入数据库
    run_id = scrape_status.get('current_run_id')
    if run_id:
        try:
            run_record = ScraperRun.objects.get(id=run_id)
            run_record.log_text += log_line + '\n'
            run_record.save(update_fields=['log_text'])
        except Exception:
            pass

def enhance_with_ai(raw_text, category_name="硬件"):
    """
    使用数据库中的 API 配置调用 AI：
    根据类别名抓取相应的重点参数并形成规整格式。与推荐系统共用一套 AI。
    """
    from .models import ApiConfig
    configs = list(ApiConfig.objects.filter(is_active=True).order_by('-is_primary', 'id'))
    if not configs:
        log_msg("无可用API配置，跳过数据清洗")
        return None

    target_params = CATEGORY_PARAMS_SCHEMA.get(category_name, "核心参数")
    
    prompt = f"""
    你是一个专业的电脑硬件数据清洗助手。
    当前被抓取的商品类别为：【{category_name}】。
    请从以下中关村在线的原始抓取文本中提取信息，并以严格且合法的 JSON 格式返回，不要包含 markdown 代码块标记，不要多余字符。
    必须包含以下键：
    "name": 字符串，产品全称
    "brand": 字符串，品牌
    "model": 字符串，具体型号
    "price": 数字，如果没有提取到价格请填 0
    "desc": 字符串。请你将原文本中的相关参数提炼为一段文本，对于该类别，请务必重点关注并涵盖：{target_params}。
    
    原始文本：
    {raw_text[:800]}
    """
    
    for config in configs:
        messages = [{"role": "user", "content": prompt}]

        try:
            ok, content = invoke_with_config(
                config=config,
                messages=messages,
                temperature=0.1,
                timeout=20,
            )
            if ok:
                content = content.replace('```json', '').replace('```', '').strip()
                return json.loads(content)
            else:
                log_msg(f"API {config.name} 返回错误: {content}")
        except Exception as e:
            log_msg(f"API {config.name} 调用异常: {e}")
            continue
            
    log_msg("所有配置的 AI API 均未能成功提取数据")
    return None

 
def run_spider(max_items=10):
    """
    后台爬虫主线程。
    严格遵守 robots.txt 约束：控制延时，伪装 UA，过滤所有带 '?' 的动态参数 URL。
    """
    scrape_status['is_running'] = True
    scrape_status['total_scraped'] = 0
    scrape_status['logs'] = []
    scrape_status['current_task'] = '正在启动爬虫，初始化目标列表...'
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36 ZOLDataCrawler/1.0"
    }
    
    try:
        log_msg("开始多分类商品抓取流程...")
        
        for category in CATEGORIES:
            cat_name = category['name']
            base_url = category['url']
            
            if scrape_status.get('should_stop'):
                log_msg("接收到停止指令，不再请求新的分类。")
                break
                
            scrape_status['current_task'] = f'正在请求分类首页: {cat_name}'
            log_msg(f"===== 开始抓取分类：{cat_name} ({base_url}) =====")
            
            links = []
            allowed_prefixes = CATEGORY_ALLOWED_PATH_PREFIXES.get(cat_name, [])
            estimated_total_items = 0
            detected_total_pages = 0
            # 动态分页抓取：默认至少扫3页；若可解析到总页数，按需增加扫描上限
            max_scan_pages = 3
            page = 1

            while page <= max_scan_pages and len(links) < max_items:
                page_url = base_url if page == 1 else f"{base_url}{page}.html"
                try:
                    # 法律与防封禁合规：在对列表页的每次翻页请求前也强制休眠 3~5 秒。
                    page_sleep = random.uniform(3.0, 5.0)
                    log_msg(f"合规休眠 {page_sleep:.2f} 秒后请求列表页...")
                    time.sleep(page_sleep)
                    
                    res = _request_get_with_proxy(page_url, headers=headers, timeout=10, max_retries=3)

                    # 某些分类对 https 更敏感，尝试 http 回退
                    if (not res or res.status_code != 200) and page_url.startswith('https://'):
                        alt_page_url = 'http://' + page_url[len('https://'):]
                        log_msg(f"列表页回退尝试 HTTP: {alt_page_url}")
                        alt_res = _request_get_with_proxy(alt_page_url, headers=headers, timeout=10, max_retries=2)
                        if alt_res and alt_res.status_code == 200:
                            res = alt_res

                    if not res:
                        log_msg(f"分类 {cat_name} 第 {page} 页请求失败(代理与直连均失败)")
                        time.sleep(2)
                        page += 1
                        continue
                    if res.status_code != 200:
                        log_msg(f"分类 {cat_name} 第 {page} 页请求被拦截 (状态码: {res.status_code})")
                        time.sleep(2)
                        page += 1
                        continue
                        
                    res.encoding = 'gbk' # ZOL 通常使用 gbk
                    soup = BeautifulSoup(res.text, 'html.parser')

                    page_links = _extract_detail_links_from_soup(soup, allowed_path_prefixes=allowed_prefixes)
                    for item_link in page_links:
                        if item_link not in links:
                            links.append(item_link)

                    # 仅首屏做容量估算，并据此动态调整扫描页数
                    if page == 1:
                        page_size_hint = len(page_links)
                        estimated_total_items, detected_total_pages = _estimate_category_capacity(
                            base_url=base_url,
                            soup=soup,
                            html_text=res.text,
                            page_size_hint=page_size_hint
                        )

                        pages_needed_for_target = max(3, math.ceil(max_items / max(page_size_hint, 1)) + 1)
                        if detected_total_pages > 0:
                            max_scan_pages = min(max(detected_total_pages, pages_needed_for_target), 80)
                        else:
                            max_scan_pages = min(pages_needed_for_target, 20)

                    page += 1
                except Exception as eval_err:
                    log_msg(f"获取 {cat_name} 列表页 {page} 异常: {eval_err}")
                    page += 1
                    continue
            
            # 使用列表截取保证准确满足请求数据量
            links = links[:max_items]
            if estimated_total_items > 0:
                log_msg(f"在【{cat_name}】分类估算全站可抓取约 {estimated_total_items} 个详情页；本次按设置准备抓取 {len(links)} 个。")
            else:
                log_msg(f"在【{cat_name}】分类共准备抓取合法详情页 {len(links)} 个。")
            if detected_total_pages > 0:
                log_msg(f"【{cat_name}】检测到分页约 {detected_total_pages} 页，本次实际扫描 {min(page - 1, max_scan_pages)} 页。")
            
            for i, link in enumerate(links):
                if scrape_status.get('should_stop'):
                    log_msg("接收到停止指令，爬虫已手工中断。")
                    scrape_status['current_task'] = '已中断'
                    break
                    
                scrape_status['current_task'] = f'【{cat_name}】抓取 ({i+1}/{max_items}): {link}'
                log_msg(f"正在访问 (类别:{cat_name}): {link}")
                
                # --- 严控请求频率以规避封禁与法律风险 ---
                # 将休眠时间延长至真正安全的区间：2~4秒，而且放到实际发出网络请求的正前方
                sleep_time = random.uniform(2.0, 4.0)
                log_msg(f"合规休眠 {sleep_time:.2f} 秒，即将执行 {link} 的抓取任务。")
                time.sleep(sleep_time)
                
                try:
                    # 获取当前真实模拟的 User-Agent
                    current_ua = headers.get('User-Agent')
                    log_msg(f"使用标识: {current_ua[:35]}...")
                    
                    detail_res = _request_get_with_proxy(link, headers=headers, timeout=10, max_retries=3)
                    if not detail_res:
                        log_msg("警告：详情页请求失败(代理与直连均失败)，跳过。")
                        continue
                    
                    # 防反爬拦截：如果访问未成功，可能是被封IP或触发了频率限制
                    if detail_res.status_code != 200:
                        log_msg(f"警告：该页面访问返回异常状态码 {detail_res.status_code}，非正常商品页！")
                        # 休眠一下避免被封挡更久
                        time.sleep(2)
                        continue

                    detail_res.encoding = 'gbk'
                    detail_soup = BeautifulSoup(detail_res.text, 'html.parser')
                    
                    # 抽取核心的标题、价格和参数概览节点，避免抓到顶部无用的导航菜单干扰 AI
                    title_tag = detail_soup.find('h1')
                    title = title_tag.text.strip() if title_tag else ''
                    
                    # 如果没有正常提取到商品标题，或者标题里含有 503 等网关屏蔽特征说明页面被盾了
                    if not title or '503' in title or 'Service' in title or 'Error' in title:
                        log_msg(f"警告：未成功解析到商品标题，或被服务网关拦截 (检测到 {title[:15]})，跳过。")
                        continue
                    
                    price_tag = detail_soup.find(class_='price-type')
                    price = price_tag.text.strip() if price_tag else '暂无报价'
                    
                    param_tag = detail_soup.find(class_='product-param-item')
                    param_text = param_tag.get_text(separator=' ', strip=True) if param_tag else ''
                    
                    raw_text = f"商品名称: {title}\n商品参考价: {price}\n主要参数: {param_text}\n链接: {link}"
                    
                    log_msg("开始调用 AI 进行数据清洗和参数提取(共用推荐系统API)...")
                    # 传入当前分类名称以便 AI 对症下药
                    structured_data = enhance_with_ai(raw_text, category_name=cat_name)
                    
                    if structured_data and isinstance(structured_data, dict):
                        # 数据入库
                        name = structured_data.get('name', '未知硬件')
                        brand_val = structured_data.get('brand', '')
                        model_val = structured_data.get('model', '')
                        desc = structured_data.get('desc', '')
                        expected_category_key = CATEGORY_NAME_TO_KEY.get(cat_name, 'other')
                        category_key = infer_category_key(name=name, desc=desc, current=expected_category_key)
                        if category_key != expected_category_key:
                            log_msg(f"分类纠偏: {name[:40]}... 由 {expected_category_key} 修正为 {category_key}")
                        raw_price = structured_data.get('price', 0)
                        try:
                            price_val = float(raw_price)
                        except (ValueError, TypeError):
                            price_val = 0.0
                        
                        hw, created = Hardware.objects.update_or_create(
                            name=name, model=model_val,
                            defaults={
                                'category': category_key,
                                'brand': brand_val,
                                'description': f"[经智谱AI强化] {desc}"
                            }
                        )
                        
                        # 记录价格历史
                        PriceHistory.objects.create(
                            hardware=hw,
                            date=datetime.now().strftime('%Y-%m-%d'),
                            price=price_val
                        )
                        log_msg(f"入库成功: {name} - 价格 ¥{price_val}")
                        scrape_status['total_scraped'] += 1
                    else:
                        log_msg("大模型未能成功提取该页面的有效 JSON 硬件结构")
                        
                except Exception as item_err:
                    log_msg(f"单页抓取失败 {link}: {str(item_err)}")
                
    except Exception as main_err:
        log_msg(f"爬虫主进程异常: {str(main_err)}")
        
    finally:
        if not scrape_status.get('should_stop'):
            scrape_status['current_task'] = '爬虫任务结束'
            log_msg("所有更新任务执行完毕。")
        
        # 结束记录
        run_id = scrape_status.get('current_run_id')
        if run_id:
            try:
                run_record = ScraperRun.objects.get(id=run_id)
                run_record.end_time = datetime.now()
                run_record.status = 'manually_stopped' if scrape_status.get('should_stop') else 'completed'
                run_record.save()
            except Exception:
                pass
            scrape_status['current_run_id'] = None

        scrape_status['is_running'] = False
        scrape_status['should_stop'] = False

def start_background_spider(max_items=10):
    if scrape_status['is_running']:
        return False, "爬虫已经在运行中"

    scrape_status['should_stop'] = False

    # 创建新日志记录
    new_run = ScraperRun.objects.create(status='running', log_text='')
    scrape_status['current_run_id'] = new_run.id
    
    t = threading.Thread(target=run_spider, args=(max_items,))
    t.daemon = True
    t.start()
    
    return True, "数据更新进程已在后台启动"

def stop_background_spider():
    if scrape_status['is_running']:
        scrape_status['should_stop'] = True
        return True, "已发送中断信号，爬虫将在当前操作完成后停止"
    return False, "当前没有运行的任务"