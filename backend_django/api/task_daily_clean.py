import datetime
import json
import re
from django.utils import timezone
from django.db.models import Count
from django.db.models import Q
from api.llm_client import invoke_with_config
from api.models import (
    Post,
    Comment,
    RecommendedScheme,
    ApiConfig,
    Hardware,
    HardwareWeightAdjustmentLog,
)

def _call_recommend_api(primary_api, messages, temperature=0.1, timeout=30):
    ok, content_or_error = invoke_with_config(
        config=primary_api,
        messages=messages,
        temperature=temperature,
        timeout=timeout,
    )
    if not ok:
        raise RuntimeError(str(content_or_error))
    return str(content_or_error or '')


def _extract_json(text):
    s = str(text or '').strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        pass
    m = re.search(r'\{[\s\S]*\}', s)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _to_confidence(v, default=0.5):
    try:
        x = float(v)
    except Exception:
        return default
    if x < 0:
        return 0.0
    if x > 1:
        return 1.0
    return x


def _compute_delta(sentiment, confidence):
    c = _to_confidence(confidence, default=0.5)
    base = 0.08 * c
    s = str(sentiment or '').strip().lower()
    if s == 'positive':
        return base
    if s == 'negative':
        return -base
    return 0.0


def _clip_weight(w):
    if w < 0.2:
        return 0.2
    if w > 3.0:
        return 3.0
    return w


def _find_hardware_by_mention(mention_text):
    key = str(mention_text or '').strip()
    if not key:
        return None

    exact = Hardware.objects.filter(Q(name__iexact=key) | Q(model__iexact=key)).order_by('-recommend_weight', 'id').first()
    if exact:
        return exact

    fuzzy = Hardware.objects.filter(
        Q(name__icontains=key) | Q(model__icontains=key) | Q(description__icontains=key)
    ).order_by('-recommend_weight', 'id').first()
    return fuzzy


def _adjust_hardware_weights(primary_api, items, today):
    if not items:
        return

    system_prompt = (
        "你是硬件口碑提取助手。请从用户文本中提取被提及的硬件，并判断用户对该硬件的评价倾向。"
        "必须只输出JSON："
        "{\"mentions\":[{\"hardware\":\"硬件名或型号\",\"sentiment\":\"positive|negative|neutral\",\"confidence\":0.0-1.0,\"reason\":\"简短原因\"}]}。"
        "如未提及硬件，则输出 {\"mentions\":[]}。"
    )

    for item in items:
        already_done = HardwareWeightAdjustmentLog.objects.filter(
            source_type=item['type'],
            source_id=item['id'],
            created_at__gte=today,
        ).exists()
        if already_done:
            continue

        try:
            content = _call_recommend_api(
                primary_api,
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": item['text'][:2600]},
                ],
                temperature=0,
                timeout=35,
            )
            data = _extract_json(content)
            if not isinstance(data, dict):
                continue
            mentions = data.get('mentions', [])
            if not isinstance(mentions, list):
                continue

            for m in mentions:
                if not isinstance(m, dict):
                    continue
                mention_text = str(m.get('hardware', '') or '').strip()
                if not mention_text:
                    continue

                hw = _find_hardware_by_mention(mention_text)
                if not hw:
                    continue

                sentiment = str(m.get('sentiment', 'neutral') or 'neutral').strip().lower()
                if sentiment not in ('positive', 'negative', 'neutral'):
                    sentiment = 'neutral'
                confidence = _to_confidence(m.get('confidence', 0.5), default=0.5)
                delta = _compute_delta(sentiment, confidence)
                before = float(hw.recommend_weight or 1.0)
                after = _clip_weight(before + delta)

                hw.recommend_weight = after
                hw.weight_updated_at = timezone.now()
                hw.save(update_fields=['recommend_weight', 'weight_updated_at'])

                HardwareWeightAdjustmentLog.objects.create(
                    hardware=hw,
                    source_type=item['type'],
                    source_id=item['id'],
                    source_excerpt=item['text'][:280],
                    mention_text=mention_text,
                    sentiment=sentiment,
                    confidence=confidence,
                    delta=(after - before),
                    weight_before=before,
                    weight_after=after,
                    reason=str(m.get('reason', '') or '')[:600],
                )
        except Exception as e:
            print(f"Weight adjust failed for {item['type']} {item['id']}: {e}")

def do_daily_clean():
    today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # A. 权重调整：清洗当日全部新增动态/评论
    all_posts = Post.objects.filter(
        created_at__gte=today,
        is_deleted=False
    )
    all_comments = Comment.objects.filter(
        created_at__gte=today,
        is_deleted=False,
        post__is_deleted=False
    )

    all_items = []
    for p in all_posts:
        all_items.append({'id': p.id, 'type': 'post', 'text': f"{p.title or ''}\n{p.content or ''}"})
    for c in all_comments:
        all_items.append({'id': c.id, 'type': 'comment', 'text': c.content or ''})

    # B. 推荐方案提取：继续使用当日高赞内容
    posts = Post.objects.filter(
        created_at__gte=today,
        is_deleted=False
    ).annotate(likes_count=Count('likes')).filter(likes_count__gt=50)

    # 2. Fetch comments from today with likes > 50
    comments = Comment.objects.filter(
        created_at__gte=today,
        is_deleted=False,
        post__is_deleted=False
    ).annotate(likes_count=Count('likes')).filter(likes_count__gt=50)

    # Combine to process
    items = []
    for p in posts:
        items.append({'id': p.id, 'type': 'post', 'text': p.title + '\n' + p.content})
    for c in comments:
        items.append({'id': c.id, 'type': 'comment', 'text': c.content})

    primary_api = ApiConfig.objects.filter(is_active=True, is_primary=True).first()
    if not primary_api:
        return

    system_prompt = """你是一个硬件清洗助理。请判断以下文本是否包含一个完整且合理的电脑硬件配置方案。
如果是，请总结并返回JSON格式，包括 title (方案标题, 例如: 4000元高性价比游戏配置) 和 content (整理好的Markdown表格配置和理由)。
如果不是，或者只是一些只言片语、单个配件解答等，请仅仅返回 {"is_scheme": false} 。
注意：如果是合法配置，必须返回 {"is_scheme": true, "title": "...", "content": "..."}。
不要输出其他内容，必须是合法JSON。"""

    _adjust_hardware_weights(primary_api=primary_api, items=all_items, today=today)

    if not items:
        return

    for item in items:
        # Check if already processed
        if RecommendedScheme.objects.filter(source_type=item['type'], source_id=item['id']).exists():
            continue

        api_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": item['text']}
        ]

        try:
            reply = _call_recommend_api(primary_api, api_messages, temperature=0.1, timeout=30)
            # Clean markdown JSON block if present
            reply = reply.strip()
            if reply.startswith("`json"):
                reply = reply[7:-3].strip()
            elif reply.startswith("`"):
                reply = reply[3:-3].strip()

            data = json.loads(reply)
            if data.get('is_scheme') is True:
                RecommendedScheme.objects.create(
                    title=data.get('title', '社群精选推荐方案'),
                    content=data.get('content', ''),
                    source_type=item['type'],
                    source_id=item['id']
                )
        except Exception as e:
            print(f"Error processing item {item['type']} {item['id']}: {e}")

