import re

CATEGORY_LABEL_MAP = {
    'cpu': 'CPU',
    'gpu': '显卡',
    'motherboard': '主板',
    'memory': '内存',
    'storage': '硬盘',
    'psu': '电源',
    'case': '机箱',
    'cooler': '散热器',
    'laptop': '笔记本电脑',
    'monitor': '显示器',
    'keyboard': '键盘',
    'mouse': '鼠标',
    'headphone': '耳机',
    'speaker': '音箱',
    'other': '其他',
}

CATEGORY_ALIAS_TO_KEY = {
    'cpu': 'cpu', '处理器': 'cpu', '中央处理器': 'cpu',
    'gpu': 'gpu', '显卡': 'gpu',
    '主板': 'motherboard', 'motherboard': 'motherboard',
    '内存': 'memory', 'memory': 'memory',
    '硬盘': 'storage', 'ssd': 'storage', 'hdd': 'storage', '存储': 'storage',
    '电源': 'psu', 'psu': 'psu',
    '机箱': 'case',
    '散热器': 'cooler', '散热': 'cooler',
    '笔记本电脑': 'laptop', '笔记本': 'laptop', 'notebook': 'laptop', 'laptop': 'laptop',
    '显示器': 'monitor', 'monitor': 'monitor',
    '键盘': 'keyboard', 'keyboard': 'keyboard',
    '鼠标': 'mouse', 'mouse': 'mouse',
    '耳机': 'headphone', 'headphone': 'headphone', 'headset': 'headphone',
    '音箱': 'speaker', 'speaker': 'speaker',
}

# 分值越高权重越大，便于压过错误的 current 类别
_CATEGORY_KEYWORDS = {
    'cpu': {
        'strong': ['cpu', '处理器', '中央处理器', 'ryzen', '酷睿', 'threadripper'],
        'weak': ['i3', 'i5', 'i7', 'i9', '锐龙'],
    },
    'gpu': {
        'strong': ['显卡', 'gpu', 'geforce', 'radeon', 'rtx', 'gtx', 'rx 7'],
        'weak': ['显存', 'cuda'],
    },
    'motherboard': {
        'strong': ['主板', 'motherboard', '芯片组', 'lga1700', 'am5', 'socket'],
        'weak': ['b760', 'z790', 'x670', 'h610', 'b650', 'x870', 'z890', 'm-atx', 'itx'],
    },
    'memory': {
        'strong': ['内存', 'memory', '内存条'],
        'weak': ['cl16', 'cl18', '频率'],
    },
    'storage': {
        'strong': ['硬盘', 'ssd', 'hdd', 'nvme', '固态', '机械硬盘'],
        'weak': ['pcie4.0', 'pcie 4.0', '读取速度', '写入速度'],
    },
    'psu': {
        'strong': ['电源', 'psu', 'power supply', '80plus', '额定功率'],
        'weak': ['金牌', '全模组', '非模组'],
    },
    'case': {
        'strong': ['机箱', 'case', '中塔', '全塔'],
        'weak': ['atx', 'matx', 'itx 机箱'],
    },
    'cooler': {
        'strong': ['散热器', '散热', '水冷', '风冷', 'cooler'],
        'weak': ['热管', '冷排', '风扇尺寸'],
    },
    'laptop': {
        'strong': [
            '笔记本', 'notebook', 'laptop', '轻薄本', '游戏本',
            '天选', '拯救者', '暗影精灵', '灵耀', 'y9000', 'y7000', 'rog 枪神', 'matebook', 'magicbook'
        ],
        'weak': ['屏幕尺寸', '电池容量', '整机', '便携'],
    },
    'monitor': {
        'strong': ['显示器', 'monitor', 'lcd', '面板类型'],
        'weak': ['刷新率', '响应时间', '色域'],
    },
    'keyboard': {
        'strong': ['键盘', 'keyboard', '机械键盘'],
        'weak': ['轴体', '键帽', '键程'],
    },
    'mouse': {
        'strong': ['鼠标', 'mouse'],
        'weak': ['dpi', '回报率'],
    },
    'headphone': {
        'strong': ['耳机', 'headphone', 'headset'],
        'weak': ['降噪', '麦克风', '阻抗'],
    },
    'speaker': {
        'strong': ['音箱', 'speaker'],
        'weak': ['声道', '总功率'],
    },
}

# 某些词出现时，对特定类别进行扣分，抑制明显错分
_NEGATIVE_HINTS = {
    'cpu': ['笔记本', 'notebook', 'laptop', '显示器', '键盘', '鼠标', '耳机', '音箱'],
    'gpu': ['笔记本', 'notebook', 'laptop', '显示器', '键盘', '鼠标', '耳机', '音箱'],
    'motherboard': ['笔记本', 'notebook', 'laptop', '显示器', '键盘', '鼠标'],
    'memory': ['笔记本', 'notebook', 'laptop', '显示器', '键盘', '鼠标'],
    'storage': ['笔记本', 'notebook', 'laptop', '显示器', '键盘', '鼠标'],
    'psu': ['笔记本', 'notebook', 'laptop', '显示器', '键盘', '鼠标'],
    'case': ['笔记本', 'notebook', 'laptop', '显示器', '键盘', '鼠标'],
    'cooler': ['笔记本', 'notebook', 'laptop', '显示器', '键盘', '鼠标'],
}

