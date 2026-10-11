import json
import re

from .llm_client import invoke_with_config, normalize_chat_completions_url
from .models import AuditApiConfig


SENSITIVE_AUDIT_PROMPT = (
    "你是论坛内容审核员。请判断文本是否包含敏感、违规、攻击、辱骂、仇恨、色情、暴力、诈骗、违法等不当内容。"
    "只输出JSON，不要输出其他文字。"
    "通过返回：{\"sensitive\": false, \"reason\": \"\"}。"
    "不通过返回：{\"sensitive\": true, \"reason\": \"简要原因\"}。"
)


def _normalize_chat_completions_url(base_url):
    return normalize_chat_completions_url(base_url)


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


def _coerce_sensitive_result(content):
    parsed = _extract_json_from_text(content)
    if isinstance(parsed, dict) and 'sensitive' in parsed:
        sensitive = parsed.get('sensitive', False)
        if isinstance(sensitive, str):
            sensitive = sensitive.strip().lower() in ('true', '1', 'yes', '是', '违规', '敏感')
        reason = str(parsed.get('reason', '') or '').strip()
        return bool(sensitive), reason

    txt = str(content or '').strip().lower()
    if not txt:
        return None

    if '"sensitive": true' in txt or "'sensitive': true" in txt or 'sensitive=true' in txt:
        return True, ''
    if '"sensitive": false' in txt or "'sensitive': false" in txt or 'sensitive=false' in txt:
        return False, ''
    return None


def _call_chat_api(config, messages, timeout=40):
    return invoke_with_config(
        config=config,
        messages=messages,
        temperature=0,
        timeout=timeout,
        max_tokens=120,
    )


def check_text_sensitive(content_text):
    configs = list(AuditApiConfig.objects.filter(is_active=True).order_by('-is_primary', 'id'))
    if not configs:
        return {
            'available': False,
            'sensitive': False,
            'reason': '未配置审核API',
            'used_api': None,
            'errors': [],
        }

    errors = []
    for config in configs:
        ok, content_or_error = _call_chat_api(
            config,
            [
                {'role': 'system', 'content': SENSITIVE_AUDIT_PROMPT},
                {'role': 'user', 'content': str(content_text or '')[:3000]},
            ],
            timeout=35,
        )
        if not ok:
            errors.append(f'[{config.name}] {content_or_error}')
            continue

        parsed = _coerce_sensitive_result(content_or_error)
        if parsed is None:
            errors.append(f'[{config.name}] 审核返回不可解析')
            continue

        sensitive, reason = parsed
        return {
            'available': True,
            'sensitive': bool(sensitive),
            'reason': reason or ('命中敏感内容' if sensitive else ''),
            'used_api': config.name,
            'errors': errors,
        }

    return {
        'available': False,
        'sensitive': False,
        'reason': '审核系统不可用',
        'used_api': None,
        'errors': errors,
    }
