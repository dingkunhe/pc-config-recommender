from apscheduler.schedulers.background import BackgroundScheduler
from django.conf import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

def daily_cleanup_job():
    from .task_daily_clean import do_daily_clean
    try:
        print("Running daily clean job...")
        do_daily_clean()
    except Exception as e:
        print(f"Daily clean job failed: {str(e)}")


def ai_moderation_job():
    from .ai_moderation import check_text_sensitive
    from .models import Post, Comment

    now = timezone.now()
    batch_size = 120

    post_qs = Post.objects.filter(
        is_deleted=False,
        ai_moderation_status='pending',
    ).order_by('id')[:batch_size]

    for post in post_qs:
        content_text = f"标题：{post.title or ''}\n正文：{post.content or ''}"
        result = check_text_sensitive(content_text)
        if not result.get('available'):
            logger.warning('AI审核任务中断（帖子）：%s', '; '.join(result.get('errors', [])[:2]))
            break

        post.ai_moderation_checked_at = now
        if result.get('sensitive'):
            post.ai_moderation_status = 'flagged'
            post.ai_moderation_reason = str(result.get('reason') or '命中敏感内容')
            post.ai_moderation_flagged_at = now
        else:
            post.ai_moderation_status = 'safe'
            post.ai_moderation_reason = ''
            post.ai_moderation_flagged_at = None
        post.save(update_fields=['ai_moderation_status', 'ai_moderation_reason', 'ai_moderation_checked_at', 'ai_moderation_flagged_at'])

    comment_qs = Comment.objects.filter(
        is_deleted=False,
        post__is_deleted=False,
        ai_moderation_status='pending',
    ).order_by('id')[:batch_size]

    for comment in comment_qs:
        content_text = f"评论：{comment.content or ''}"
        result = check_text_sensitive(content_text)
        if not result.get('available'):
            logger.warning('AI审核任务中断（评论）：%s', '; '.join(result.get('errors', [])[:2]))
            break

        comment.ai_moderation_checked_at = now
        if result.get('sensitive'):
            comment.ai_moderation_status = 'flagged'
            comment.ai_moderation_reason = str(result.get('reason') or '命中敏感内容')
            comment.ai_moderation_flagged_at = now
        else:
            comment.ai_moderation_status = 'safe'
            comment.ai_moderation_reason = ''
            comment.ai_moderation_flagged_at = None
        comment.save(update_fields=['ai_moderation_status', 'ai_moderation_reason', 'ai_moderation_checked_at', 'ai_moderation_flagged_at'])

def start_scheduler():
    scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)
    scheduler.add_job(daily_cleanup_job, 'cron', hour=23, minute=0, id='daily_cleanup_job', replace_existing=True)
    scheduler.add_job(ai_moderation_job, 'interval', hours=1, id='ai_moderation_job', replace_existing=True)
    scheduler.start()