_HIGH_CONFIDENCE_SWITCH = {
    'laptop': ['笔记本', 'notebook', 'laptop', '轻薄本', '游戏本', 'matebook', 'magicbook', 'macbook', 'thinkbook', 'thinkpad'],
    'monitor': ['显示器', 'monitor', 'ips', 'oled'],
    'keyboard': ['键盘', 'keyboard', '机械键盘'],
    'mouse': ['鼠标', 'mouse'],
    'headphone': ['耳机', 'headphone', 'headset'],
    'speaker': ['音箱', 'speaker', '2.0音箱', '2.1音箱'],
}

_MOBILE_HINTS = ['iphone', '荣耀', 'vivo', 'redmi note', '手机', 'pura', 'nova']

_CURRENT_STRONG_HINTS = {
    'cpu': ['cpu', '处理器', '酷睿', '锐龙', 'threadripper'],
    'gpu': ['显卡', 'gpu', 'rtx', 'gtx', 'radeon'],
    'motherboard': ['主板', 'motherboard', 'b760', 'z790', 'h610', 'x870'],
    'memory': ['内存', '内存条', 'ddr4', 'ddr5', 'sodimm'],
    'storage': ['硬盘', 'ssd', '固态', 'nvme', 'hdd'],
    'psu': ['电源', 'psu', '80plus', '额定功率'],
    'case': ['机箱', 'atx', 'itx', 'matx'],
    'cooler': ['散热', '散热器', '水冷', '风冷', '热管'],
    'laptop': ['笔记本', 'notebook', 'laptop', 'macbook', 'matebook'],
    'monitor': ['显示器', 'monitor', 'lcd', 'ips', 'oled'],
    'keyboard': ['键盘', 'keyboard'],
    'mouse': ['鼠标', 'mouse'],
    'headphone': ['耳机', 'headphone', 'headset'],
    'speaker': ['音箱', 'speaker'],
}


def normalize_text(value):
    if value is None:
        return ''
    return ' '.join(str(value).split())


def _score_category(text, category_key):
    cfg = _CATEGORY_KEYWORDS.get(category_key, {})
    score = 0

    for kw in cfg.get('strong', []):
        if kw in text:
            score += 5
    for kw in cfg.get('weak', []):
        if kw in text:
            score += 2

    for kw in _NEGATIVE_HINTS.get(category_key, []):
        if kw in text:
            score -= 4

    return score


def infer_category_key(name, desc='', current=''):
    current = normalize_text(current).lower()
    if current in CATEGORY_ALIAS_TO_KEY:
        current = CATEGORY_ALIAS_TO_KEY[current]

    name_text = normalize_text(name).lower()
    text = f"{name_text} {normalize_text(desc).lower()}".strip()
    if not text.strip():
        return current if current in CATEGORY_LABEL_MAP else 'other'

    # 手机/非PC硬件，直接打回 other，避免污染PC配件分类
    if any(k in text for k in _MOBILE_HINTS):
        return 'other'

    # 若当前类别有效，默认信任 current，仅在“高置信度冲突”时纠偏
    if current in CATEGORY_LABEL_MAP and current != 'other':
        is_core_category = current in {'cpu', 'gpu', 'motherboard', 'memory', 'storage', 'psu', 'case', 'cooler'}

        # 对核心部件：先判断是否明显是“整机笔记本”
        if is_core_category:
            if current == 'memory' and any(k in name_text for k in ['内存', '内存条', 'ddr4', 'ddr5', 'sodimm']):
                pass
            elif any(k in name_text for k in _HIGH_CONFIDENCE_SWITCH['laptop']):
                return 'laptop'
            # 常见整机命名特征：型号 + 规格串（如 i7/16GB/1TB/RTX4060）
            if current != 'memory' and re.search(r'\d+gb\s*/\s*\d+tb', name_text) and any(k in name_text for k in ['rtx', 'hx', 'ultra', 'macbook', 'matebook', 'thinkbook', 'thinkpad']):
                return 'laptop'

        strong_hints = _CURRENT_STRONG_HINTS.get(current, [])
        if any(k in name_text for k in strong_hints):
            return current

        for target_key, kws in _HIGH_CONFIDENCE_SWITCH.items():
            if target_key == current:
                continue
            if target_key == 'laptop' and current in {'keyboard', 'mouse', 'headphone', 'speaker'}:
                continue
            if any(k in name_text for k in kws):
                return target_key

        return current

    # 显式别名优先
    for alias, key in CATEGORY_ALIAS_TO_KEY.items():
        if alias and alias in text:
            if key == 'laptop':
                return 'laptop'

    best_key = 'other'
    best_score = -10**9

    for key in CATEGORY_LABEL_MAP.keys():
        if key == 'other':
            continue
        score = _score_category(text, key)
        if key == current:
            score += 1  # 仅轻微偏置，不再盲目信任 current
        if score > best_score:
            best_score = score
            best_key = key

    # 分数过低，视为无法判定
    if best_score < 2:
        return current if current in CATEGORY_LABEL_MAP else 'other'

    return best_key


def infer_model(name):
    name = normalize_text(name)
    if not name:
        return ''
    parts = name.split(' ', 1)
    return parts[1] if len(parts) > 1 else name


def infer_brand(name, model=''):
    name = normalize_text(name)
    model = normalize_text(model)
    if not name:
        return ''

    token = name.split(' ', 1)[0]
    m = re.match(r'^([A-Za-z][A-Za-z0-9_-]*|[\u4e00-\u9fffA-Za-z]+)', token)
    candidate = m.group(1) if m else token

    m2 = re.match(r'^([\u4e00-\u9fff]{2,6})[A-Za-z0-9].*', candidate)
    if m2:
        candidate = m2.group(1)

    if model and candidate and candidate == model:
        parts = name.split(' ', 1)
        if len(parts) > 1:
            candidate = parts[0]

    return candidate[:100]
