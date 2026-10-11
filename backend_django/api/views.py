import os
import json
import re
from urllib.parse import urlparse
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.db import connection, transaction
from datetime import timedelta, datetime
from .models import (
    Post,
    Comment,
    Profile,
    ApiConfig,
    AuditApiConfig,
    PromptConfig,
    ChatSession,
    ChatMessage,
    PostImage,
    PostAttachment,
    CommentImage,
    CommentAttachment,
    LikeNotification,
    ReplyNotification,
    SystemNotification,
    RecommendedScheme,
    HardwareWeightAdjustmentLog,
)
from django.forms.models import model_to_dict
from django.contrib.auth import authenticate, login, logout, get_user_model, update_session_auth_hash
from django.contrib.auth.models import User
from .hardware_cleaner import (
    CATEGORY_LABEL_MAP as CLEANER_CATEGORY_LABEL_MAP,
    infer_category_key as cleaner_infer_category_key,
)
from .llm_client import invoke_with_config, normalize_chat_completions_url

try:
    # reuse existing scraper implementation in src/scraper.py
    from src.scraper import scrape_urls
except Exception:
    scrape_urls = None


# 推荐链路网络参数（可用环境变量覆盖）
API_REQUEST_TIMEOUT_SECONDS = int(os.getenv('API_REQUEST_TIMEOUT_SECONDS', '65'))
API_RETRY_ON_TRANSIENT = int(os.getenv('API_RETRY_ON_TRANSIENT', '1'))
API_RETRY_BACKOFF_SECONDS = float(os.getenv('API_RETRY_BACKOFF_SECONDS', '0.6'))
try:
    RAG_SIMILARITY_THRESHOLD = float(os.getenv('RAG_SIMILARITY_THRESHOLD', '0.35'))
except Exception:
    RAG_SIMILARITY_THRESHOLD = 0.35
RAG_SIMILARITY_THRESHOLD = min(max(RAG_SIMILARITY_THRESHOLD, 0.0), 1.0)


def health(request):
    return JsonResponse({'status': 'ok'})


AI_HIDDEN_POST_TEXT = '此动态涉及敏感信息，等待管理员核实'
AI_HIDDEN_COMMENT_TEXT = '此评论涉及敏感信息，等待管理员核实'


def _is_ai_hidden(obj):
    return getattr(obj, 'ai_moderation_status', '') == 'flagged'


DEFAULT_RECOMMEND_PROMPT_TEMPLATE = """你是一个专业的电脑配置推荐专家。无论用户提什么问题，请【优先基于以下本地最新的硬件知识库】为用户推荐或解答：
<本地最新硬件知识库>
{{knowledge_str}}
</本地最新硬件知识库>

【核心要求（预算第一）】：
0. 【形态二选一（强制）】：每次回答只能输出一种方案形态：
    - A) 台式机整机方案（按配件列清单并合计）；或
    - B) 笔记本整机方案（只推荐笔记本整机型号，不得拆成CPU/主板/机箱等台式机配件）。
1. 【绝对控制预算】：认真识别并计算推荐的所有硬件（知识库或你的预估价）总价，保证推荐总金额不能超过用户预算上限。
2. 【提供精准总价】：在配置单末尾，必须准确计算配置单总价，并展示距离预算的差额。
3. 【整机/配件一致性】：笔记本/整机不可拆件重复计价；台式机按配件分别列出并合计。
4. 【品牌约束】：用户要求纯品牌时，只能推荐该品牌；若无法完整满足，明确给出“严格纯品牌整机方案”和“放宽品牌装机方案”。
5. 【严禁错误】：严禁重复计价、严禁同一硬件重复出现在多个位置、严禁虚构不存在配件。
6. 【审核反馈修正】：收到“审核未通过原因”时，必须按原因修正并输出完整结果。
7. 【兼容性强校验（内部完成即可，不必单独输出段落）】：
    - 主板与 CPU 插槽必须完全匹配（如 AM5/LGA1700）；
    - 电源额定功率需满足整机峰值功耗并预留至少 20% 裕量；
    - 机箱尺寸需兼容主板板型（ATX/MATX/ITX）与显卡长度；
    - 散热器需满足平台类型并且散热器高度不超过机箱限高；
    - 内存代际与主板一致（DDR4/DDR5），并检查频率支持范围。
8. 【价格核算格式（必须严格执行）】：
    - 先输出“价格明细（仅数值）”，每个部件一行；
    - 然后输出“总计：¥X”；
    - 总计必须等于上述明细逐项求和，禁止出现数学不一致。
"""


DEFAULT_AUDIT_PROMPT_TEMPLATE = """你是电脑配置推荐内容审核员。请仅输出 JSON，不要输出任何额外文字。
请审查“待审核回答”是否存在预算超标、价格合计错误、与用户需求不匹配、关键部件缺失、逻辑矛盾。
重点检查：
1) 笔记本/整机被错误拆成CPU内存硬盘等重复计价；
2) 同一硬件被重复计价；
3) 用户要求纯品牌但回答中混入其他品牌或虚构该品牌不存在配件。
4) 兼容性错误：主板与CPU插槽不匹配、电源功率不足、机箱尺寸不兼容显卡或主板、散热器限高超出机箱上限、内存代际不匹配；
5) 总价错误：明细价格之和与“总计”不一致。
通过返回：{"passed": true, "reason": "..."}
不通过返回：{"passed": false, "reason": "..."}
"""


MANDATORY_RECOMMEND_GUARD = """
【强制校验规则（系统追加，不可忽略）】
A. 先判定方案形态（必须二选一，不得混搭）：
    1) 若用户明确提到“笔记本/轻薄本/游戏本/便携/出差”等移动办公诉求，输出【笔记本整机方案】；
    2) 其他场景默认输出【台式机整机方案】；
    3) 严禁在“笔记本整机方案”中出现主板/机箱/电源/散热器等台式机配件分项。
A1. 笔记本整机方案输出要求：
    1) 必须输出“完整配置清单（Markdown表格）”，列为：项目 | 具体型号 | 单价；
    2) 项目至少包含：整机型号、CPU、内存、硬盘、显卡（可写集成显卡）、屏幕、重量/续航（可合并）；
    3) 不得出现台式机分体配件项（如主板/机箱/电源/散热器）。
A2. 台式机整机方案输出要求：
    1) 必须输出“完整配置清单（Markdown表格）”，列为：部件 | 具体型号 | 单价；
    2) CPU/主板/显卡/内存/硬盘/电源/机箱/散热器为必填项；
    3) 若用户要求外设（显示器/键盘/鼠标/音箱等），必须单独列出具体型号与单价。

B. 禁止只给价格不给型号，若缺型号视为不合格答案。
C. 兼容性必须逐项自检（可内部完成，不要求单独成段输出；仅对台式机强制）：
    1) CPU 插槽 = 主板插槽；
    2) 电源功率 >= 整机峰值功耗 × 1.2；
    3) 机箱支持主板板型且显卡长度 <= 机箱限长；
    4) 散热器高度 <= 机箱散热限高，且散热器平台兼容 CPU；
    5) 内存代际/频率需被主板支持。
D. 价格计算必须一致：
    1) 仅统计实际列出的硬件项；
    2) 输出“总计：¥X”前自行复算一次；
    3) 若复算不一致，必须改正后再输出。
E. 固定输出顺序（不得缺段）：
   1) 完整配置清单（Markdown表格）
   2) 价格明细（仅数值）
   3) 总计：¥X
    4) （可选）简要说明（非必需）
""".strip()


MANDATORY_AUDIT_GUARD = """
【强制审核规则（系统追加，不可忽略）】
若发现以下任一问题，必须判定 passed=false：
1) 总价与明细逐项求和不一致；
2) 笔记本方案中出现台式机分体配件（主板/机箱/电源/散热器）或与台式机配件混搭；
3) 台式机方案缺少 CPU/主板/显卡/内存/硬盘/电源/机箱/散热器任一关键部件；
4) 台式机兼容性错误：CPU 与主板插槽不匹配、电源功率不足、机箱与主板/显卡不兼容、散热器限高或平台不兼容、内存代际不匹配；
5) 缺少“完整配置清单（项目或部件|具体型号|单价）”或关键信息缺失；
6) 仅给价格而无具体型号（如“显卡：42999”）。
""".strip()


REQUIREMENT_PARSE_PROMPT_TEMPLATE = """
你是电脑硬件需求分析助手。请把用户自然语言需求解析为结构化 JSON，仅输出 JSON。
JSON字段：
- demand_summary: 字符串，简明需求摘要（预算/用途/偏好）
- budget_min: 数字或 null
- budget_max: 数字或 null
- form_factor: "desktop" | "laptop" | "either"
- brand_preference: 字符串数组
- usage_scenarios: 字符串数组
- category_focus: 字符串数组（从以下键中选择：cpu,gpu,motherboard,memory,storage,psu,case,cooler,laptop,monitor,keyboard,mouse,headphone,speaker）
- search_text_by_category: 对象，键为上述类别，值为该类别的检索语句（中文短句）
要求：
1) 若无法确定字段，填 null 或空数组；
2) 不要输出解释文字，不要 markdown；
3) search_text_by_category 尽量覆盖用户重点提及类别。
""".strip()


RECOMMEND_REPAIR_PROMPT_TEMPLATE = """
审核系统未通过，请你严格按失败原因修复并重生成最终答案。
必须满足：
1) 输出完整配置清单（含具体型号和单价）；
2) 价格明细与总计严格一致；
3) 满足用户预算、品牌和用途；
4) 保持方案形态单一（台式机整机 / 笔记本整机二选一）。
""".strip()


def _infer_machine_mode(user_message='', reply_text=''):
    """推断推荐形态：laptop / desktop。优先用户需求，其次回答内容。"""
    user_txt = str(user_message or '')
    reply_txt = str(reply_text or '')

    laptop_keywords = ['笔记本', '轻薄本', '游戏本', '便携', '出差', '移动办公', '随身']
    desktop_keywords = ['台式', '主机', '装机', 'DIY', '组装机', '台式机']

    if any(k in user_txt for k in laptop_keywords):
        return 'laptop'
    if any(k in user_txt for k in desktop_keywords):
        return 'desktop'

    # 用户未明确时，按回答内容反推
    if any(k in reply_txt for k in ['主板', '机箱', '电源', '散热器']):
        return 'desktop'
    if any(k in reply_txt for k in laptop_keywords):
        return 'laptop'

    # 默认台式机
    return 'desktop'


def _check_output_structure_consistency(reply_text, user_message=''):
    """校验推荐结果是否包含完整配置清单与关键部件型号。返回 (ok, reason)。"""
    text = str(reply_text or '')
    if not text.strip():
        return False, '输出为空，缺少完整配置清单'

    # 结构段落检查
    if ('完整配置清单' not in text) and ('配置清单' not in text):
        return False, '缺少“完整配置清单”段落'

    mode = _infer_machine_mode(user_message=user_message, reply_text=text)

    required_parts = ['CPU', '主板', '显卡', '内存', '硬盘', '电源', '机箱', '散热']
    extra_parts = []
    user_msg = str(user_message or '')
    for p in ['显示器', '键盘', '鼠标', '音箱']:
        if p in user_msg:
            extra_parts.append(p)

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    def _validate_line_has_model(part_name):
        hit_line = None
        for ln in lines:
            if part_name in ln and all(k not in ln for k in ['总计', '合计', '总价', '兼容性']):
                hit_line = ln
                break
        if not hit_line:
            return False, f'缺少关键部件：{part_name}'

        rhs = hit_line
        if '：' in hit_line:
            rhs = hit_line.split('：', 1)[1].strip()
        elif ':' in hit_line:
            rhs = hit_line.split(':', 1)[1].strip()

        rhs_slim = re.sub(r'[¥￥元,，\s\.|\-_/()（）]+', '', rhs)
        if rhs_slim and re.fullmatch(r'\d+', rhs_slim):
            return False, f'{part_name} 缺少具体型号，仅给出价格'
        return True, ''

    if mode == 'laptop':
        # 笔记本方案必须是“整机”表达，不能混入台式机分体配件
        desktop_parts = ['主板', '机箱', '电源', '散热器']
        found_desktop_parts = [p for p in desktop_parts if any(p in ln for ln in lines)]
        if found_desktop_parts:
            return False, '笔记本方案中出现台式机分体配件，请改为整机笔记本方案'

        laptop_anchor_keywords = ['整机', '笔记本', '型号']
        if not any(any(k in ln for k in laptop_anchor_keywords) for ln in lines):
            return False, '笔记本方案缺少整机型号信息'

        # 笔记本至少应覆盖这些项目（可写集成显卡）
        for part in ['CPU', '内存', '硬盘', '显卡']:
            ok, reason = _validate_line_has_model(part)
            if not ok:
                return False, reason
    else:
        all_parts = required_parts + extra_parts
        for part in all_parts:
            ok, reason = _validate_line_has_model(part)
            if not ok:
                return False, reason

    return True, ''


def _get_or_create_prompt_config():
    has_topk_column = _prompt_config_has_topk_column()
    qs = PromptConfig.objects.order_by('-updated_at', '-id')
    if not has_topk_column:
        # 兼容数据库尚未执行新增字段迁移：避免 SELECT 不存在列导致 500
        qs = qs.defer('rag_top_k_per_category')

    cfg = qs.first()
    if cfg:
        changed = False
        if not (cfg.recommend_prompt or '').strip():
            cfg.recommend_prompt = DEFAULT_RECOMMEND_PROMPT_TEMPLATE
            changed = True
        if not (cfg.audit_prompt or '').strip():
            cfg.audit_prompt = DEFAULT_AUDIT_PROMPT_TEMPLATE
            changed = True
        if has_topk_column:
            try:
                topk_val = int(getattr(cfg, 'rag_top_k_per_category', 5) or 5)
            except Exception:
                topk_val = 5
            if topk_val < 1 or topk_val > 20:
                cfg.rag_top_k_per_category = min(max(topk_val, 1), 20)
                changed = True
        if changed:
            update_fields = ['recommend_prompt', 'audit_prompt', 'updated_at']
            if has_topk_column:
                update_fields.append('rag_top_k_per_category')
            cfg.save(update_fields=update_fields)
        return cfg

    create_kwargs = {
        'recommend_prompt': DEFAULT_RECOMMEND_PROMPT_TEMPLATE,
        'audit_prompt': DEFAULT_AUDIT_PROMPT_TEMPLATE,
    }
    if has_topk_column:
        create_kwargs['rag_top_k_per_category'] = 5
    return PromptConfig.objects.create(**create_kwargs)


def _prompt_config_has_topk_column():
    """检测 prompt_config 表是否已包含 rag_top_k_per_category 列。"""
    try:
        table_name = PromptConfig._meta.db_table
        with connection.cursor() as cursor:
            cols = connection.introspection.get_table_description(cursor, table_name)
        col_names = {getattr(c, 'name', '') for c in cols}
        return 'rag_top_k_per_category' in col_names
    except Exception:
        return False


def _get_rag_top_k_per_category():
    if not _prompt_config_has_topk_column():
        return 5
    cfg = _get_or_create_prompt_config()
    try:
        topk = int(getattr(cfg, 'rag_top_k_per_category', 5) or 5)
    except Exception:
        topk = 5
    return min(max(topk, 1), 20)


def _build_recommend_prompt(knowledge_str):
    cfg = _get_or_create_prompt_config()
    template = (cfg.recommend_prompt or DEFAULT_RECOMMEND_PROMPT_TEMPLATE).strip()
    if '{{knowledge_str}}' in template:
        rendered = template.replace('{{knowledge_str}}', str(knowledge_str or ''))
        return f"{rendered}\n\n{MANDATORY_RECOMMEND_GUARD}"
    if '{knowledge_str}' in template:
        rendered = template.replace('{knowledge_str}', str(knowledge_str or ''))
        return f"{rendered}\n\n{MANDATORY_RECOMMEND_GUARD}"
    return f"{template}\n\n<本地最新硬件知识库>\n{knowledge_str}\n</本地最新硬件知识库>\n\n{MANDATORY_RECOMMEND_GUARD}"


def _build_audit_prompt():
    cfg = _get_or_create_prompt_config()
    template = (cfg.audit_prompt or DEFAULT_AUDIT_PROMPT_TEMPLATE).strip()
    return f"{template}\n\n{MANDATORY_AUDIT_GUARD}"


def _extract_price_value(text):
    """从价格文本中提取整数金额（元），如 ¥12,999 / 12999 元。"""
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None

    # 1) 优先提取带货币符号/单位的金额（避免把 i9-14900K 里的数字当价格）
    currency_matches = re.findall(r'[¥￥]\s*([0-9][0-9,，]*)', s)
    if currency_matches:
        try:
            return int(currency_matches[-1].replace(',', '').replace('，', ''))
        except Exception:
            pass

    yuan_matches = re.findall(r'([0-9][0-9,，]*)\s*元', s)
    if yuan_matches:
        try:
            return int(yuan_matches[-1].replace(',', '').replace('，', ''))
        except Exception:
            pass

    # 2) 再尝试取冒号后半段中的数值（价格通常在这一段）
    tail = s
    if '：' in s:
        tail = s.rsplit('：', 1)[-1]
    elif ':' in s:
        tail = s.rsplit(':', 1)[-1]

    nums_in_tail = re.findall(r'([0-9][0-9,，]*)', tail)
    if nums_in_tail:
        try:
            return int(nums_in_tail[-1].replace(',', '').replace('，', ''))
        except Exception:
            pass

    # 3) 最后兜底取整行最后一个数字
    nums = re.findall(r'([0-9][0-9,，]*)', s)
    if nums:
        try:
            return int(nums[-1].replace(',', '').replace('，', ''))
        except Exception:
            return None
    return None


