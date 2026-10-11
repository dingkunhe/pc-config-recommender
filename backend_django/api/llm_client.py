import os
from urllib.parse import urlparse

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


def normalize_chat_completions_url(base_url):
    """兼容 OpenAI 风格配置：自动补全 chat/completions 路径。"""
    base_url = (base_url or '').strip()
    if not base_url:
        return ''

    if base_url.endswith('/chat/completions') or base_url.endswith('/v1/chat/completions'):
        return base_url

    parsed = urlparse(base_url)
    path = (parsed.path or '').rstrip('/')
    if path in ('', '/', '/v1', '/openai', '/api', '/api/v1'):
        return base_url.rstrip('/') + '/chat/completions'

    return base_url.rstrip('/') + '/chat/completions'


def normalize_openai_base_url(base_url):
    """
    将任意配置（域名、/v1、/chat/completions）转换为 OpenAI/ LangChain 期望的 base_url。
    例如：
    - https://api.xxx.com/v1/chat/completions -> https://api.xxx.com/v1
    - https://api.xxx.com/chat/completions -> https://api.xxx.com
    """
    endpoint = normalize_chat_completions_url(base_url)
    if not endpoint:
        return ''

    parsed = urlparse(endpoint)
    path = (parsed.path or '').rstrip('/')
    if path.endswith('/chat/completions'):
        path = path[: -len('/chat/completions')]

    if not path:
        return f"{parsed.scheme}://{parsed.netloc}"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def _to_lc_messages(messages):
    out = []
    for m in (messages or []):
        role = str((m or {}).get('role', 'user')).strip().lower()
        content = str((m or {}).get('content', '') or '')
        if role == 'system':
            out.append(SystemMessage(content=content))
        elif role == 'assistant':
            out.append(AIMessage(content=content))
        else:
            out.append(HumanMessage(content=content))
    return out


def _extract_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks = []
        for item in content:
            if isinstance(item, dict):
                chunks.append(str(item.get('text', '') or item.get('content', '') or ''))
            else:
                chunks.append(str(item))
        return ''.join(chunks)
    return str(content or '')


def invoke_with_config(config, messages, temperature=0.7, timeout=40, max_tokens=None):
    """
    统一通过 LangChain 发起 LLM 调用。
    返回: (ok: bool, content_or_error: str)
    """
    ChatOpenAI = None
    import_errs = []
    try:
        # 新版本优先
        from langchain_openai import ChatOpenAI as _ChatOpenAI  # type: ignore
        ChatOpenAI = _ChatOpenAI
    except Exception as e:
        import_errs.append(f'langchain_openai: {e}')

    if ChatOpenAI is None:
        try:
            # 兼容旧版本
            from langchain_community.chat_models import ChatOpenAI as _ChatOpenAI  # type: ignore
            ChatOpenAI = _ChatOpenAI
        except Exception as e:
            import_errs.append(f'langchain_community: {e}')

    if ChatOpenAI is None:
        return False, 'LangChain ChatOpenAI 不可用，请安装: pip install langchain-openai openai；详细: ' + ' | '.join(import_errs)

    try:
        base_url = normalize_openai_base_url(getattr(config, 'base_url', ''))
        api_key = getattr(config, 'api_key', '')
        model_name = getattr(config, 'model_name', '')

        if not base_url:
            return False, 'Base URL 不能为空'
        if not api_key:
            return False, 'API Key 不能为空'
        if not model_name:
            return False, '模型名称不能为空'

        model_kwargs = {}
        if max_tokens is not None:
            model_kwargs['max_tokens'] = int(max_tokens)

        # 兼容不同 LangChain/OpenAI 版本参数名
        common = {
            'model_name': model_name,
            'openai_api_key': api_key,
            'openai_api_base': base_url,
            'temperature': temperature,
            'request_timeout': timeout,
            'model_kwargs': model_kwargs,
        }

        # 某些环境变量代理会干扰 SDK，允许通过环境变量显式关闭
        if os.getenv('LLM_DISABLE_PROXY', '0') == '1':
            os.environ.pop('HTTP_PROXY', None)
            os.environ.pop('HTTPS_PROXY', None)

        llm = ChatOpenAI(**common)
        resp = llm.invoke(_to_lc_messages(messages))

        return True, _extract_text(getattr(resp, 'content', ''))
    except Exception as e:
        return False, str(e)