def _check_price_total_consistency(reply_text):
    """检测回答中的价格明细与总计是否一致。返回 (ok, reason)。"""
    text = str(reply_text or '')
    if not text.strip():
        return True, ''

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    item_sum = 0
    item_count = 0
    positive_price_count = 0
    total_value = None

    # 先找总计行
    total_idx = -1
    for i, ln in enumerate(lines):
        if any(k in ln for k in ['总计', '合计', '总价']):
            v = _extract_price_value(ln)
            if v is not None:
                total_value = v
                total_idx = i
                break

    # 优先使用“价格明细”区块，避免把兼容性说明中的数字误计入
    detail_start = -1
    for i, ln in enumerate(lines):
        if '价格明细' in ln:
            detail_start = i
            break

    if detail_start >= 0:
        candidate_lines = lines[detail_start + 1: total_idx if total_idx > detail_start else len(lines)]
    else:
        candidate_lines = lines[:total_idx] if total_idx > 0 else lines

    for ln in candidate_lines:
        # 只统计“部件: 价格”格式，尽量避开“预算/差额”等说明行
        if any(k in ln for k in ['总计', '合计', '总价', '预算', '差额', '节省', '余量', '剩余']):
            continue

        # Markdown 表头/分隔符跳过
        compact = ln.replace('|', '').replace('-', '').replace(':', '').replace('：', '').strip().lower()
        if compact in ('', '配件类型具体型号单价', '配件型号价格', '部件具体型号单价'):
            continue

        # 明细行判定：冒号格式、表格格式、或含货币单位
        if ('：' in ln) or (':' in ln) or ('|' in ln) or ('¥' in ln) or ('￥' in ln) or ('元' in ln):
            v = _extract_price_value(ln)
            if v is not None and v >= 0:
                item_sum += v
                item_count += 1
                if v > 0:
                    positive_price_count += 1

    # 没提取到有效价格明细或总计，视为无法校验，不拦截
    if item_count == 0 or total_value is None:
        return True, ''

    # 提取到的明细若全部为 0，通常属于无效/不可解析输出，避免误判为数学错误
    if positive_price_count == 0:
        return True, ''

    if item_sum != total_value:
        return False, f'价格合计错误：明细求和为 {item_sum} 元，但总计写为 {total_value} 元。'
    return True, ''


def _extract_json_from_text(text):
    if not text:
        return None
    text = str(text).strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    m = re.search(r'\{[\s\S]*\}', text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _call_chat_api(config, messages, temperature=0.7, timeout=40, max_tokens=None):
    """统一通过 LangChain 调用大模型，返回 (ok, content_or_error)。"""
    import time

    attempts = 1 + max(0, int(API_RETRY_ON_TRANSIENT))
    last_error = ''

    for attempt in range(attempts):
        try:
            ok, content_or_error = invoke_with_config(
                config=config,
                messages=messages,
                temperature=temperature,
                timeout=timeout,
                max_tokens=max_tokens,
            )
            if ok:
                content = content_or_error
                return True, content

            last_error = str(content_or_error)
            lower_err = last_error.lower()
            # LangChain 侧无法稳定拿到状态码，这里按常见瞬时错误关键字重试
            is_transient_http = (
                ('429' in lower_err)
                or ('timeout' in lower_err)
                or ('timed out' in lower_err)
                or ('connection' in lower_err)
                or ('503' in lower_err)
                or ('502' in lower_err)
                or ('500' in lower_err)
            )
            if is_transient_http and attempt < attempts - 1:
                time.sleep(API_RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue
            return False, last_error
        except Exception as e:
            return False, str(e)

    return False, last_error or 'unknown error'


def _normalize_chat_completions_url(base_url):
    return normalize_chat_completions_url(base_url)


def _test_chat_api(base_url, api_key, model_name, probe_text='hello', timeout=15):
    target_url = _normalize_chat_completions_url(base_url)
    if not target_url:
        return False, 'Base URL 不能为空'
    if not api_key:
        return False, 'API Key 不能为空'
    if not model_name:
        return False, '模型名称不能为空'

    class _TmpConfig:
        pass

    cfg = _TmpConfig()
    cfg.base_url = target_url
    cfg.api_key = api_key
    cfg.model_name = model_name

    ok, content_or_error = invoke_with_config(
        config=cfg,
        messages=[{'role': 'user', 'content': probe_text}],
        temperature=0,
        timeout=timeout,
        max_tokens=16,
    )
    if ok:
        return True, ''

    # 部分模型对 max_tokens 更严格，兜底再试一次
    ok2, content_or_error2 = invoke_with_config(
        config=cfg,
        messages=[{'role': 'user', 'content': probe_text}],
        temperature=0,
        timeout=timeout,
        max_tokens=None,
    )
    if ok2:
        return True, ''

    return False, f'{content_or_error2 or content_or_error} (URL: {target_url})'


def _coerce_audit_result(content):
    """尽量从审核模型文本中提取 passed/reason，兼容非严格JSON返回。"""
    parsed = _extract_json_from_text(content)
    if isinstance(parsed, dict):
        passed = parsed.get('passed', True)
        if isinstance(passed, str):
            p = passed.strip().lower()
            passed = p in ('true', '1', 'yes', '通过', 'pass')
        reason = str(parsed.get('reason', '') or '').strip()
        return bool(passed), reason

    txt = str(content or '').strip()
    if not txt:
        return None

    lower = txt.lower()
    # 英文/JSON碎片
    if '"passed": false' in lower or "'passed': false" in lower or 'passed=false' in lower:
        return False, ''
    if '"passed": true' in lower or "'passed': true" in lower or 'passed=true' in lower:
        return True, ''

    # 中文语义兜底
    if any(k in txt for k in ['审核不通过', '不通过', '未通过', '存在问题', '超预算', '逻辑矛盾']):
        return False, ''
    if any(k in txt for k in ['审核通过', '通过', '可行', '符合要求']):
        return True, ''

    return None


def _audit_generated_reply(user_message, generated_reply, knowledge_str):
    """Run audit check with primary + backup audit APIs, returning availability/pass/fail with reason."""

    configs = list(AuditApiConfig.objects.filter(is_active=True).order_by('-is_primary', 'id'))
    if not configs:
        return {'available': False, 'passed': None, 'used_api': None, 'reason': '未配置审核API', 'errors': []}

    prompt = _build_audit_prompt()

    # 审核阶段控制输入长度，避免深度推理模型因上下文过长超时
    user_message_short = str(user_message or '')[:800]
    knowledge_short = str(knowledge_str or '')[:1200]
    generated_reply_short = str(generated_reply or '')[:1800]

    audit_messages = [
        {'role': 'system', 'content': prompt},
        {'role': 'user', 'content': f"用户需求：\n{user_message_short}\n\n参考知识库摘要：\n{knowledge_short}\n\n待审核回答：\n{generated_reply_short}"},
    ]

    errors = []
    had_success_response = False
    for config in configs:
        ok, content_or_error = _call_chat_api(
            config,
            audit_messages,
            temperature=0.0,
            timeout=90,
            max_tokens=420,
        )
        try:
            if not ok:
                errors.append(f"[{config.name}] 审核请求失败: {content_or_error}")
                continue

            had_success_response = True

            coerced = _coerce_audit_result(content_or_error)
            if coerced is not None:
                passed, reason = coerced
                return {
                    'available': True,
                    'passed': bool(passed),
                    'used_api': config.name,
                    'reason': reason or ('审核通过' if passed else '审核未通过')
                }

            errors.append(f"[{config.name}] 审核返回不可解析内容")
        except Exception as e:
            errors.append(f"[{config.name}] 审核异常: {str(e)}")

    # 至少有一个审核API成功返回，但格式异常：改为“未通过”，触发推荐端重生成
    if had_success_response:
        return {
            'available': True,
            'passed': False,
            'used_api': None,
            'reason': '审核返回不可解析，已要求重生成'
        }

    return {'available': False, 'passed': None, 'used_api': None, 'reason': '审核系统不可用', 'errors': errors}


def _decorate_reply_with_audit_notice(reply, audit_meta):
    """将审核状态提示固化进回答正文，避免前端刷新后状态提示丢失。"""
    text = str(reply or '')
    meta = audit_meta or {}
    status = str(meta.get('status', '') or '').strip().lower()
    reason = str(meta.get('reason', '') or '').strip()

    notice = ''
    if status == 'unavailable':
        notice = '⚠ 审核系统不可用，无法保证准确性。'

    if not notice:
        return text

    # 避免重复追加同一提醒
    if notice in text:
        return text
    return f"{notice}\n\n{text}"


def _strip_audit_notice_prefix(text):
    """移除历史回答里固化的审核提示前缀，避免被下轮模型复读。"""
    s = str(text or '')
    prefixes = [
        '⚠ 审核系统不可用，无法保证准确性。',
        '⚠ 审核返回不可解析，已要求重生成。',
        '⚠ 审核接口返回格式异常，请按规则重新生成并输出完整配置清单（含具体型号）。',
    ]
    changed = True
    while changed:
        changed = False
        for p in prefixes:
            if s.startswith(p):
                s = s[len(p):].lstrip('\n').lstrip()
                changed = True
    return s


def _normalize_requirement_parse(parsed, user_message=''):
    """规范化需求解析结果，保证字段齐全可用。"""
    data = parsed if isinstance(parsed, dict) else {}
    out = {
        'demand_summary': _normalize_text(data.get('demand_summary') or user_message),
        'budget_min': data.get('budget_min'),
        'budget_max': data.get('budget_max'),
        'form_factor': _normalize_text(data.get('form_factor') or 'either').lower(),
        'brand_preference': data.get('brand_preference') if isinstance(data.get('brand_preference'), list) else [],
        'usage_scenarios': data.get('usage_scenarios') if isinstance(data.get('usage_scenarios'), list) else [],
        'category_focus': data.get('category_focus') if isinstance(data.get('category_focus'), list) else [],
        'search_text_by_category': data.get('search_text_by_category') if isinstance(data.get('search_text_by_category'), dict) else {},
    }
    if out['form_factor'] not in ('desktop', 'laptop', 'either'):
        out['form_factor'] = 'either'
    return out


def _parse_user_requirement_with_llm(user_message, configs):
    """调用推荐API先做需求解析，返回结构化需求。"""
    parse_messages = [
        {'role': 'system', 'content': REQUIREMENT_PARSE_PROMPT_TEMPLATE},
        {'role': 'user', 'content': str(user_message or '').strip()}
    ]

    errors = []
    for config in configs:
        ok, content_or_error = _call_chat_api(
            config=config,
            messages=parse_messages,
            temperature=0.1,
            timeout=min(API_REQUEST_TIMEOUT_SECONDS, 35),
            max_tokens=600,
        )
        if not ok:
            errors.append(f"[{config.name}] 需求解析失败: {content_or_error}")
            continue

        parsed = _extract_json_from_text(content_or_error)
        if isinstance(parsed, dict):
            return {
                'ok': True,
                'used_api': config.name,
                'parsed': _normalize_requirement_parse(parsed, user_message=user_message),
                'raw': str(content_or_error or '')[:1500],
                'errors': errors,
            }

        errors.append(f"[{config.name}] 需求解析返回非JSON")

    return {
        'ok': False,
        'used_api': None,
        'parsed': _normalize_requirement_parse({}, user_message=user_message),
        'raw': '',
        'errors': errors,
    }


def _cosine_similarity(v1, v2):
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = 0.0
    n1 = 0.0
    n2 = 0.0
    for a, b in zip(v1, v2):
        fa = float(a)
        fb = float(b)
        dot += fa * fb
        n1 += fa * fa
        n2 += fb * fb
    if n1 <= 0 or n2 <= 0:
        return 0.0
    return dot / ((n1 ** 0.5) * (n2 ** 0.5))


def _search_vectors_one_category(category_key, query_text, top_k=5, similarity_threshold=None):
    """在单一硬件类别向量库内做相似检索，返回[{hardware_id, score, ...}]。"""
    query_vec, emb_meta = _embed_text_with_bge(query_text)
    query_dim = len(query_vec) if isinstance(query_vec, list) and query_vec else 256
    threshold = RAG_SIMILARITY_THRESHOLD if similarity_threshold is None else float(similarity_threshold)
    threshold = min(max(threshold, 0.0), 1.0)

    # 1) 优先 Chroma collection: hardware_knowledge_{category}_{suffix}
    chroma_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'vector_store',
        'chroma_hardware'
    )
    col_name = _vector_collection_name(category_key, query_dim)
    try:
        import chromadb
        client = chromadb.PersistentClient(path=chroma_path)
        col = client.get_collection(name=col_name)
        result = col.query(
            query_embeddings=[query_vec],
            n_results=max(1, int(top_k)),
            include=['metadatas', 'documents', 'distances']
        )

        ids = result.get('ids', [[]])[0] if isinstance(result.get('ids', []), list) else []
        metadatas = result.get('metadatas', [[]])[0] if isinstance(result.get('metadatas', []), list) else []
        documents = result.get('documents', [[]])[0] if isinstance(result.get('documents', []), list) else []
        distances = result.get('distances', [[]])[0] if isinstance(result.get('distances', []), list) else []

        rows = []
        for i in range(min(len(ids), len(metadatas), len(documents), len(distances))):
            meta = metadatas[i] or {}
            hw_id = meta.get('hardware_id')
            try:
                hw_id = int(hw_id)
            except Exception:
                continue
            dist = float(distances[i]) if distances[i] is not None else 1.0
            score = 1.0 / (1.0 + max(0.0, dist))
            rows.append({
                'hardware_id': hw_id,
                'score': score,
                'document': str(documents[i] or ''),
                'metadata': {**meta, 'query_embedding_model': emb_meta.get('embedding_model', '')},
            })
        if rows:
            rows = [r for r in rows if float(r.get('score', 0.0)) >= threshold]
            rows.sort(key=lambda x: x.get('score', 0.0), reverse=True)
            return rows[:top_k]
    except Exception:
        # 兼容历史旧集合（deterministic）
        try:
            old_col_names = [
                f'hardware_knowledge_{category_key}_{BGE_COLLECTION_SUFFIX}',
                f'hardware_knowledge_{category_key}',
            ]
            import chromadb
            client = chromadb.PersistentClient(path=chroma_path)
            result = None
            for old_col_name in old_col_names:
                try:
                    col = client.get_collection(name=old_col_name)
                    result = col.query(
                        query_embeddings=[query_vec],
                        n_results=max(1, int(top_k)),
                        include=['metadatas', 'documents', 'distances']
                    )
                    break
                except Exception:
                    continue
            if result is None:
                raise RuntimeError('no old collection found')
            ids = result.get('ids', [[]])[0] if isinstance(result.get('ids', []), list) else []
            metadatas = result.get('metadatas', [[]])[0] if isinstance(result.get('metadatas', []), list) else []
            documents = result.get('documents', [[]])[0] if isinstance(result.get('documents', []), list) else []
            distances = result.get('distances', [[]])[0] if isinstance(result.get('distances', []), list) else []
            rows = []
            for i in range(min(len(ids), len(metadatas), len(documents), len(distances))):
                meta = metadatas[i] or {}
                hw_id = meta.get('hardware_id')
                try:
                    hw_id = int(hw_id)
                except Exception:
                    continue
                dist = float(distances[i]) if distances[i] is not None else 1.0
                score = 1.0 / (1.0 + max(0.0, dist))
                rows.append({
                    'hardware_id': hw_id,
                    'score': score,
                    'document': str(documents[i] or ''),
                    'metadata': {**meta, 'query_embedding_model': emb_meta.get('embedding_model', '')},
                })
            if rows:
                rows = [r for r in rows if float(r.get('score', 0.0)) >= threshold]
                rows.sort(key=lambda x: x.get('score', 0.0), reverse=True)
                return rows[:top_k]
        except Exception:
            pass

    # 2) SQLite 兜底: hardware_vectors_{category}_{suffix}
    try:
        import sqlite3
        sqlite_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'vector_store',
            'hardware_vectors.sqlite3'
        )
        if not os.path.exists(sqlite_path):
            return []

        table_name = _vector_table_name(category_key, query_dim)
        conn = sqlite3.connect(sqlite_path)
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,)
            )
            if not cursor.fetchone():
                # 兼容历史旧表
                fallback_tables = [
                    f'hardware_vectors_{category_key}_{BGE_COLLECTION_SUFFIX}',
                    f'hardware_vectors_{category_key}',
                ]
                found = False
                for tb in fallback_tables:
                    cursor = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                        (tb,)
                    )
                    if cursor.fetchone():
                        table_name = tb
                        found = True
                        break
                if not found:
                    return []

            cur = conn.execute(
                f"SELECT hardware_id, vector_json, document, metadata_json FROM {table_name}"
            )
            rows = []
            for hw_id, vec_json, doc, meta_json in cur.fetchall():
                try:
                    vec = json.loads(vec_json)
                    cosine = _cosine_similarity(query_vec, vec)
                    score = (cosine + 1.0) / 2.0
                    meta = json.loads(meta_json) if meta_json else {}
                    rows.append({
                        'hardware_id': int(hw_id),
                        'score': float(score),
                        'document': str(doc or ''),
                        'metadata': meta if isinstance(meta, dict) else {},
                    })
                except Exception:
                    continue

            rows = [r for r in rows if float(r.get('score', 0.0)) >= threshold]
            rows.sort(key=lambda x: x.get('score', 0.0), reverse=True)
            return rows[:top_k]
        finally:
            conn.close()
    except Exception:
        return []


def _retrieve_hardware_context_by_category_vectors(user_message, parsed_requirement, top_k_each=5):
    from .models import Hardware

    categories = [k for k, _ in Hardware.CATEGORY_CHOICES if k != 'other']
    search_text_map = parsed_requirement.get('search_text_by_category') or {}
    demand_summary = _normalize_text(parsed_requirement.get('demand_summary') or user_message)

    retrieved_hits = {}
    all_ids = []

    for c in categories:
        cat_query_text = _normalize_text(search_text_map.get(c) or f"{demand_summary} {user_message} {c}")
        hits = _search_vectors_one_category(c, cat_query_text, top_k=top_k_each)
        retrieved_hits[c] = hits
        for h in hits:
            hid = h.get('hardware_id')
            if isinstance(hid, int) and hid not in all_ids:
                all_ids.append(hid)

    hw_map = {h.id: h for h in Hardware.objects.filter(id__in=all_ids)}

    lines = []
    category_counts = {}
    for c in categories:
        hits = retrieved_hits.get(c, [])
        category_counts[c] = len(hits)
        if not hits:
            continue
        cat_label = _CATEGORY_LABEL_MAP.get(c, c)
        lines.append(f"\n### [{cat_label}] 候选硬件 Top {len(hits)}")
        for rank, item in enumerate(hits, start=1):
            hid = item.get('hardware_id')
            hw = hw_map.get(hid)
            if not hw:
                continue
            latest_price_obj = hw.pricehistory_set.order_by('-id').first()
            latest_price = latest_price_obj.price if latest_price_obj else '未知'
            lines.append(
                f"{rank}. ID={hw.id} | {hw.name} ({hw.model or 'N/A'}) | 品牌:{hw.brand or '未知'} | "
                f"价格:{latest_price}元 | 相似度:{round(float(item.get('score', 0.0)), 4)} | 参数:{_normalize_text(hw.description)[:140]}"
            )

    knowledge_str = '\n'.join(lines).strip()
    if not knowledge_str:
        fallback_hw = Hardware.objects.all().order_by('-recommend_weight', 'id')[:60]
        fallback_lines = []
        for hw in fallback_hw:
            latest_price_obj = hw.pricehistory_set.order_by('-id').first()
            latest_price = latest_price_obj.price if latest_price_obj else '未知'
            cat_label = _CATEGORY_LABEL_MAP.get(getattr(hw, 'category', 'other'), '其他')
            fallback_lines.append(
                f"[{cat_label}] ID={hw.id} | {hw.name} ({hw.model or 'N/A'}) | 品牌:{hw.brand or '未知'} | 价格:{latest_price}元 | 参数:{_normalize_text(hw.description)[:120]}"
            )
        knowledge_str = '\n'.join(fallback_lines)

    return {
        'knowledge_str': knowledge_str,
        'category_counts': category_counts,
        'similarity_threshold': RAG_SIMILARITY_THRESHOLD,
    }


@csrf_exempt
def recommend(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        data = {}

    user_message = data.get('message', '')
    session_id = data.get('session_id')
    is_retry = bool(data.get('retry', False))

    user = request.user if request.user.is_authenticated else None
    if not request.session.session_key:
        request.session.create()
    session_key = request.session.session_key

    chat_session = None
    if session_id:
        try:
            if user:
                chat_session = ChatSession.objects.get(id=session_id, user=user)
            else:
                chat_session = ChatSession.objects.get(id=session_id, session_key=session_key)
        except ChatSession.DoesNotExist:
            pass

    if not chat_session and user_message:
        title = user_message[:15] + "..." if len(user_message) > 15 else user_message
        if not title:
            title = "新对话"
        chat_session = ChatSession.objects.create(user=user, session_key=session_key, title=title)

    if chat_session and user_message:
        should_save_user_msg = True
        if is_retry:
            last_user_msg = chat_session.messages.filter(role='user').order_by('-created_at').first()
            if last_user_msg and str(last_user_msg.content or '').strip() == str(user_message or '').strip():
                should_save_user_msg = False
        if should_save_user_msg:
            ChatMessage.objects.create(session=chat_session, role='user', content=user_message)

    configs = list(ApiConfig.objects.filter(is_active=True).order_by('-is_primary', 'id'))
    if not configs:
        return JsonResponse({'error': '未配置可用的API，请联系管理员在论坛管理中设置'}, status=500)

    # 对话消息（不含 system），用于后续推荐生成
    history_messages = []
    if chat_session:
        for m in chat_session.messages.order_by('created_at'):
            content = m.content
            if m.role == 'assistant':
                content = _strip_audit_notice_prefix(content)
            history_messages.append({'role': m.role, 'content': content})
    elif user_message:
        history_messages.append({'role': 'user', 'content': user_message})

    def _chain_step_parse(state):
        parsed_pack = _parse_user_requirement_with_llm(state['user_message'], state['configs'])
        state['parsed_requirement'] = parsed_pack.get('parsed', {})
        state['parse_used_api'] = parsed_pack.get('used_api')
        state['parse_errors'] = parsed_pack.get('errors', [])
        return state

    def _chain_step_retrieve(state):
        topk = _get_rag_top_k_per_category()
        rag = _retrieve_hardware_context_by_category_vectors(
            user_message=state['user_message'],
            parsed_requirement=state.get('parsed_requirement') or {},
            top_k_each=topk,
        )
        state['knowledge_str'] = rag.get('knowledge_str', '')
        state['rag_category_counts'] = rag.get('category_counts', {})
        state['rag_top_k_per_category'] = topk
        state['rag_similarity_threshold'] = rag.get('similarity_threshold', RAG_SIMILARITY_THRESHOLD)
        return state

    def _chain_step_generate(state):
        parsed_req = state.get('parsed_requirement') or {}
        parsed_text = json.dumps(parsed_req, ensure_ascii=False)

        system_prompt = _build_recommend_prompt(state.get('knowledge_str', ''))
        api_messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'system', 'content': f'以下是用户需求结构化解析结果（请严格遵循）：\n{parsed_text}'}
        ]
        api_messages.extend(state.get('history_messages') or [])

        errors = []
        for config in state['configs']:
            ok, content_or_error = _call_chat_api(
                config,
                api_messages,
                temperature=0.6,
                timeout=API_REQUEST_TIMEOUT_SECONDS,
            )
            if ok:
                state['reply'] = content_or_error
                state['used_api'] = config.name
                state['api_messages_for_retry'] = api_messages
                state['generation_errors'] = errors
                return state
            errors.append(f"[{config.name}] 生成失败: {content_or_error}")

        state['reply'] = ''
        state['used_api'] = None
        state['generation_errors'] = errors
        return state

    def _chain_step_audit(state):
        reply = str(state.get('reply') or '')
        if not reply.strip():
            state['audit_passed'] = False
            state['audit_meta'] = {
                'status': 'failed',
                'used_api': None,
                'reason': '推荐生成失败，未得到有效回复',
            }
            return state

        user_msg = state.get('user_message', '')
        knowledge_str = state.get('knowledge_str', '')

        struct_ok, struct_reason = _check_output_structure_consistency(reply, user_message=user_msg)
        if not struct_ok:
            audit1 = {'available': True, 'passed': False, 'used_api': None, 'reason': struct_reason}
        else:
            calc_ok, calc_reason = _check_price_total_consistency(reply)
            if calc_ok:
                audit1 = _audit_generated_reply(user_message=user_msg, generated_reply=reply, knowledge_str=knowledge_str)
            else:
                audit1 = {'available': True, 'passed': False, 'used_api': None, 'reason': calc_reason}

        if audit1.get('passed') is True:
            state['audit_passed'] = True
            state['audit_meta'] = {
                'status': 'passed',
                'used_api': audit1.get('used_api'),
                'reason': audit1.get('reason', '审核通过')
            }
            state['final_reply'] = reply
            return state

        # 审核未过时，按原因进行一次链内修复重生成
        fail_reason = audit1.get('reason', '未提供')
        retry_messages = list(state.get('api_messages_for_retry') or [])
        retry_messages.append({
            'role': 'system',
            'content': (
                f"{RECOMMEND_REPAIR_PROMPT_TEMPLATE}\n"
                f"原始问题：{user_msg}\n"
                f"未通过原因：{fail_reason}\n"
                f"待修复答案：\n{reply[:1800]}"
            )
        })

        retry_reply = ''
        retry_used_api = None
        retry_errors = []
        for config in state['configs']:
            ok_retry, retry_or_err = _call_chat_api(
                config,
                retry_messages,
                temperature=0.45,
                timeout=API_REQUEST_TIMEOUT_SECONDS,
            )
            if ok_retry:
                retry_reply = retry_or_err
                retry_used_api = config.name
                break
            retry_errors.append(f"[{config.name}] 修复重生成失败: {retry_or_err}")

        if not retry_reply:
            state['audit_passed'] = False
            state['audit_meta'] = {
                'status': 'failed',
                'used_api': audit1.get('used_api'),
                'reason': f"审核未通过且修复生成失败：{fail_reason}",
                'errors': retry_errors,
            }
            return state

        retry_struct_ok, retry_struct_reason = _check_output_structure_consistency(retry_reply, user_message=user_msg)
        if not retry_struct_ok:
            audit2 = {'available': True, 'passed': False, 'used_api': None, 'reason': retry_struct_reason}
        else:
            retry_calc_ok, retry_calc_reason = _check_price_total_consistency(retry_reply)
            if retry_calc_ok:
                audit2 = _audit_generated_reply(user_message=user_msg, generated_reply=retry_reply, knowledge_str=knowledge_str)
            else:
                audit2 = {'available': True, 'passed': False, 'used_api': None, 'reason': retry_calc_reason}

        if audit2.get('passed') is True:
            state['audit_passed'] = True
            state['audit_meta'] = {
                'status': 'regenerated_passed',
                'used_api': audit2.get('used_api'),
                'reason': audit2.get('reason', '审核通过'),
                'regenerated': True,
                'first_fail_reason': fail_reason,
                'retry_used_api': retry_used_api,
            }
            state['final_reply'] = retry_reply
            return state

        state['audit_passed'] = False
        state['audit_meta'] = {
            'status': 'failed',
            'used_api': audit2.get('used_api'),
            'reason': f"修复后仍未通过审核：{audit2.get('reason', '未知原因')}",
            'regenerated': True,
            'first_fail_reason': fail_reason,
            'retry_used_api': retry_used_api,
        }
        return state

    initial_state = {
        'user_message': user_message,
        'history_messages': history_messages,
        'configs': configs,
    }

    try:
        from langchain_core.runnables import RunnableLambda
        chain = RunnableLambda(_chain_step_parse) | RunnableLambda(_chain_step_retrieve) | RunnableLambda(_chain_step_generate) | RunnableLambda(_chain_step_audit)
        final_state = chain.invoke(initial_state)
    except Exception:
        # 兜底：即使 LangChain 运行时异常，也串行执行同一链路
        final_state = _chain_step_audit(_chain_step_generate(_chain_step_retrieve(_chain_step_parse(initial_state))))

    if final_state.get('audit_passed'):
        audit_meta = final_state.get('audit_meta') or {}
        display_reply = _decorate_reply_with_audit_notice(final_state.get('final_reply', ''), audit_meta)
        if chat_session:
            ChatMessage.objects.create(session=chat_session, role='assistant', content=display_reply)
            return JsonResponse({
                'status': 'ok',
                'reply': display_reply,
                'used_api': final_state.get('used_api'),
                'audit': audit_meta,
                'rag': {
                    'parse_used_api': final_state.get('parse_used_api'),
                    'top_k_per_category': final_state.get('rag_top_k_per_category'),
                    'similarity_threshold': final_state.get('rag_similarity_threshold'),
                    'category_counts': final_state.get('rag_category_counts', {}),
                },
                'session_id': chat_session.id,
                'session_title': chat_session.title,
            })
        return JsonResponse({
            'status': 'ok',
            'reply': display_reply,
            'used_api': final_state.get('used_api'),
            'audit': audit_meta,
            'rag': {
                'parse_used_api': final_state.get('parse_used_api'),
                'top_k_per_category': final_state.get('rag_top_k_per_category'),
                'similarity_threshold': final_state.get('rag_similarity_threshold'),
                'category_counts': final_state.get('rag_category_counts', {}),
            },
        })

    err_details = []
    err_details.extend(final_state.get('parse_errors') or [])
    err_details.extend(final_state.get('generation_errors') or [])
    err_details.extend((final_state.get('audit_meta') or {}).get('errors', []) if isinstance(final_state.get('audit_meta'), dict) else [])

    return JsonResponse({
        'error': '未能生成通过审核的推荐结果',
        'reason': (final_state.get('audit_meta') or {}).get('reason', '未知原因') if isinstance(final_state.get('audit_meta'), dict) else '未知原因',
        'details': err_details[:8],
        'rag': {
            'parse_used_api': final_state.get('parse_used_api'),
            'top_k_per_category': final_state.get('rag_top_k_per_category'),
            'similarity_threshold': final_state.get('rag_similarity_threshold'),
            'category_counts': final_state.get('rag_category_counts', {}),
        }
    }, status=500)


@csrf_exempt
def chat_sessions_view(request):
    if not request.session.session_key:
        request.session.create()
    session_key = request.session.session_key
    user = request.user if request.user.is_authenticated else None

    if request.method == 'GET':
        if user:
            qs = ChatSession.objects.filter(user=user).order_by('-updated_at')
        else:
            qs = ChatSession.objects.filter(session_key=session_key, user__isnull=True).order_by('-updated_at')
        return JsonResponse({'sessions': [s.to_dict() for s in qs]})
        
    elif request.method == 'DELETE':
        try:
            data = json.loads(request.body)
            sid = data.get('id')
            if user:
                ChatSession.objects.filter(id=sid, user=user).delete()
            else:
                ChatSession.objects.filter(id=sid, session_key=session_key).delete()
            return JsonResponse({'status': 'ok'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
            
    return JsonResponse({'error': 'GET or DELETE required'}, status=405)

@csrf_exempt
def chat_history_view(request, session_id):
    user = request.user if request.user.is_authenticated else None
    session_key = request.session.session_key
    try:
        if user:
            session = ChatSession.objects.get(id=session_id, user=user)
        else:
            session = ChatSession.objects.get(id=session_id, session_key=session_key)
        messages = session.messages.order_by('created_at')
        return JsonResponse({'messages': [m.to_dict() for m in messages]})
    except ChatSession.DoesNotExist:
        return JsonResponse({'error': '未找到该对话'}, status=404)

@csrf_exempt
def api_configs_view(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({'error': 'admin required'}, status=401)
        
    if request.method == 'GET':
        configs = list(ApiConfig.objects.all().values())
        return JsonResponse({'configs': configs})
        
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
        except Exception:
            data = {}
        action = data.get('action')
        
        if action == 'add':
            is_primary = data.get('is_primary', False)
            if is_primary:
                ApiConfig.objects.filter(is_primary=True).update(is_primary=False)
            ApiConfig.objects.create(
                name=data.get('name', 'New API'),
                api_key=data.get('api_key', ''),
                model_name=data.get('model_name', ''),
                base_url=data.get('base_url', 'https://api.siliconflow.cn/v1/chat/completions'),
                is_primary=is_primary,
                is_active=data.get('is_active', True)
            )
        elif action == 'edit':
            config_id = data.get('id')
            c = ApiConfig.objects.get(id=config_id)
            is_primary = data.get('is_primary', c.is_primary)
            if is_primary and not c.is_primary:
                ApiConfig.objects.filter(is_primary=True).update(is_primary=False)
            c.name = data.get('name', c.name)
            c.api_key = data.get('api_key', c.api_key)
            c.model_name = data.get('model_name', c.model_name)
            c.base_url = data.get('base_url', c.base_url)
            c.is_primary = is_primary
            c.is_active = data.get('is_active', c.is_active)
            c.save()
        elif action == 'delete':
            config_id = data.get('id')
            ApiConfig.objects.filter(id=config_id).delete()
        elif action == 'test':
            import time
            api_key = data.get('api_key', '')
            model_name = data.get('model_name', '')
            base_url = data.get('base_url', '')
            start_time = time.time()
            ok, err = _test_chat_api(base_url=base_url, api_key=api_key, model_name=model_name, probe_text='hello', timeout=15)
            latency = int((time.time() - start_time) * 1000)
            if ok:
                return JsonResponse({'status': 'ok', 'latency': latency})
            return JsonResponse({'error': err}, status=400)
            
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'error': 'POST or GET required'}, status=405)


@csrf_exempt
def prompt_configs_view(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({'error': 'admin required'}, status=401)

    if request.method == 'GET':
        cfg = _get_or_create_prompt_config()
        has_topk_column = _prompt_config_has_topk_column()
        topk_val = 5
        if has_topk_column:
            try:
                topk_val = int(getattr(cfg, 'rag_top_k_per_category', 5) or 5)
            except Exception:
                topk_val = 5
        topk_val = min(max(topk_val, 1), 20)
        return JsonResponse({
            'status': 'ok',
            'data': {
                'id': cfg.id,
                'recommend_prompt': cfg.recommend_prompt,
                'audit_prompt': cfg.audit_prompt,
                'rag_top_k_per_category': topk_val,
                'updated_at': cfg.updated_at.strftime('%Y-%m-%d %H:%M:%S') if cfg.updated_at else '',
            },
            'defaults': {
                'recommend_prompt': DEFAULT_RECOMMEND_PROMPT_TEMPLATE,
                'audit_prompt': DEFAULT_AUDIT_PROMPT_TEMPLATE,
                'rag_top_k_per_category': 5,
            },
            'placeholders': {
                'recommend_prompt': ['{{knowledge_str}}'],
                'audit_prompt': []
            }
        })

    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8') or '{}')
        except Exception:
            data = {}

        action = (data.get('action') or 'save').strip().lower()
        cfg = _get_or_create_prompt_config()
        has_topk_column = _prompt_config_has_topk_column()

        if action == 'reset':
            cfg.recommend_prompt = DEFAULT_RECOMMEND_PROMPT_TEMPLATE
            cfg.audit_prompt = DEFAULT_AUDIT_PROMPT_TEMPLATE
            update_fields = ['recommend_prompt', 'audit_prompt', 'updated_at']
            if has_topk_column:
                cfg.rag_top_k_per_category = 5
                update_fields.append('rag_top_k_per_category')
            cfg.save(update_fields=update_fields)
            return JsonResponse({'status': 'ok', 'message': '提示词已重置为默认值'})

        recommend_prompt = str(data.get('recommend_prompt', '') or '').strip()
        audit_prompt = str(data.get('audit_prompt', '') or '').strip()
        if not recommend_prompt:
            return JsonResponse({'error': '推荐系统提示词不能为空'}, status=400)
        if not audit_prompt:
            return JsonResponse({'error': '审核系统提示词不能为空'}, status=400)

        raw_topk = data.get('rag_top_k_per_category', 5)
        try:
            rag_top_k_per_category = int(raw_topk)
        except Exception:
            return JsonResponse({'error': '按类别召回数量必须为整数'}, status=400)
        if rag_top_k_per_category < 1 or rag_top_k_per_category > 20:
            return JsonResponse({'error': '按类别召回数量范围需在 1~20 之间'}, status=400)

        cfg.recommend_prompt = recommend_prompt
        cfg.audit_prompt = audit_prompt
        update_fields = ['recommend_prompt', 'audit_prompt', 'updated_at']
        if has_topk_column:
            cfg.rag_top_k_per_category = rag_top_k_per_category
            update_fields.append('rag_top_k_per_category')
        cfg.save(update_fields=update_fields)
        return JsonResponse({'status': 'ok', 'message': '提示词保存成功'})

    return JsonResponse({'error': 'POST or GET required'}, status=405)


@csrf_exempt
def audit_api_configs_view(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({'error': 'admin required'}, status=401)

    if request.method == 'GET':
        configs = list(AuditApiConfig.objects.all().values())
        return JsonResponse({'configs': configs})

    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
        except Exception:
            data = {}
        action = data.get('action')

        if action == 'add':
            is_primary = data.get('is_primary', False)
            if is_primary:
                AuditApiConfig.objects.filter(is_primary=True).update(is_primary=False)
            AuditApiConfig.objects.create(
                name=data.get('name', 'New Audit API'),
                api_key=data.get('api_key', ''),
                model_name=data.get('model_name', ''),
                base_url=data.get('base_url', 'https://api.siliconflow.cn/v1/chat/completions'),
                is_primary=is_primary,
                is_active=data.get('is_active', True)
            )
        elif action == 'edit':
            config_id = data.get('id')
            c = AuditApiConfig.objects.get(id=config_id)
            is_primary = data.get('is_primary', c.is_primary)
            if is_primary and not c.is_primary:
                AuditApiConfig.objects.filter(is_primary=True).update(is_primary=False)
            c.name = data.get('name', c.name)
            c.api_key = data.get('api_key', c.api_key)
            c.model_name = data.get('model_name', c.model_name)
            c.base_url = data.get('base_url', c.base_url)
            c.is_primary = is_primary
            c.is_active = data.get('is_active', c.is_active)
            c.save()
        elif action == 'delete':
            config_id = data.get('id')
            AuditApiConfig.objects.filter(id=config_id).delete()
        elif action == 'test':
            import time
            api_key = data.get('api_key', '')
            model_name = data.get('model_name', '')
            base_url = data.get('base_url', '')
            start_time = time.time()
            ok, err = _test_chat_api(base_url=base_url, api_key=api_key, model_name=model_name, probe_text='请仅回复 ok', timeout=15)
            latency = int((time.time() - start_time) * 1000)
            if ok:
                return JsonResponse({'status': 'ok', 'latency': latency})
            return JsonResponse({'error': err}, status=400)

        return JsonResponse({'status': 'ok'})

    return JsonResponse({'error': 'POST or GET required'}, status=405)


@csrf_exempt
def admin_start_data_update_view(request):
    if not (request.user.is_authenticated and request.user.is_staff):
        return JsonResponse({'error': 'admin required'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    import json
    max_items = 50
    try:
        body = json.loads(request.body)
        max_items = int(body.get('items_per_category', 50))
    except (ValueError, TypeError, json.JSONDecodeError):
        pass

    from .scraper_service import start_background_spider
    success, msg = start_background_spider(max_items=max_items)
    if success:
        return JsonResponse({'status': 'ok', 'message': msg})
    else:
        return JsonResponse({'error': msg}, status=400)

@csrf_exempt
def admin_stop_data_update_view(request):
    if not (request.user.is_authenticated and request.user.is_staff):
        return JsonResponse({'error': 'admin required'}, status=401)
        
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
        
    from .scraper_service import stop_background_spider
    success, msg = stop_background_spider()
    if success:
        return JsonResponse({'status': 'ok', 'message': msg})
    else:
        return JsonResponse({'error': msg}, status=400)

@csrf_exempt
def admin_data_update_status_view(request):
    if not (request.user.is_authenticated and request.user.is_staff):
        return JsonResponse({'error': 'admin required'}, status=401)
        
    from .scraper_service import scrape_status
    return JsonResponse({'status': 'ok', 'data': scrape_status})


def _normalize_text(v):
    if v is None:
        return ''
    return ' '.join(str(v).split())


def _infer_model(name):
    name = _normalize_text(name)
    if not name:
        return ''
    parts = name.split(' ', 1)
    return parts[1] if len(parts) > 1 else name


def _infer_brand(name, model=''):
    name = _normalize_text(name)
    model = _normalize_text(model)

    if not name:
        return ''

    token = name.split(' ', 1)[0]

    # 例：HP（惠普）G160、AULA（狼蛛）SC680
    m = re.match(r'^([A-Za-z][A-Za-z0-9_-]*|[\u4e00-\u9fffA-Za-z]+)', token)
    if m:
        candidate = m.group(1)
    else:
        candidate = token

    # 例：罗技MX Anywhere -> 罗技
    m2 = re.match(r'^([\u4e00-\u9fff]{2,6})[A-Za-z0-9].*', candidate)
    if m2:
        candidate = m2.group(1)

    # 避免把完整型号误认成品牌
    if model and candidate and candidate == model:
        parts = name.split(' ', 1)
        if len(parts) > 1:
            candidate = parts[0]

    return candidate[:100]


_CATEGORY_LABEL_MAP = CLEANER_CATEGORY_LABEL_MAP


def _infer_category_key(name, desc='', current=''):
    return cleaner_infer_category_key(name=name, desc=desc, current=current)


def _split_sql_statements(sql_text):
    """Split SQL script into statements, avoiding semicolons inside quotes/comments."""
    statements = []
    buff = []
    i = 0
    n = len(sql_text)
    in_single = False
    in_double = False
    in_backtick = False
    in_line_comment = False
    in_block_comment = False

    while i < n:
        ch = sql_text[i]
        nxt = sql_text[i + 1] if i + 1 < n else ''

        if in_line_comment:
            buff.append(ch)
            if ch == '\n':
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            buff.append(ch)
            if ch == '*' and nxt == '/':
                buff.append(nxt)
                i += 2
                in_block_comment = False
            else:
                i += 1
            continue

        if not in_single and not in_double and not in_backtick:
            if ch == '-' and nxt == '-':
                buff.append(ch)
                buff.append(nxt)
                i += 2
                in_line_comment = True
                continue
            if ch == '/' and nxt == '*':
                buff.append(ch)
                buff.append(nxt)
                i += 2
                in_block_comment = True
                continue

        if ch == "'" and not in_double and not in_backtick:
            in_single = not in_single
            buff.append(ch)
            i += 1
            continue

        if ch == '"' and not in_single and not in_backtick:
            in_double = not in_double
            buff.append(ch)
            i += 1
            continue

        if ch == '`' and not in_single and not in_double:
            in_backtick = not in_backtick
            buff.append(ch)
            i += 1
            continue

        if ch == ';' and not in_single and not in_double and not in_backtick:
            stmt = ''.join(buff).strip()
            if stmt:
                statements.append(stmt)
            buff = []
            i += 1
            continue

        buff.append(ch)
        i += 1

    tail = ''.join(buff).strip()
    if tail:
        statements.append(tail)
    return statements

@csrf_exempt
def admin_hardware_view(request):
    if not (request.user.is_authenticated and request.user.is_staff):
        return JsonResponse({'error': 'admin required'}, status=401)
    
    if request.method == 'GET':
        from .models import Hardware

        def _to_float(value):
            if value is None or value == '':
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        category = (request.GET.get('category') or '').strip().lower()
        brand = _normalize_text(request.GET.get('brand') or '')
        keyword = _normalize_text(request.GET.get('keyword') or request.GET.get('name') or '')
        min_price = _to_float(request.GET.get('min_price'))
        max_price = _to_float(request.GET.get('max_price'))

        base_qs = Hardware.objects.all()
        hw_qs = base_qs

        # 先做数据库层可下推的筛选，减少后续 Python 层处理量
        if category and category != 'all':
            hw_qs = hw_qs.filter(category=category)
        if keyword:
            hw_qs = hw_qs.filter(name__icontains=keyword)

        # 供前端下拉的筛选项（品牌用全量，避免切换筛选后选项丢失）
        brand_set = set()
        for b in base_qs.values_list('brand', flat=True):
            nb = _normalize_text(b)
            if nb:
                brand_set.add(nb)

        category_options = [
            {'value': key, 'label': label}
            for key, label in Hardware.CATEGORY_CHOICES
        ]

        data = []
        for hw in hw_qs:
            prices = list(hw.pricehistory_set.order_by('-date').values('date', 'price'))
            latest_price = prices[0]['price'] if prices else None
            normalized_name = _normalize_text(hw.name)
            normalized_brand = _normalize_text(getattr(hw, 'brand', ''))
            normalized_model = _normalize_text(hw.model)
            category_key = _infer_category_key(normalized_name, hw.description, getattr(hw, 'category', ''))
            if not normalized_brand:
                normalized_brand = _infer_brand(normalized_name, normalized_model)
            if not normalized_model:
                normalized_model = _infer_model(normalized_name)

            # 兜底筛选：兼容历史脏数据（如 category 未标准化）
            if category and category != 'all' and category_key != category:
                continue
            if brand and normalized_brand.lower() != brand.lower():
                continue
            if keyword and keyword.lower() not in normalized_name.lower():
                continue
            if min_price is not None and (latest_price is None or latest_price < min_price):
                continue
            if max_price is not None and (latest_price is None or latest_price > max_price):
                continue

            data.append({
                'id': hw.id,
                'name': normalized_name,
                'category': category_key,
                'category_label': _CATEGORY_LABEL_MAP.get(category_key, '其他'),
                'brand': normalized_brand,
                'model': normalized_model,
                'description': _normalize_text(hw.description),
                'latest_price': latest_price,
                'price_history': prices
            })
        return JsonResponse({
            'status': 'ok',
            'total': len(data),
            'filters': {
                'categories': category_options,
                'brands': sorted(list(brand_set)),
                'selected': {
                    'category': category,
                    'brand': brand,
                    'keyword': keyword,
                    'min_price': min_price,
                    'max_price': max_price,
                }
            },
            'data': data
        })
    
    return JsonResponse({'error': 'GET required'}, status=405)


@csrf_exempt
def admin_hardware_update_view(request):
    if not (request.user.is_authenticated and request.user.is_staff):
        return JsonResponse({'error': 'admin required'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        body = json.loads(request.body or '{}')
    except Exception:
        return JsonResponse({'error': 'invalid json'}, status=400)

    hw_id = body.get('id')
    if not hw_id:
        return JsonResponse({'error': 'id required'}, status=400)

    from .models import Hardware, PriceHistory

    try:
        hw = Hardware.objects.get(id=int(hw_id))
    except Exception:
        return JsonResponse({'error': 'hardware not found'}, status=404)

    category = _normalize_text(body.get('category')).lower()
    name = _normalize_text(body.get('name'))
    brand = _normalize_text(body.get('brand'))
    model = _normalize_text(body.get('model'))
    raw_price = body.get('price')

    allowed_categories = {k for k, _ in Hardware.CATEGORY_CHOICES}
    if category and category not in allowed_categories:
        return JsonResponse({'error': 'invalid category'}, status=400)
    if not name:
        return JsonResponse({'error': 'name required'}, status=400)

    price_val = None
    if raw_price is not None and str(raw_price).strip() != '':
        try:
            price_val = float(str(raw_price).strip())
        except Exception:
            return JsonResponse({'error': 'invalid price'}, status=400)
        if price_val < 0:
            return JsonResponse({'error': 'price must be >= 0'}, status=400)

    changed_fields = []
    if category and hw.category != category:
        hw.category = category
        changed_fields.append('category')
    if hw.name != name:
        hw.name = name
        changed_fields.append('name')
    if (hw.brand or '') != brand:
        hw.brand = brand
        changed_fields.append('brand')
    if (hw.model or '') != model:
        hw.model = model
        changed_fields.append('model')

    with transaction.atomic():
        if changed_fields:
            hw.save(update_fields=changed_fields)

        if price_val is not None:
            today = timezone.now().strftime('%Y-%m-%d')
            latest = hw.pricehistory_set.order_by('-id').first()
            if latest and latest.date == today:
                latest.price = price_val
                latest.save(update_fields=['price'])
            else:
                PriceHistory.objects.create(hardware=hw, date=today, price=price_val)

    latest_price_obj = hw.pricehistory_set.order_by('-id').first()
    latest_price = latest_price_obj.price if latest_price_obj else None

    return JsonResponse({
        'status': 'ok',
        'message': '硬件数据已更新',
        'data': {
            'id': hw.id,
            'category': hw.category,
            'name': hw.name,
            'brand': hw.brand,
            'model': hw.model,
            'latest_price': latest_price,
        }
    })


@csrf_exempt
def admin_hardware_import_sql_view(request):
    if not (request.user.is_authenticated and request.user.is_staff):
        return JsonResponse({'error': 'admin required'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return JsonResponse({'error': '请上传SQL文件'}, status=400)

    filename = (uploaded_file.name or '').lower()
    if not filename.endswith('.sql'):
        return JsonResponse({'error': '仅支持 .sql 文件'}, status=400)

    if uploaded_file.size and uploaded_file.size > 20 * 1024 * 1024:
        return JsonResponse({'error': 'SQL文件过大，请控制在20MB以内'}, status=400)

    raw = uploaded_file.read()
    sql_text = None
    for enc in ('utf-8-sig', 'utf-8', 'gbk', 'latin-1'):
        try:
            sql_text = raw.decode(enc)
            break
        except Exception:
            continue

    if sql_text is None:
        return JsonResponse({'error': 'SQL文件编码无法识别，请使用 UTF-8/GBK 编码'}, status=400)

    statements = _split_sql_statements(sql_text)
    if not statements:
        return JsonResponse({'error': 'SQL文件为空或无有效语句'}, status=400)

    executed = 0
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                if connection.vendor == 'sqlite':
                    # sqlite 对脚本执行兼容性更好
                    cursor.cursor.executescript(sql_text)
                    executed = len(statements)
                else:
                    for stmt in statements:
                        cursor.execute(stmt)
                        executed += 1
    except Exception as e:
        return JsonResponse({'error': f'SQL导入失败: {str(e)}'}, status=400)

    return JsonResponse({'status': 'ok', 'message': f'导入成功，共执行 {executed} 条SQL语句'})


@csrf_exempt
def admin_hardware_transform_view(request):
    if not (request.user.is_authenticated and request.user.is_staff):
        return JsonResponse({'error': 'admin required'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    from .models import Hardware

    updated_count = 0
    for hw in Hardware.objects.all():
        name = _normalize_text(hw.name)
        model = _normalize_text(hw.model)
        brand = _normalize_text(getattr(hw, 'brand', ''))
        category_key = _infer_category_key(name, hw.description, getattr(hw, 'category', ''))

        if not brand:
            brand = _infer_brand(name, model)
        if not model:
            model = _infer_model(name)

        changed = False
        if hw.name != name:
            hw.name = name
            changed = True
        if hw.model != model:
            hw.model = model
            changed = True
        if getattr(hw, 'brand', '') != brand:
            hw.brand = brand
            changed = True
        if getattr(hw, 'category', 'other') != category_key:
            hw.category = category_key
            changed = True

        if changed:
            hw.save(update_fields=['name', 'model', 'brand', 'category'])
            updated_count += 1

    return JsonResponse({'status': 'ok', 'message': f'数据转换完成，共更新 {updated_count} 条记录'})


_HARDWARE_DESC_FOCUS_BY_CATEGORY = {
    'cpu': '核心数、线程数、主频/睿频、功耗、是否带核显、适合场景',
    'gpu': '显存容量、功耗、接口、分辨率/刷新率能力、适合场景',
    'motherboard': '芯片组、CPU插槽、内存代际、扩展接口、板型、适合场景',
    'memory': '容量、频率、时序、代际、电压、适合场景',
    'storage': '容量、类型、接口、顺序读写速度、耐久度、适合场景',
    'psu': '额定功率、转换效率认证、模组类型、供电接口、适合场景',
    'case': '板型兼容、显卡限长、散热器限高、风扇位、适合场景',
    'cooler': '散热类型、热管/风扇规格、平台兼容、解热能力、适合场景',
    'laptop': 'CPU/GPU、内存、硬盘、屏幕、重量续航、适合场景',
    'monitor': '尺寸、分辨率、面板、刷新率、色域、接口、适合场景',
    'keyboard': '轴体/结构、连接方式、键位布局、做工手感、适合场景',
    'mouse': '传感器、DPI、重量、连接方式、续航、适合场景',
    'headphone': '发声单元、连接方式、降噪、麦克风、续航、适合场景',
    'speaker': '声道、功率、连接方式、频响、适合场景',
    'other': '核心参数、适合场景',
}


def _build_hardware_completion_prompt(hw, latest_price=None):
    category_key = _infer_category_key(hw.name, hw.description, getattr(hw, 'category', 'other'))
    category_label = _CATEGORY_LABEL_MAP.get(category_key, '其他')
    focus_schema = _HARDWARE_DESC_FOCUS_BY_CATEGORY.get(category_key, _HARDWARE_DESC_FOCUS_BY_CATEGORY['other'])

    name = _normalize_text(hw.name)
    brand = _normalize_text(getattr(hw, 'brand', '')) or _infer_brand(name, _normalize_text(hw.model))
    model = _normalize_text(hw.model) or _infer_model(name)
    old_desc = _normalize_text(hw.description)
    price_txt = f"{latest_price} 元" if latest_price is not None else '未知'

    return f"""
你是一个专业电脑硬件参数编辑助手。请基于公开网络可得信息（若模型支持联网检索请主动检索），对给定硬件生成“参数描述”文本。
要求：
1) 只输出合法 JSON，不要输出 markdown 代码块。
2) JSON 结构必须为：{{"description":"..."}}。
3) description 必须为简洁中文，且必须明确包含“适合场景：...”。
4) 优先覆盖这些参数点：{focus_schema}。
5) 若部分参数无法确定，可写“待确认”，但“适合场景”必须给出。

硬件名称：{name}
类别：{category_label}
品牌：{brand or '未知'}
型号：{model or '未知'}
参考价格：{price_txt}
当前描述：{old_desc or '无'}
""".strip()


def _extract_completed_description(content):
    parsed = _extract_json_from_text(content)

    desc = ''
    scene = ''
    if isinstance(parsed, dict):
        desc = _normalize_text(parsed.get('description') or parsed.get('desc') or parsed.get('text') or '')
        scene = _normalize_text(parsed.get('scene') or parsed.get('scenario') or parsed.get('适合场景') or '')
    else:
        desc = _normalize_text(str(content or ''))

    if not desc:
        return ''

    if '适合场景' not in desc and scene:
        tail = f"适合场景：{scene}"
        if not desc.endswith('。'):
            desc = f"{desc}。{tail}"
        else:
            desc = f"{desc}{tail}"

    if len(desc) > 360:
        desc = desc[:360].rstrip('，,。;； ') + '。'
    return desc


# 向量化配置：本地 BGE 小模型（可通过环境变量覆盖）
BGE_EMBEDDING_MODEL_ID = os.getenv('BGE_EMBEDDING_MODEL_ID', 'BAAI/bge-small-zh-v1.5')
BGE_HF_ENDPOINT = os.getenv('HF_ENDPOINT', os.getenv('BGE_HF_ENDPOINT', 'https://hf-mirror.com'))
BGE_BACKEND_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BGE_PROJECT_ROOT_DIR = os.path.dirname(BGE_BACKEND_ROOT_DIR)

_bge_manual_download_dir = os.path.join(
    BGE_PROJECT_ROOT_DIR,
    'downloaded_models',
    'bge-small-zh-v1.5'
)
_bge_backend_model_dir = os.path.join(
    BGE_BACKEND_ROOT_DIR,
    'models',
    'bge-small-zh-v1.5'
)

BGE_LOCAL_MODEL_DIR = os.getenv(
    'BGE_SMALL_ZH_MODEL_DIR',
    _bge_manual_download_dir if os.path.isdir(_bge_manual_download_dir) else _bge_backend_model_dir
)
BGE_HF_CACHE_DIR = os.getenv(
    'BGE_HF_CACHE_DIR',
    os.path.join(
        BGE_BACKEND_ROOT_DIR,
        'models',
        'hf_cache'
    )
)
BGE_COLLECTION_SUFFIX = 'bge_small_zh_v15'
_bge_model_cache = {
    'model': None,
    'source': '',
    'error': ''
}


def _vector_collection_name(category_key, dim):
    try:
        d = int(dim)
    except Exception:
        d = 256
    return f'hardware_knowledge_{category_key}_{BGE_COLLECTION_SUFFIX}_d{d}'


def _vector_table_name(category_key, dim):
    try:
        d = int(dim)
    except Exception:
        d = 256
    return f'hardware_vectors_{category_key}_{BGE_COLLECTION_SUFFIX}_d{d}'


def _text_to_deterministic_vector(text, dim=256):
    """将文本稳定映射到定长向量（无需外部嵌入模型）。"""
    import hashlib

    txt = _normalize_text(text)
    if not txt:
        return [0.0] * dim

    tokens = re.findall(r'[\u4e00-\u9fffA-Za-z0-9_\-\.]+', txt.lower())
    if not tokens:
        tokens = [txt.lower()]

    vec = [0.0] * dim
    for token in tokens:
        digest = hashlib.sha256(token.encode('utf-8')).digest()
        idx = int.from_bytes(digest[:4], 'big') % dim
        sign = 1.0 if (digest[4] % 2 == 0) else -1.0
        weight = 1.0 + (digest[5] / 255.0)
        vec[idx] += sign * weight

    norm = sum(v * v for v in vec) ** 0.5
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def _get_bge_embedding_model():
    """加载本地 BGE 模型（优先本地目录，其次模型ID）。"""
    cached = _bge_model_cache.get('model')
    if cached is not None:
        return cached, _bge_model_cache.get('source', '')

    try:
        from sentence_transformers import SentenceTransformer
    except Exception as e:
        _bge_model_cache['error'] = f'sentence-transformers 不可用: {e}'
        return None, ''

    try:
        # 强制使用 Hugging Face 中国镜像
        if BGE_HF_ENDPOINT:
            os.environ['HF_ENDPOINT'] = BGE_HF_ENDPOINT

        model_path = BGE_LOCAL_MODEL_DIR
        model_source = ''
        if model_path and os.path.isdir(model_path):
            model = SentenceTransformer(model_path)
            model_source = model_path
        else:
            # 若本地目录不存在，优先通过镜像下载到本地后再本地加载
            os.makedirs(BGE_HF_CACHE_DIR, exist_ok=True)
            os.makedirs(BGE_LOCAL_MODEL_DIR, exist_ok=True)

            try:
                from huggingface_hub import snapshot_download

                local_repo_path = snapshot_download(
                    repo_id=BGE_EMBEDDING_MODEL_ID,
                    local_dir=BGE_LOCAL_MODEL_DIR,
                    cache_dir=BGE_HF_CACHE_DIR,
                    resume_download=True,
                )
                model = SentenceTransformer(local_repo_path, local_files_only=True)
                model_source = f"{BGE_HF_ENDPOINT}::{BGE_EMBEDDING_MODEL_ID}"
            except Exception as mirror_err:
                # 再次兜底：仍由 sentence-transformers 走 HF_ENDPOINT 下载
                model = SentenceTransformer(BGE_EMBEDDING_MODEL_ID)
                model_source = f"{BGE_HF_ENDPOINT}::{BGE_EMBEDDING_MODEL_ID}"
                _bge_model_cache['error'] = f"mirror snapshot failed: {mirror_err}"

        _bge_model_cache['model'] = model
        _bge_model_cache['source'] = model_source
        _bge_model_cache['error'] = ''
        return model, model_source
    except Exception as e:
        _bge_model_cache['error'] = str(e)
        return None, ''


def _embed_text_with_bge(text):
    """使用 bge-small-zh-v1.5 生成向量；失败时回退确定性向量。"""
    txt = _normalize_text(text)
    if not txt:
        return [0.0] * 256, {'embedding_model': 'deterministic-fallback', 'fallback_reason': 'empty text'}

    model, source = _get_bge_embedding_model()
    if model is None:
        return _text_to_deterministic_vector(txt, dim=256), {
            'embedding_model': 'deterministic-fallback',
            'fallback_reason': _bge_model_cache.get('error', 'bge load failed')[:180],
        }

    try:
        vec = model.encode([txt], normalize_embeddings=True, show_progress_bar=False)[0]
        return [float(x) for x in vec], {
            'embedding_model': 'bge-small-zh-v1.5',
            'model_source': source,
            'fallback_reason': '',
        }
    except Exception as e:
        return _text_to_deterministic_vector(txt, dim=256), {
            'embedding_model': 'deterministic-fallback',
            'fallback_reason': str(e)[:180],
        }


@csrf_exempt
def admin_hardware_complete_descriptions_view(request):
    if not (request.user.is_authenticated and request.user.is_staff):
        return JsonResponse({'error': 'admin required'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        body = json.loads(request.body or '{}')
    except Exception:
        body = {}

    from .models import Hardware

    ids = body.get('ids') or []
    if ids and not isinstance(ids, list):
        return JsonResponse({'error': 'ids must be a list'}, status=400)

    configs = list(ApiConfig.objects.filter(is_active=True).order_by('-is_primary', 'id'))
    if not configs:
        return JsonResponse({'error': '未配置可用的推荐系统API，请先在 API配置管理 中启用至少一个配置'}, status=400)

    hw_qs = Hardware.objects.all().order_by('id')
    if ids:
        valid_ids = []
        for x in ids:
            try:
                valid_ids.append(int(x))
            except Exception:
                continue
        hw_qs = hw_qs.filter(id__in=valid_ids)

    hw_list = list(hw_qs)
    if not hw_list:
        return JsonResponse({'status': 'ok', 'message': '没有可补全的数据', 'updated': 0, 'failed': 0})

    updated_count = 0
    unchanged_count = 0
    failed_count = 0
    failed_details = []

    for hw in hw_list:
        latest_obj = hw.pricehistory_set.order_by('-id').first()
        latest_price = latest_obj.price if latest_obj else None

        prompt = _build_hardware_completion_prompt(hw, latest_price=latest_price)
        messages = [{"role": "user", "content": prompt}]

        generated_desc = ''
        last_error = ''
        for config in configs:
            ok, content_or_error = _call_chat_api(
                config=config,
                messages=messages,
                temperature=0.2,
                timeout=28,
                max_tokens=360,
            )
            if ok:
                generated_desc = _extract_completed_description(content_or_error)
                if generated_desc:
                    break
                last_error = 'API返回为空或格式无法解析'
            else:
                last_error = str(content_or_error)

        if not generated_desc:
            failed_count += 1
            failed_details.append({
                'id': hw.id,
                'name': _normalize_text(hw.name),
                'error': last_error[:160] if last_error else '补全失败',
            })
            continue

        old_desc = _normalize_text(hw.description)
        if old_desc == generated_desc:
            unchanged_count += 1
            continue

        hw.description = generated_desc
        hw.save(update_fields=['description'])
        updated_count += 1

    message = f'数据补全完成：更新 {updated_count} 条，未变化 {unchanged_count} 条，失败 {failed_count} 条。'
    return JsonResponse({
        'status': 'ok',
        'message': message,
        'updated': updated_count,
        'unchanged': unchanged_count,
        'failed': failed_count,
        'failed_items': failed_details[:20],
    })


@csrf_exempt
def admin_hardware_vectorize_view(request):
    if not (request.user.is_authenticated and request.user.is_staff):
        return JsonResponse({'error': 'admin required'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        body = json.loads(request.body or '{}')
    except Exception:
        body = {}

    ids = body.get('ids') or []
    if ids and not isinstance(ids, list):
        return JsonResponse({'error': 'ids must be a list'}, status=400)

    chromadb = None
    chroma_init_error = ''
    try:
        import chromadb as _chromadb
        chromadb = _chromadb
    except Exception as e:
        chroma_init_error = str(e)

    from .models import Hardware

    hw_qs = Hardware.objects.all().order_by('id')
    if ids:
        valid_ids = []
        for x in ids:
            try:
                valid_ids.append(int(x))
            except Exception:
                continue
        hw_qs = hw_qs.filter(id__in=valid_ids)

    hw_list = list(hw_qs)
    if not hw_list:
        return JsonResponse({'status': 'ok', 'message': '没有可向量化的数据', 'vectorized': 0, 'failed': 0})

    vector_store_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'vector_store',
        'chroma_hardware'
    )
    os.makedirs(vector_store_path, exist_ok=True)

    vector_db_backend = 'chroma'
    sqlite_conn = None
    sqlite_path = ''
    chroma_collections = {}
    sqlite_tables_created = set()
    if chromadb is not None:
        try:
            client = chromadb.PersistentClient(path=vector_store_path)
        except Exception as e:
            chroma_init_error = str(e)
            vector_db_backend = 'sqlite'
    else:
        vector_db_backend = 'sqlite'

    if vector_db_backend == 'sqlite':
        import sqlite3
        sqlite_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'vector_store'
        )
        os.makedirs(sqlite_dir, exist_ok=True)
        sqlite_path = os.path.join(sqlite_dir, 'hardware_vectors.sqlite3')
        sqlite_conn = sqlite3.connect(sqlite_path)
        sqlite_conn.commit()

    vectorized_count = 0
    failed_count = 0
    failed_items = []
    per_category_counts = {}
    allowed_categories = {k for k, _ in Hardware.CATEGORY_CHOICES}
    embedding_models_used = set()
    fallback_reasons = []

    for hw in hw_list:
        try:
            latest_obj = hw.pricehistory_set.order_by('-id').first()
            latest_price = latest_obj.price if latest_obj else None

            category_key = _infer_category_key(hw.name, hw.description, getattr(hw, 'category', 'other'))
            if category_key not in allowed_categories:
                category_key = 'other'
            category_label = _CATEGORY_LABEL_MAP.get(category_key, '其他')
            name = _normalize_text(hw.name)
            brand = _normalize_text(getattr(hw, 'brand', ''))
            model = _normalize_text(hw.model)
            desc = _normalize_text(hw.description)

            doc_text = (
                f"硬件ID: {hw.id}\n"
                f"名称: {name}\n"
                f"类别: {category_label}\n"
                f"品牌: {brand or '未知'}\n"
                f"型号: {model or '未知'}\n"
                f"价格: {latest_price if latest_price is not None else '未知'}\n"
                f"参数描述: {desc or '无'}"
            )
            embedding, emb_meta = _embed_text_with_bge(doc_text)
            emb_dim = len(embedding) if isinstance(embedding, list) and embedding else 256
            emb_model = emb_meta.get('embedding_model', '')
            if emb_model:
                embedding_models_used.add(emb_model)
            if emb_meta.get('fallback_reason'):
                fallback_reasons.append(str(emb_meta.get('fallback_reason'))[:180])

            metadata_obj = {
                'hardware_id': int(hw.id),
                'name': name[:255],
                'category': category_key[:30],
                'brand': (brand or '')[:100],
                'model': (model or '')[:255],
                'price': float(latest_price) if latest_price is not None else -1.0,
                'updated_at': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
                'embedding_model': emb_model or 'unknown',
            }

            if vector_db_backend == 'chroma':
                target_col_name = _vector_collection_name(category_key, emb_dim)
                col = chroma_collections.get(target_col_name)
                if col is None:
                    col = client.get_or_create_collection(name=target_col_name)
                    chroma_collections[target_col_name] = col
                col.upsert(
                    ids=[f'hardware_{hw.id}'],
                    documents=[doc_text],
                    embeddings=[embedding],
                    metadatas=[metadata_obj]
                )
            else:
                table_name = _vector_table_name(category_key, emb_dim)
                if table_name not in sqlite_tables_created:
                    sqlite_conn.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {table_name} (
                            hardware_id INTEGER PRIMARY KEY,
                            vector_json TEXT NOT NULL,
                            document TEXT,
                            metadata_json TEXT,
                            updated_at TEXT
                        )
                        """
                    )
                    sqlite_tables_created.add(table_name)

                sqlite_conn.execute(
                    f"""
                    INSERT OR REPLACE INTO {table_name} (hardware_id, vector_json, document, metadata_json, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        int(hw.id),
                        json.dumps(embedding, ensure_ascii=False),
                        doc_text,
                        json.dumps(metadata_obj, ensure_ascii=False),
                        metadata_obj['updated_at'],
                    )
                )
            vectorized_count += 1
            per_category_counts[category_key] = per_category_counts.get(category_key, 0) + 1
        except Exception as e:
            failed_count += 1
            failed_items.append({
                'id': int(hw.id),
                'name': _normalize_text(hw.name),
                'error': str(e)[:160]
            })

    if sqlite_conn is not None:
        sqlite_conn.commit()
        sqlite_conn.close()

    msg = f'向量化完成：成功 {vectorized_count} 条，失败 {failed_count} 条。'
    if vector_db_backend == 'sqlite' and chroma_init_error:
        msg = f"{msg} 当前已自动切换到 SQLite 向量库兜底。"
    if 'deterministic-fallback' in embedding_models_used:
        msg = f"{msg} 注意：部分数据使用了兜底向量，请检查本地 BGE 模型部署。"

    category_targets = []
    if vector_db_backend == 'chroma':
        category_targets = sorted(list(chroma_collections.keys()))
    else:
        category_targets = sorted(list(sqlite_tables_created))

    return JsonResponse({
        'status': 'ok',
        'message': msg,
        'vectorized': vectorized_count,
        'failed': failed_count,
        'vector_backend': vector_db_backend,
        'category_targets': category_targets,
        'category_counts': per_category_counts,
        'embedding_models_used': sorted(list(embedding_models_used)),
        'embedding_fallback_reasons': fallback_reasons[:8],
        'vector_store_path': vector_store_path if vector_db_backend == 'chroma' else sqlite_path,
        'fallback_reason': chroma_init_error[:180] if chroma_init_error else '',
        'failed_items': failed_items[:20],
    })


@csrf_exempt
def admin_hardware_vector_cleanup_old_view(request):
    if not (request.user.is_authenticated and request.user.is_staff):
        return JsonResponse({'error': 'admin required'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    from .models import Hardware

    categories = [k for k, _ in Hardware.CATEGORY_CHOICES]
    chroma_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'vector_store',
        'chroma_hardware'
    )
    sqlite_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'vector_store',
        'hardware_vectors.sqlite3'
    )

    deleted_chroma = []
    deleted_sqlite = []
    errors = []

    # 1) 删除旧 Chroma collection
    try:
        import chromadb
        if os.path.isdir(chroma_path):
            client = chromadb.PersistentClient(path=chroma_path)
            # 旧命名（无维度后缀）
            old_collection_names = []
            for c in categories:
                old_collection_names.append(f'hardware_knowledge_{c}')
                old_collection_names.append(f'hardware_knowledge_{c}_{BGE_COLLECTION_SUFFIX}')

            for name in old_collection_names:
                try:
                    client.delete_collection(name=name)
                    deleted_chroma.append(name)
                except Exception:
                    continue
    except Exception as e:
        errors.append(f'chroma cleanup error: {str(e)[:180]}')

    # 2) 删除旧 SQLite 表
    try:
        import sqlite3
        if os.path.exists(sqlite_path):
            conn = sqlite3.connect(sqlite_path)
            try:
                for c in categories:
                    old_tables = [
                        f'hardware_vectors_{c}',
                        f'hardware_vectors_{c}_{BGE_COLLECTION_SUFFIX}',
                    ]
                    for tb in old_tables:
                        try:
                            conn.execute(f'DROP TABLE IF EXISTS {tb}')
                            deleted_sqlite.append(tb)
                        except Exception:
                            continue
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        errors.append(f'sqlite cleanup error: {str(e)[:180]}')

    # 去重展示
    deleted_chroma = sorted(list(set(deleted_chroma)))
    deleted_sqlite = sorted(list(set(deleted_sqlite)))

    msg = f'旧向量库清理完成：删除 Chroma 集合 {len(deleted_chroma)} 个，删除 SQLite 表 {len(deleted_sqlite)} 个。'
    return JsonResponse({
        'status': 'ok',
        'message': msg,
        'deleted_chroma_collections': deleted_chroma,
        'deleted_sqlite_tables': deleted_sqlite,
        'errors': errors,
    })

@csrf_exempt
def admin_hardware_cleanup_view(request):
    if not (request.user.is_authenticated and request.user.is_staff):
        return JsonResponse({'error': 'admin required'}, status=401)
        
    if request.method == 'POST':
        from .models import Hardware, RecommendedScheme, RecommendedScheme, PriceHistory
        deleted_count = 0
        
        # 1. 剔除价格为0（或者没有价格）的无效数据
        # 查找最新的priceΪ0的记录并删除对应的hardware，或者没有任何price history直接删除
        all_hws = Hardware.objects.all()
        to_delete_ids = set()
        
        for hw in all_hws:
            latest_price = hw.pricehistory_set.order_by('-date').first()
            if not latest_price or latest_price.price <= 0:
                to_delete_ids.add(hw.id)
                
        # 2. 剔除重复数据（根据名称或者型号去重，保留最新更新的一条）
        # 我们先剔除价格为0的，剩下的再查重
        Hardware.objects.filter(id__in=to_delete_ids).delete()
        deleted_count += len(to_delete_ids)
        
        remaining_hws = Hardware.objects.all().order_by('-id')
        seen_names = set()
        duplicate_ids = set()
        
        for hw in remaining_hws:
            if hw.name in seen_names:
                duplicate_ids.add(hw.id)
            else:
                seen_names.add(hw.name)
                
        Hardware.objects.filter(id__in=duplicate_ids).delete()
        deleted_count += len(duplicate_ids)
        
        return JsonResponse({'status': 'ok', 'message': f'成功清理了 {deleted_count} 条无效或重复数据'})
        
    return JsonResponse({'error': 'POST required'}, status=405)

def _is_admin(user):
    return user.is_authenticated and user.is_staff


@csrf_exempt
def scrape_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        data = {}
    # allow admin users (session) or admin_key
    admin_key = data.get('admin_key')
    user = request.user if hasattr(request, 'user') else None
    if not (_is_admin(user) or admin_key == os.getenv('ADMIN_KEY', 'changeme')):
        return JsonResponse({'error': 'unauthorized'}, status=401)
    urls = data.get('urls') or []
    if not scrape_urls:
        return JsonResponse({'error': 'scraper not available'}, status=500)
    items = scrape_urls(urls)
    return JsonResponse({'scraped': len(items), 'items': items})


@csrf_exempt
def register_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        data = {}
    nickname = data.get('nickname')
    password = data.get('password')
    email = data.get('email')
    phone = data.get('phone')
    address = data.get('address')
    if not nickname or not password or not email or not phone or not address:
        return JsonResponse({'error': 'all fields required'}, status=400)
        
    if Profile.objects.filter(nickname=nickname).exists():
        return JsonResponse({'error': 'nickname already taken. please choose another'}, status=400)
    
    # generate username from nickname
    username = nickname
    if User.objects.filter(username=username).exists():
        import time
        username = f"{nickname}{int(time.time() * 1000)}"
    user = User.objects.create_user(username=username, password=password, email=email)
    Profile.objects.create(user=user, nickname=nickname, phone=phone, address=address)
    return JsonResponse({'status': 'ok', 'id': user.id})


@csrf_exempt
def login_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        data = {}
    nickname = data.get('nickname')
    password = data.get('password')
    if not nickname or not password:
        return JsonResponse({'error': 'nickname and password required'}, status=400)
        
    # 尝试作为直接的 username 登录（比如 admin 管理员）
    user = authenticate(request, username=nickname, password=password)
    
    if user is None:
        # 尝试通过 nickname 查找绑定的 user
        try:
            db_user = Profile.objects.get(nickname=nickname).user
            user = authenticate(request, username=db_user.username, password=password)
        except Profile.DoesNotExist:
            user = None

    if user is None:
        return JsonResponse({'error': 'invalid credentials'}, status=401)
        
    try:
        profile = user.profile
        if getattr(profile, 'banned', False):
            return JsonResponse({'error': '你已被封禁，详情咨询管理员'}, status=403)
    except Exception:
        profile = Profile.objects.create(user=user, nickname=nickname)
        
    login(request, user)
    return JsonResponse({
        'status': 'ok',
        'user': profile.to_dict()
    })

@csrf_exempt
def logout_view(request):
    # simple logout
    logout(request)
    return JsonResponse({'status': 'ok'})


@csrf_exempt
def profile_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'login required'}, status=401)
    try:
        profile = request.user.profile
    except Profile.DoesNotExist:
        profile = Profile.objects.create(user=request.user)
    if request.method == 'GET':
        return JsonResponse({'profile': profile.to_dict()})
    if request.method == 'PUT' or request.method == 'POST':
        is_multipart = (request.content_type or '').startswith('multipart/form-data')
        if is_multipart:
            data = request.POST
        else:
            try:
                data = json.loads(request.body.decode('utf-8') or '{}')
            except Exception:
                data = {}

        profile.nickname = data.get('nickname', profile.nickname)
        profile.phone = data.get('phone', profile.phone)
        profile.address = data.get('address', profile.address)
        email = data.get('email')
        if email:
            request.user.email = email
            request.user.save()

        avatar_file = request.FILES.get('avatar') if is_multipart else None
        if avatar_file is not None:
            max_size = 5 * 1024 * 1024
            ctype = (getattr(avatar_file, 'content_type', '') or '').lower()
            if not ctype.startswith('image/'):
                return JsonResponse({'error': '头像文件必须是图片格式'}, status=400)
            if avatar_file.size > max_size:
                return JsonResponse({'error': '头像大小不能超过5MB'}, status=400)
            profile.avatar = avatar_file

        remove_avatar = str(data.get('remove_avatar', '')).lower() in ('1', 'true', 'yes', 'on')
        if remove_avatar and profile.avatar:
            profile.avatar.delete(save=False)
            profile.avatar = None
            
        new_password = data.get('new_password')
        if new_password:
            request.user.set_password(new_password)
            request.user.save()
            update_session_auth_hash(request, request.user)
            
        profile.save()
        return JsonResponse({'status': 'ok', 'profile': profile.to_dict()})
    return JsonResponse({'error': 'method not allowed'}, status=405)


@csrf_exempt
def activate_admin_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'login required'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        data = {}
    code = data.get('code')
    # 激活码从环境变量读取（ADMIN_ACTIVATE_CODE）；未配置时该入口关闭。
    expected_code = os.getenv('ADMIN_ACTIVATE_CODE', '')
    if expected_code and code == expected_code:
        request.user.is_staff = True
        request.user.save()
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'error': 'invalid code'}, status=400)


@csrf_exempt
def admin_ban_view(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({'error': 'admin required'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        data = {}
    user_id = data.get('user_id')
    ban = data.get('ban', True)
    try:
        u = User.objects.get(id=user_id)
        p, _ = Profile.objects.get_or_create(user=u)
        p.banned = bool(ban)
        p.save()
        return JsonResponse({'status': 'ok'})
    except User.DoesNotExist:
        return JsonResponse({'error': 'user not found'}, status=404)


@csrf_exempt
def posts_view(request):
    allowed_boards = {'square', 'qa', 'system'}
    avatar_map = {}

    def _build_avatar_map(usernames):
        if not usernames:
            return {}
        rows = Profile.objects.filter(user__username__in=usernames).select_related('user')
        return {
            r.user.username: (r.avatar.url if getattr(r, 'avatar', None) else '')
            for r in rows
        }

    def _file_info(file_field):
        return {
            'name': file_field.name.split('/')[-1],
            'url': file_field.url,
            'size': file_field.size,
        }

    def _serialize_post(p):
        liked = False
        if request.user.is_authenticated:
            liked = request.user in p.likes.all()
        is_ai_hidden = _is_ai_hidden(p)
        latest_comment = Comment.objects.filter(post_id=p.id, is_deleted=False).order_by('-created_at').first()
        return {
            'id': p.id,
            'title': (AI_HIDDEN_POST_TEXT if is_ai_hidden else p.title),
            'content': (AI_HIDDEN_POST_TEXT if is_ai_hidden else p.content),
            'author': p.author,
            'author_avatar_url': avatar_map.get(p.author, ''),
            'board': getattr(p, 'board', 'square'),
            'created_at': p.created_at.isoformat() if p.created_at else None,
            'comments_count': Comment.objects.filter(post_id=p.id, is_deleted=False).count(),
            'latest_reply_author': latest_comment.author if latest_comment else '',
            'latest_reply_at': latest_comment.created_at.isoformat() if latest_comment and latest_comment.created_at else None,
            'likes_count': p.likes.count(),
            'is_liked': liked,
            'is_ai_hidden': is_ai_hidden,
            'images': ([] if is_ai_hidden else [_file_info(img.file) for img in p.images.all()]),
            'attachments': ([] if is_ai_hidden else [_file_info(att.file) for att in p.attachments.all()]),
        }

    def _validate_uploads(images, attachments):
        max_size = 10 * 1024 * 1024
        for f in images:
            if not (getattr(f, 'content_type', '') or '').startswith('image/'):
                return '仅支持上传图片文件到图片区域'
            if f.size > max_size:
                return f'图片 {f.name} 超过 10MB 限制'
        for f in attachments:
            if f.size > max_size:
                return f'附件 {f.name} 超过 10MB 限制'
        return None

    if request.method == 'GET':
        qs = Post.objects.filter(is_deleted=False).order_by('-id')
        board = (request.GET.get('board') or '').strip()
        if board:
            if board not in allowed_boards:
                return JsonResponse({'error': 'invalid board'}, status=400)
            qs = qs.filter(board=board)
        author = request.GET.get('author')
        if author:
            qs = qs.filter(author=author)
        avatar_map = _build_avatar_map(list(qs.values_list('author', flat=True).distinct()))
        out = [_serialize_post(p) for p in qs]
        return JsonResponse({'posts': out})
    if request.method == 'POST':
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'login required'}, status=401)
        try:
            profile = request.user.profile
            if profile.banned:
                return JsonResponse({'error': 'banned'}, status=403)
        except Profile.DoesNotExist:
            pass
        is_multipart = (request.content_type or '').startswith('multipart/form-data')
        if is_multipart:
            data = request.POST
            title = data.get('title')
            content = data.get('content', '')
            board = (data.get('board') or 'square').strip()
            images = request.FILES.getlist('images')
            attachments = request.FILES.getlist('attachments')
        else:
            try:
                data = json.loads(request.body.decode('utf-8') or '{}')
            except Exception:
                data = {}
            title = data.get('title')
            content = data.get('content', '')
            board = (data.get('board') or 'square').strip()
            images = []
            attachments = []

        if not title:
            return JsonResponse({'error': 'title required'}, status=400)
        if board not in allowed_boards:
            return JsonResponse({'error': 'invalid board'}, status=400)
        if board == 'system' and not request.user.is_staff:
            return JsonResponse({'error': '仅管理员可在系统通知发布内容'}, status=403)
        err = _validate_uploads(images, attachments)
        if err:
            return JsonResponse({'error': err}, status=400)

        author = request.user.username
        avatar_map = _build_avatar_map([author])
        p = Post.objects.create(title=title, content=content, author=author, board=board)
        for f in images:
            PostImage.objects.create(post=p, file=f)
        for f in attachments:
            PostAttachment.objects.create(post=p, file=f)
        return JsonResponse({'id': p.id, 'title': p.title, 'post': _serialize_post(p)})
    return JsonResponse({'error': 'method not allowed'}, status=405)


@csrf_exempt
def comments_view(request, post_id):
    avatar_map = {}

    def _build_avatar_map(usernames):
        if not usernames:
            return {}
        rows = Profile.objects.filter(user__username__in=usernames).select_related('user')
        return {
            r.user.username: (r.avatar.url if getattr(r, 'avatar', None) else '')
            for r in rows
        }

    def _file_info(file_field):
        return {
            'name': file_field.name.split('/')[-1],
            'url': file_field.url,
            'size': file_field.size,
        }

    def _serialize_comment(c):
        liked = False
        if request.user.is_authenticated:
            liked = request.user in c.likes.all()
        is_ai_hidden = _is_ai_hidden(c)
        parent_info = None
        if c.parent_comment_id:
            parent_content = ''
            if c.parent_comment and c.parent_comment.is_deleted:
                parent_content = '[该回复已删除]'
            elif c.parent_comment and c.parent_comment.content:
                parent_content = c.parent_comment.content[:80]
            parent_info = {
                'id': c.parent_comment_id,
                'author': c.parent_comment.author if c.parent_comment else '',
                'content': parent_content,
            }
        return {
            'id': c.id,
            'post': c.post_id,
            'parent_comment_id': c.parent_comment_id,
            'parent_comment': parent_info,
            'content': (AI_HIDDEN_COMMENT_TEXT if is_ai_hidden else c.content),
            'author': c.author,
            'author_avatar_url': avatar_map.get(c.author, ''),
            'created_at': c.created_at.isoformat() if c.created_at else None,
            'likes_count': c.likes.count(),
            'is_liked': liked,
            'is_ai_hidden': is_ai_hidden,
            'images': ([] if is_ai_hidden else [_file_info(img.file) for img in c.images.all()]),
            'attachments': ([] if is_ai_hidden else [_file_info(att.file) for att in c.attachments.all()]),
        }

    def _validate_uploads(images, attachments):
        max_size = 10 * 1024 * 1024
        for f in images:
            if not (getattr(f, 'content_type', '') or '').startswith('image/'):
                return '仅支持上传图片文件到图片区域'
            if f.size > max_size:
                return f'图片 {f.name} 超过 10MB 限制'
        for f in attachments:
            if f.size > max_size:
                return f'附件 {f.name} 超过 10MB 限制'
        return None

    if request.method == 'GET':
        qs = Comment.objects.filter(post_id=post_id, is_deleted=False).order_by('id')
        avatar_map = _build_avatar_map(list(qs.values_list('author', flat=True).distinct()))
        out = [_serialize_comment(c) for c in qs]
        return JsonResponse({'comments': out})
    if request.method == 'POST':
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'login required'}, status=401)
        try:
            post_obj = Post.objects.get(id=post_id)
        except Post.DoesNotExist:
            return JsonResponse({'error': 'post not found'}, status=404)
        if _is_ai_hidden(post_obj):
            return JsonResponse({'error': '此动态正在等待管理员核实，暂不可评论'}, status=403)
        if getattr(post_obj, 'board', 'square') == 'system' and not request.user.is_staff:
            return JsonResponse({'error': '仅管理员可在系统通知发布内容'}, status=403)
        try:
            profile = request.user.profile
            if profile.banned:
                return JsonResponse({'error': 'banned'}, status=403)
        except Profile.DoesNotExist:
            pass
        is_multipart = (request.content_type or '').startswith('multipart/form-data')
        if is_multipart:
            data = request.POST
            content = data.get('content')
            parent_comment_id = data.get('parent_comment_id')
            images = request.FILES.getlist('images')
            attachments = request.FILES.getlist('attachments')
        else:
            try:
                data = json.loads(request.body.decode('utf-8') or '{}')
            except Exception:
                data = {}
            content = data.get('content')
            parent_comment_id = data.get('parent_comment_id')
            images = []
            attachments = []

        if (not content or not str(content).strip()) and not images and not attachments:
            return JsonResponse({'error': 'content required'}, status=400)
        err = _validate_uploads(images, attachments)
        if err:
            return JsonResponse({'error': err}, status=400)

        parent_comment = None
        if parent_comment_id not in (None, '', 0, '0'):
            try:
                parent_comment = Comment.objects.get(id=int(parent_comment_id), post_id=post_id)
            except (Comment.DoesNotExist, ValueError, TypeError):
                return JsonResponse({'error': 'parent comment not found'}, status=400)

        author = request.user.username
        avatar_map = _build_avatar_map([author])
        c = Comment.objects.create(post_id=post_id, parent_comment=parent_comment, content=content, author=author)
        for f in images:
            CommentImage.objects.create(comment=c, file=f)
        for f in attachments:
            CommentAttachment.objects.create(comment=c, file=f)

        post_author = post_obj.author
        recipients = set()
        if post_author:
            recipients.add(('post', post_id, post_author))
        if parent_comment is not None and parent_comment.author:
            recipients.add(('comment', parent_comment.id, parent_comment.author))

        for target_type, target_id, recipient_username in recipients:
            _create_reply_notification(
                recipient_username=recipient_username,
                actor_user=request.user,
                target_type=target_type,
                target_id=target_id,
                source_post_id=post_id,
                reply_comment_id=c.id,
            )

        return JsonResponse({'id': c.id, 'comment': _serialize_comment(c)})
    return JsonResponse({'error': 'method not allowed'}, status=405)


@csrf_exempt
def post_detail_view(request, post_id):
    try:
        from .models import Post, Comment, Profile
        post = Post.objects.get(id=post_id)
    except Post.DoesNotExist:
        return JsonResponse({'error': 'post not found'}, status=404)
    if request.method == 'GET':
        comments = Comment.objects.filter(post_id=post_id, is_deleted=False).order_by('id')
        usernames = {post.author}
        usernames.update(c.author for c in comments)
        avatar_rows = Profile.objects.filter(user__username__in=usernames).select_related('user')
        avatar_map = {
            r.user.username: (r.avatar.url if getattr(r, 'avatar', None) else '')
            for r in avatar_rows
        }
        def _file_info(file_field):
            return {
                'name': file_field.name.split('/')[-1],
                'url': file_field.url,
                'size': file_field.size,
            }

        post_liked = request.user.is_authenticated and request.user in post.likes.all()
        post_is_ai_hidden = _is_ai_hidden(post)
        return JsonResponse({
            'post': {
                'id': post.id,
                'title': (AI_HIDDEN_POST_TEXT if post_is_ai_hidden else post.title),
                'content': (AI_HIDDEN_POST_TEXT if post_is_ai_hidden else post.content),
                'author': post.author,
                'author_avatar_url': avatar_map.get(post.author, ''),
                'board': getattr(post, 'board', 'square'),
                'likes_count': post.likes.count(),
                'is_liked': post_liked,
                'is_ai_hidden': post_is_ai_hidden,
                'images': ([] if post_is_ai_hidden else [_file_info(img.file) for img in post.images.all()]),
                'attachments': ([] if post_is_ai_hidden else [_file_info(att.file) for att in post.attachments.all()]),
            },
            'comments': [
                {
                    'id': c.id,
                    'parent_comment_id': c.parent_comment_id,
                    'parent_comment': {
                        'id': c.parent_comment_id,
                        'author': c.parent_comment.author if c.parent_comment else '',
                        'content': ('[该回复已删除]' if c.parent_comment and c.parent_comment.is_deleted else (c.parent_comment.content[:80] if c.parent_comment and c.parent_comment.content else '')),
                    } if c.parent_comment_id else None,
                    'content': (AI_HIDDEN_COMMENT_TEXT if _is_ai_hidden(c) else c.content),
                    'author': c.author,
                    'author_avatar_url': avatar_map.get(c.author, ''),
                    'likes_count': c.likes.count(),
                    'is_liked': request.user.is_authenticated and request.user in c.likes.all(),
                    'is_ai_hidden': _is_ai_hidden(c),
                    'images': ([] if _is_ai_hidden(c) else [_file_info(img.file) for img in c.images.all()]),
                    'attachments': ([] if _is_ai_hidden(c) else [_file_info(att.file) for att in c.attachments.all()]),
                }
                for c in comments
            ]
        })
    if request.method == 'DELETE':
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'login required'}, status=401)
        if request.user.username != post.author and not request.user.is_staff:
            return JsonResponse({'error': 'forbidden'}, status=403)
        is_admin_delete_other = request.user.is_staff and request.user.username != post.author
        post.is_deleted = True
        import django.utils.timezone as timezone
        post.deleted_at = timezone.now()
        post.save()
        if is_admin_delete_other:
            admin_name = _display_name(request.user)
            deleted_content = _preview_text(post.content, 160)
            _create_system_notification(
                recipient_username=post.author,
                target_type='post',
                target_id=post.id,
                source_post_id=post.id,
                title='帖子处理通知',
                content=f'管理员【{admin_name}】已封禁你的帖子《{post.title or "未命名帖子"}》。帖子内容：{deleted_content or "(无正文)"}',
            )
        return JsonResponse({'success': True})
    return JsonResponse({'error': 'method not allowed'}, status=405)

@csrf_exempt
def comment_delete_view(request, post_id, comment_id):
    from .models import Comment
    try:
        comment = Comment.objects.get(id=comment_id, post_id=post_id)
    except Comment.DoesNotExist:
        return JsonResponse({'error': 'comment not found'}, status=404)
    if request.method == 'DELETE':
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'login required'}, status=401)
        if request.user.username != comment.author and not request.user.is_staff:
            return JsonResponse({'error': 'forbidden'}, status=403)
        is_admin_delete_other = request.user.is_staff and request.user.username != comment.author
        comment.is_deleted = True
        comment.deleted_at = timezone.now()
        comment.save(update_fields=['is_deleted', 'deleted_at'])
        if is_admin_delete_other:
            admin_name = _display_name(request.user)
            deleted_content = _preview_text(comment.content, 160)
            _create_system_notification(
                recipient_username=comment.author,
                target_type='comment',
                target_id=comment.id,
                source_post_id=comment.post_id,
                title='发言处理通知',
                content=f'管理员【{admin_name}】已封禁你的发言。发言内容：{deleted_content or "(无正文)"}',
            )
        return JsonResponse({'status': 'deleted'})
    return JsonResponse({'error': 'method not allowed'}, status=405)

@csrf_exempt
def admin_users_view(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method == 'GET':
        from .models import Profile
        profiles = Profile.objects.filter(user__is_staff=False)
        data = [p.to_dict() for p in profiles]
        return JsonResponse({'users': data})
    return JsonResponse({'error': 'method not allowed'}, status=405)

@csrf_exempt
def admin_ban_user_view(request, profile_id):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method == 'POST':
        import json
        from .models import Profile
        data = json.loads(request.body.decode('utf-8') or '{}')
        action = data.get('action')
        try:
            profile = Profile.objects.get(id=profile_id)
            profile.banned = (action == 'ban')
            profile.save()
            return JsonResponse({'success': True, 'banned': profile.banned})
        except Profile.DoesNotExist:
            return JsonResponse({'error': 'Profile not found'}, status=404)
    return JsonResponse({'error': 'method not allowed'}, status=405)

@csrf_exempt
def admin_deleted_posts_view(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method == 'GET':
        import django.utils.timezone as timezone
        from datetime import timedelta
        thirty_days_ago = timezone.now() - timedelta(days=30)
        from .models import Post, Comment

        post_qs = Post.objects.filter(is_deleted=True, deleted_at__gte=thirty_days_ago).order_by('-deleted_at')
        comment_qs = Comment.objects.filter(is_deleted=True, deleted_at__gte=thirty_days_ago).order_by('-deleted_at')

        posts = []
        for p in post_qs:
            posts.append({
                'id': p.id,
                'title': p.title,
                'author': p.author,
                'deleted_at': p.deleted_at.isoformat() if p.deleted_at else None,
            })

        comments = []
        for c in comment_qs:
            comments.append({
                'id': c.id,
                'post_id': c.post_id,
                'parent_comment_id': c.parent_comment_id,
                'content': c.content,
                'author': c.author,
                'deleted_at': c.deleted_at.isoformat() if c.deleted_at else None,
            })

        return JsonResponse({'posts': posts, 'comments': comments})
    return JsonResponse({'error': 'method not allowed'}, status=405)

@csrf_exempt
def admin_restore_post_view(request, post_id):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method == 'POST':
        from .models import Post
        try:
            post = Post.objects.get(id=post_id)
            if not post.is_deleted:
                return JsonResponse({'error': 'post is not deleted'}, status=400)
            if not post.deleted_at or post.deleted_at < timezone.now() - timedelta(days=30):
                return JsonResponse({'error': '只能恢复30天内删除的帖子'}, status=400)
            admin_name = _display_name(request.user)
            restored_content = _preview_text(post.content, 160)
            post.is_deleted = False
            post.deleted_at = None
            post.save()
            if request.user.username != post.author:
                _create_system_notification(
                    recipient_username=post.author,
                    target_type='post',
                    target_id=post.id,
                    source_post_id=post.id,
                    title='帖子恢复通知',
                    content=f'管理员【{admin_name}】已恢复你的帖子《{post.title or "未命名帖子"}》。帖子内容：{restored_content or "(无正文)"}',
                )
            return JsonResponse({'success': True})
        except Post.DoesNotExist:
            return JsonResponse({'error': 'Post not found'}, status=404)
    return JsonResponse({'error': 'method not allowed'}, status=405)


@csrf_exempt
def admin_restore_comment_view(request, comment_id):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method == 'POST':
        from .models import Comment
        try:
            comment = Comment.objects.get(id=comment_id)
            if not comment.is_deleted:
                return JsonResponse({'error': 'comment is not deleted'}, status=400)
            if not comment.deleted_at or comment.deleted_at < timezone.now() - timedelta(days=30):
                return JsonResponse({'error': '只能恢复30天内删除的回复'}, status=400)
            admin_name = _display_name(request.user)
            restored_content = _preview_text(comment.content, 160)
            comment.is_deleted = False
            comment.deleted_at = None
            comment.save(update_fields=['is_deleted', 'deleted_at'])
            if request.user.username != comment.author:
                _create_system_notification(
                    recipient_username=comment.author,
                    target_type='comment',
                    target_id=comment.id,
                    source_post_id=comment.post_id,
                    title='发言恢复通知',
                    content=f'管理员【{admin_name}】已恢复你的发言。发言内容：{restored_content or "(无正文)"}',
                )
            return JsonResponse({'success': True})
        except Comment.DoesNotExist:
            return JsonResponse({'error': 'Comment not found'}, status=404)
    return JsonResponse({'error': 'method not allowed'}, status=405)


@csrf_exempt
def admin_ai_ban_list_view(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method != 'GET':
        return JsonResponse({'error': 'method not allowed'}, status=405)

    posts_qs = Post.objects.filter(
        is_deleted=False,
        ai_moderation_status='flagged',
    ).order_by('-ai_moderation_flagged_at', '-id')

    comments_qs = Comment.objects.filter(
        is_deleted=False,
        post__is_deleted=False,
        ai_moderation_status='flagged',
    ).order_by('-ai_moderation_flagged_at', '-id')

    posts = [
        {
            'id': p.id,
            'title': p.title,
            'content': p.content,
            'author': p.author,
            'reason': p.ai_moderation_reason,
            'flagged_at': p.ai_moderation_flagged_at.isoformat() if p.ai_moderation_flagged_at else None,
            'created_at': p.created_at.isoformat() if p.created_at else None,
        }
        for p in posts_qs
    ]

    comments = [
        {
            'id': c.id,
            'post_id': c.post_id,
            'parent_comment_id': c.parent_comment_id,
            'content': c.content,
            'author': c.author,
            'reason': c.ai_moderation_reason,
            'flagged_at': c.ai_moderation_flagged_at.isoformat() if c.ai_moderation_flagged_at else None,
            'created_at': c.created_at.isoformat() if c.created_at else None,
        }
        for c in comments_qs
    ]

    return JsonResponse({'posts': posts, 'comments': comments})


@csrf_exempt
def admin_ai_restore_comment_view(request, comment_id):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)

    try:
        comment = Comment.objects.get(id=comment_id, is_deleted=False)
    except Comment.DoesNotExist:
        return JsonResponse({'error': 'comment not found'}, status=404)

    if comment.ai_moderation_status != 'flagged':
        return JsonResponse({'error': 'comment is not ai hidden'}, status=400)

    comment.ai_moderation_status = 'safe'
    comment.ai_moderation_reason = ''
    comment.ai_moderation_checked_at = timezone.now()
    comment.ai_moderation_flagged_at = None
    comment.save(update_fields=['ai_moderation_status', 'ai_moderation_reason', 'ai_moderation_checked_at', 'ai_moderation_flagged_at'])

    return JsonResponse({'success': True})


@csrf_exempt
def admin_ai_delete_comment_view(request, comment_id):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)

    try:
        comment = Comment.objects.get(id=comment_id, is_deleted=False)
    except Comment.DoesNotExist:
        return JsonResponse({'error': 'comment not found'}, status=404)

    comment.is_deleted = True
    comment.deleted_at = timezone.now()
    comment.ai_moderation_status = 'safe'
    comment.ai_moderation_reason = ''
    comment.ai_moderation_checked_at = timezone.now()
    comment.ai_moderation_flagged_at = None
    comment.save(update_fields=[
        'is_deleted',
        'deleted_at',
        'ai_moderation_status',
        'ai_moderation_reason',
        'ai_moderation_checked_at',
        'ai_moderation_flagged_at',
    ])

    return JsonResponse({'success': True})


def admin_scraper_logs_view(request):
    if not (request.user.is_authenticated and request.user.is_staff):
        return JsonResponse({'error': 'admin required'}, status=401)
    
    from .models import ScraperRun
    logs = ScraperRun.objects.order_by('-start_time')[:50]
    return JsonResponse({'logs': [log.to_dict() for log in logs]})


def admin_scraper_logs_export_view(request):
    if not (request.user.is_authenticated and request.user.is_staff):
        return JsonResponse({'error': 'admin required'}, status=401)
    if request.method != 'GET':
        return JsonResponse({'error': 'GET required'}, status=405)

    from .models import ScraperRun

    log_id = request.GET.get('id')
    logs_qs = ScraperRun.objects.order_by('-start_time')
    if log_id:
        logs_qs = logs_qs.filter(id=log_id)

    logs = list(logs_qs[:200])

    now_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    if log_id:
        filename = f"scraper_log_{log_id}_{now_str}.txt"
    else:
        filename = f"scraper_logs_{now_str}.txt"

    lines = ["===== 爬虫历史日志导出 =====", f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]
    if not logs:
        lines.append("无日志记录")
    else:
        for log in logs:
            lines.append(f"--- 任务ID: {log.id} ---")
            lines.append(f"状态: {log.status}")
            lines.append(f"开始时间: {log.start_time.strftime('%Y-%m-%d %H:%M:%S') if log.start_time else '-'}")
            lines.append(f"结束时间: {log.end_time.strftime('%Y-%m-%d %H:%M:%S') if log.end_time else '-'}")
            lines.append("日志内容:")
            lines.append(log.log_text.strip() if log.log_text else "(无日志输出)")
            lines.append("")

    content = "\n".join(lines)
    response = HttpResponse(content, content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response



@csrf_exempt
def format_table_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        data = {}

    content = data.get('content', '')
    if not content:
        return JsonResponse({'error': 'content is empty'}, status=400)

    configs = list(ApiConfig.objects.filter(is_active=True).order_by('-is_primary', 'id'))
    if not configs:
        return JsonResponse({'error': '未配置可用的API'}, status=500)

    system_prompt = """你是一个数据助理。请将下面用户提供的电脑配置推荐文本中的核心硬件配置提取出来，并使用 Markdown 表格格式进行排版。
表格应该包括：配件类型（如 CPU, 显卡, 主板等）, 具体型号, 预估价格（如果是已知价格则填入，或标明AI预估）。
只输出 Markdown 表格文本本身以及末尾的总价，不要说任何开场白或多余解释。"""

    api_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content}
    ]

    for config in configs:
        try:
            ok, reply = _call_chat_api(config, api_messages, temperature=0.1, timeout=20)
            if ok:
                return JsonResponse({'status': 'ok', 'table_content': reply})
        except Exception:
            pass

    return JsonResponse({'error': 'API格式化数据失败'}, status=500)


@csrf_exempt
def format_table_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        data = {}

    content = data.get('content', '')
    if not content:
        return JsonResponse({'error': 'content is empty'}, status=400)

    configs = list(ApiConfig.objects.filter(is_active=True).order_by('-is_primary', 'id'))
    if not configs:
        return JsonResponse({'error': '未配置可用的API'}, status=500)

    system_prompt = """你是一个数据助理。请将下面用户提供的电脑配置推荐文本中的核心硬件配置提取出来，并使用 Markdown 表格格式进行排版。
表格应该包括：配件类型（如 CPU, 显卡, 主板等）, 具体型号, 预估价格（如果是已知价格则填入，或标明AI预估）。
只输出 Markdown 表格文本本身以及末尾的总价，不要说任何开场白或多余解释。"""

    api_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content}
    ]

    for config in configs:
        try:
            ok, reply = _call_chat_api(config, api_messages, temperature=0.1, timeout=20)
            if ok:
                return JsonResponse({'status': 'ok', 'table_content': reply})
        except Exception:
            pass

    return JsonResponse({'error': 'API格式化数据失败'}, status=500)


def _create_like_notification(recipient_username, actor_user, target_type, target_id, source_post_id=None):
    if not recipient_username:
        return
    try:
        recipient = User.objects.get(username=recipient_username)
    except User.DoesNotExist:
        return

    if recipient.id == actor_user.id:
        return

    LikeNotification.objects.create(
        recipient=recipient,
        actor=actor_user,
        target_type=target_type,
        target_id=target_id,
        source_post_id=source_post_id,
        is_read=False,
    )


def _create_reply_notification(recipient_username, actor_user, target_type, target_id, source_post_id=None, reply_comment_id=None):
    if not recipient_username:
        return
    try:
        recipient = User.objects.get(username=recipient_username)
    except User.DoesNotExist:
        return

    if recipient.id == actor_user.id:
        return

    ReplyNotification.objects.create(
        recipient=recipient,
        actor=actor_user,
        target_type=target_type,
        target_id=target_id,
        source_post_id=source_post_id,
        reply_comment_id=reply_comment_id,
        is_read=False,
    )


def _create_system_notification(recipient_username, target_type, target_id, source_post_id=None, title='系统通知', content=''):
    if not recipient_username:
        return
    try:
        recipient = User.objects.get(username=recipient_username)
    except User.DoesNotExist:
        return

    SystemNotification.objects.create(
        recipient=recipient,
        target_type=target_type,
        target_id=target_id,
        source_post_id=source_post_id,
        title=title,
        content=content,
        is_read=False,
    )


def _display_name(user):
    if not user:
        return '管理员'
    try:
        if hasattr(user, 'profile') and user.profile.nickname:
            return user.profile.nickname
    except Exception:
        pass
    return user.username or '管理员'


def _preview_text(text, limit=120):
    if not text:
        return ''
    s = str(text).strip()
    if len(s) <= limit:
        return s
    return s[:limit] + '...'


@csrf_exempt
def messages_unread_counts_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': '未登录'}, status=401)
    likes_unread = LikeNotification.objects.filter(recipient=request.user, is_read=False).count()
    replies_unread = ReplyNotification.objects.filter(recipient=request.user, is_read=False).count()
    system_unread = SystemNotification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({'likes_unread': likes_unread, 'replies_unread': replies_unread, 'system_unread': system_unread})


@csrf_exempt
def messages_likes_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': '未登录'}, status=401)
    if request.method != 'GET':
        return JsonResponse({'error': 'GET required'}, status=405)

    notifications = LikeNotification.objects.filter(recipient=request.user).select_related('actor').order_by('-id')[:100]
    out = []
    for n in notifications:
        actor_name = n.actor.username
        try:
            if hasattr(n.actor, 'profile') and n.actor.profile.nickname:
                actor_name = n.actor.profile.nickname
        except Exception:
            pass

        target_text = ''
        if n.target_type == 'post':
            try:
                p = Post.objects.get(id=n.target_id)
                target_text = p.title or p.content[:60]
            except Post.DoesNotExist:
                target_text = '[帖子已删除]'
        elif n.target_type == 'comment':
            try:
                c = Comment.objects.get(id=n.target_id)
                target_text = c.content[:80]
            except Comment.DoesNotExist:
                target_text = '[评论已删除]'

        out.append({
            'id': n.id,
            'actor_name': actor_name,
            'target_type': n.target_type,
            'target_id': n.target_id,
            'source_post_id': n.source_post_id,
            'target_text': target_text,
            'is_read': n.is_read,
            'created_at': n.created_at.isoformat(),
        })

    unread = LikeNotification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({'likes': out, 'likes_unread': unread})


@csrf_exempt
def messages_likes_mark_read_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': '未登录'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    updated = LikeNotification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'status': 'ok', 'updated': updated})


@csrf_exempt
def messages_replies_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': '未登录'}, status=401)
    if request.method != 'GET':
        return JsonResponse({'error': 'GET required'}, status=405)

    notifications = ReplyNotification.objects.filter(recipient=request.user).select_related('actor').order_by('-id')[:100]
    out = []
    for n in notifications:
        actor_name = n.actor.username
        try:
            if hasattr(n.actor, 'profile') and n.actor.profile.nickname:
                actor_name = n.actor.profile.nickname
        except Exception:
            pass

        target_text = ''
        if n.target_type == 'post':
            try:
                p = Post.objects.get(id=n.target_id)
                target_text = p.title or (p.content[:80] if p.content else '')
            except Post.DoesNotExist:
                target_text = '[帖子已删除]'
        elif n.target_type == 'comment':
            try:
                c = Comment.objects.get(id=n.target_id)
                target_text = c.content[:80] if c.content else ''
            except Comment.DoesNotExist:
                target_text = '[评论已删除]'

        reply_text = ''
        if n.reply_comment_id:
            try:
                rc = Comment.objects.get(id=n.reply_comment_id)
                reply_text = rc.content[:100] if rc.content else ''
            except Comment.DoesNotExist:
                reply_text = '[回复已删除]'

        out.append({
            'id': n.id,
            'actor_name': actor_name,
            'target_type': n.target_type,
            'target_id': n.target_id,
            'source_post_id': n.source_post_id,
            'reply_comment_id': n.reply_comment_id,
            'target_text': target_text,
            'reply_text': reply_text,
            'is_read': n.is_read,
            'created_at': n.created_at.isoformat(),
        })

    unread = ReplyNotification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({'replies': out, 'replies_unread': unread})


@csrf_exempt
def messages_replies_mark_read_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': '未登录'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    updated = ReplyNotification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'status': 'ok', 'updated': updated})


@csrf_exempt
def messages_system_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': '未登录'}, status=401)
    if request.method != 'GET':
        return JsonResponse({'error': 'GET required'}, status=405)

    notifications = SystemNotification.objects.filter(recipient=request.user).order_by('-id')[:100]
    out = []
    for n in notifications:
        out.append({
            'id': n.id,
            'title': n.title,
            'content': n.content,
            'target_type': n.target_type,
            'target_id': n.target_id,
            'source_post_id': n.source_post_id,
            'is_read': n.is_read,
            'created_at': n.created_at.isoformat(),
        })

    unread = SystemNotification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({'system': out, 'system_unread': unread})


@csrf_exempt
def messages_system_mark_read_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': '未登录'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    updated = SystemNotification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'status': 'ok', 'updated': updated})


@csrf_exempt
def like_post_view(request, post_id):
    if request.method == 'POST':
        if not request.user.is_authenticated:
            return JsonResponse({'error': '未登录'}, status=401)
        try:
            post = Post.objects.get(id=post_id)
            if request.user in post.likes.all():
                post.likes.remove(request.user)
                liked = False
            else:
                post.likes.add(request.user)
                liked = True
                _create_like_notification(
                    recipient_username=post.author,
                    actor_user=request.user,
                    target_type='post',
                    target_id=post.id,
                    source_post_id=post.id,
                )
            return JsonResponse({'message': '操作成功', 'liked': liked, 'likes_count': post.likes.count()})
        except Post.DoesNotExist:
            return JsonResponse({'error': '帖子不存在'}, status=404)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
def like_comment_view(request, comment_id):
    if request.method == 'POST':
        if not request.user.is_authenticated:
            return JsonResponse({'error': '未登录'}, status=401)
        try:
            comment = Comment.objects.get(id=comment_id)
            if request.user in comment.likes.all():
                comment.likes.remove(request.user)
                liked = False
            else:
                comment.likes.add(request.user)
                liked = True
                _create_like_notification(
                    recipient_username=comment.author,
                    actor_user=request.user,
                    target_type='comment',
                    target_id=comment.id,
                    source_post_id=comment.post_id,
                )
            return JsonResponse({'message': '操作成功', 'liked': liked, 'likes_count': comment.likes.count()})
        except Comment.DoesNotExist:
            return JsonResponse({'error': '评论不存在'}, status=404)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
def report_view(request):
    if request.method == 'POST':
        if not request.user.is_authenticated:
            return JsonResponse({'error': '未登录'}, status=401)
        try:
            data = json.loads(request.body.decode('utf-8'))
            report_type = data.get('type')
            target_id = data.get('id')
            if report_type not in ['post', 'comment'] or not target_id:
                return JsonResponse({'error': '参数错误'}, status=400)
            from .models import Report
            Report.objects.create(
                report_type=report_type, 
                target_id=target_id, 
                reporter=request.user,
                handled=False
            )
            return JsonResponse({'message': '举报成功'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'method not allowed'}, status=405)

def admin_reports_view(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method == 'GET':
        from .models import Report, Post, Comment
        reports = Report.objects.filter(handled=False).order_by('-id')
        out = []
        for r in reports:
            content = ""
            author = ""
            if r.report_type == 'post':
                try:
                    p = Post.objects.get(id=r.target_id)
                    content = p.title + " - " + p.content
                    author = p.author
                except Post.DoesNotExist:
                    content = "[已删除]"
            else:
                try:
                    c = Comment.objects.get(id=r.target_id)
                    content = c.content
                    author = c.author
                except Comment.DoesNotExist:
                    content = "[已删除]"
            
            out.append({
                'id': r.id,
                'type': "动态" if r.report_type == 'post' else "评论",
                'target_id': r.target_id,
                'reporter': r.reporter.username,
                'content': content,
                'author': author,
                'created_at': r.created_at.isoformat()
            })
        return JsonResponse({'reports': out})
    return JsonResponse({'error': 'method not allowed'}, status=405)

@csrf_exempt
def admin_handle_report_view(request, report_id):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            action = data.get('action') # 'delete' or 'ignore'
            from .models import Report, Post, Comment
            report = Report.objects.get(id=report_id)
            
            if action == 'delete':
                admin_name = _display_name(request.user)
                if report.report_type == 'post':
                    try:
                        p = Post.objects.get(id=report.target_id)
                        if not p.is_deleted:
                            deleted_content = _preview_text(p.content, 160)
                            p.is_deleted = True
                            import django.utils.timezone as timezone
                            p.deleted_at = timezone.now()
                            p.save()
                            _create_system_notification(
                                recipient_username=p.author,
                                target_type='post',
                                target_id=p.id,
                                source_post_id=p.id,
                                title='帖子处理通知',
                                content=f'管理员【{admin_name}】因违规已封禁你的帖子《{p.title or "未命名帖子"}》。帖子内容：{deleted_content or "(无正文)"}',
                            )
                    except Post.DoesNotExist:
                        pass
                else:
                    try:
                        c = Comment.objects.get(id=report.target_id)
                        if not c.is_deleted:
                            deleted_content = _preview_text(c.content, 160)
                            c.is_deleted = True
                            c.deleted_at = timezone.now()
                            c.save(update_fields=['is_deleted', 'deleted_at'])
                            _create_system_notification(
                                recipient_username=c.author,
                                target_type='comment',
                                target_id=c.id,
                                source_post_id=c.post_id,
                                title='发言处理通知',
                                content=f'管理员【{admin_name}】因违规已封禁你的发言。发言内容：{deleted_content or "(无正文)"}',
                            )
                    except Comment.DoesNotExist:
                        pass
                
                # Mark all pending reports for this target as handled
                Report.objects.filter(report_type=report.report_type, target_id=report.target_id).update(handled=True)
            elif action == 'ignore':
                report.handled = True
                report.save()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'method not allowed'}, status=405)


@csrf_exempt
def admin_schemes_view(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method == 'GET':
        schemes = RecommendedScheme.objects.all().order_by('-created_at')
        return JsonResponse({'status': 'ok', 'data': [s.to_dict() for s in schemes]})
    return JsonResponse({'error': 'method not allowed'}, status=405)

@csrf_exempt
def admin_delete_scheme_view(request, scheme_id):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method in ['POST', 'DELETE']:
        try:
            scheme = RecommendedScheme.objects.get(id=scheme_id)
            scheme.delete()
            return JsonResponse({'status': 'ok'})
        except RecommendedScheme.DoesNotExist:
            return JsonResponse({'error': 'not found'}, status=404)
    return JsonResponse({'error': 'method not allowed'}, status=405)


@csrf_exempt
def admin_weight_adjustments_view(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method != 'GET':
        return JsonResponse({'error': 'method not allowed'}, status=405)

    from .models import Hardware

    limit_raw = request.GET.get('limit', '120')
    try:
        limit = max(1, min(int(limit_raw), 500))
    except Exception:
        limit = 120

    logs = HardwareWeightAdjustmentLog.objects.select_related('hardware').order_by('-id')[:limit]
    top_hardware = Hardware.objects.all().order_by('-recommend_weight', '-id')[:30]

    return JsonResponse({
        'status': 'ok',
        'logs': [x.to_dict() for x in logs],
        'hardware': [
            {
                'id': h.id,
                'name': h.name,
                'model': h.model or '',
                'brand': h.brand or '',
                'recommend_weight': h.recommend_weight,
                'weight_updated_at': h.weight_updated_at.isoformat() if h.weight_updated_at else None,
            }
            for h in top_hardware
        ],
    })

@csrf_exempt
def trigger_daily_clean_view(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    from .task_daily_clean import do_daily_clean
    try:
        do_daily_clean()
        return JsonResponse({'status': 'ok', 'message': '执行成功'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)



@csrf_exempt
def admin_schemes_view(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method == 'GET':
        schemes = RecommendedScheme.objects.all().order_by('-created_at')
        return JsonResponse({'status': 'ok', 'data': [s.to_dict() for s in schemes]})
    return JsonResponse({'error': 'method not allowed'}, status=405)

@csrf_exempt
def admin_delete_scheme_view(request, scheme_id):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method in ['POST', 'DELETE']:
        try:
            scheme = RecommendedScheme.objects.get(id=scheme_id)
            scheme.delete()
            return JsonResponse({'status': 'ok'})
        except RecommendedScheme.DoesNotExist:
            return JsonResponse({'error': 'not found'}, status=404)
    return JsonResponse({'error': 'method not allowed'}, status=405)

@csrf_exempt
def trigger_daily_clean_view(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    from .task_daily_clean import do_daily_clean
    try:
        do_daily_clean()
        return JsonResponse({'status': 'ok', 'message': '执行成功'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

