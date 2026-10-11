from django.db import models


# 硬件基础信息模型，用于存储硬件名称、类别、品牌、型号、描述和推荐权重。
class Hardware(models.Model):
    CATEGORY_CHOICES = (
        ('cpu', 'CPU'),
        ('gpu', '显卡'),
        ('motherboard', '主板'),
        ('memory', '内存'),
        ('storage', '硬盘'),
        ('psu', '电源'),
        ('case', '机箱'),
        ('cooler', '散热器'),
        ('laptop', '笔记本电脑'),
        ('monitor', '显示器'),
        ('keyboard', '键盘'),
        ('mouse', '鼠标'),
        ('headphone', '耳机'),
        ('speaker', '音箱'),
        ('other', '其他'),
    )

    name = models.CharField(max_length=255)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='other', db_index=True)
    brand = models.CharField(max_length=100, blank=True, default='')
    model = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True)
    recommend_weight = models.FloatField(default=1.0, db_index=True)
    weight_updated_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.model})"


# 硬件价格历史模型，用于记录某个硬件在不同时间点的价格。
class PriceHistory(models.Model):
    hardware = models.ForeignKey(Hardware, on_delete=models.CASCADE)
    date = models.CharField(max_length=50)
    price = models.FloatField()


# 帖子模型，用于存储社区动态、问答内容和系统通知类帖子。
class Post(models.Model):
    BOARD_CHOICES = (
        ('square', '交流广场'),
        ('qa', 'Q&A'),
        ('system', '系统通知'),
    )

    title = models.CharField(max_length=255)
    content = models.TextField(blank=True)
    author = models.CharField(max_length=100, default='anonymous')
    board = models.CharField(max_length=20, choices=BOARD_CHOICES, default='square')
    created_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    ai_moderation_status = models.CharField(max_length=20, default='pending', db_index=True)
    ai_moderation_reason = models.TextField(blank=True, default='')
    ai_moderation_checked_at = models.DateTimeField(null=True, blank=True)
    ai_moderation_flagged_at = models.DateTimeField(null=True, blank=True)
    likes = models.ManyToManyField("auth.User", related_name="liked_posts", blank=True)


# 评论模型，用于存储帖子评论及评论回复关系。
class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    parent_comment = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='child_comments')
    content = models.TextField()
    author = models.CharField(max_length=100, default='anonymous')
    created_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    ai_moderation_status = models.CharField(max_length=20, default='pending', db_index=True)
    ai_moderation_reason = models.TextField(blank=True, default='')
    ai_moderation_checked_at = models.DateTimeField(null=True, blank=True)
    ai_moderation_flagged_at = models.DateTimeField(null=True, blank=True)
    likes = models.ManyToManyField("auth.User", related_name="liked_comments", blank=True)


# 帖子图片模型，用于保存帖子上传的图片文件。
class PostImage(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='images')
    file = models.FileField(upload_to='posts/images/%Y/%m/')
    uploaded_at = models.DateTimeField(auto_now_add=True)


# 帖子附件模型，用于保存帖子上传的非图片附件。
class PostAttachment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='posts/attachments/%Y/%m/')
    uploaded_at = models.DateTimeField(auto_now_add=True)


# 评论图片模型，用于保存评论上传的图片文件。
class CommentImage(models.Model):
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='images')
    file = models.FileField(upload_to='comments/images/%Y/%m/')
    uploaded_at = models.DateTimeField(auto_now_add=True)


# 评论附件模型，用于保存评论上传的非图片附件。
class CommentAttachment(models.Model):
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='comments/attachments/%Y/%m/')
    uploaded_at = models.DateTimeField(auto_now_add=True)


# 点赞通知模型，用于通知用户其帖子或评论被点赞。
class LikeNotification(models.Model):
    TARGET_TYPES = (
        ('post', 'Post'),
        ('comment', 'Comment'),
    )

    recipient = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='like_notifications')
    actor = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='sent_like_notifications')
    target_type = models.CharField(max_length=20, choices=TARGET_TYPES)
    target_id = models.IntegerField()
    source_post_id = models.IntegerField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


# 回复通知模型，用于通知用户其帖子或评论收到了回复。
class ReplyNotification(models.Model):
    TARGET_TYPES = (
        ('post', 'Post'),
        ('comment', 'Comment'),
    )

    recipient = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='reply_notifications')
    actor = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='sent_reply_notifications')
    target_type = models.CharField(max_length=20, choices=TARGET_TYPES)
    target_id = models.IntegerField()
    source_post_id = models.IntegerField(null=True, blank=True)
    reply_comment_id = models.IntegerField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


# 系统通知模型，用于向用户发送审核、处理结果等系统消息。
class SystemNotification(models.Model):
    TARGET_TYPES = (
        ('post', 'Post'),
        ('comment', 'Comment'),
    )

    recipient = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='system_notifications')
    target_type = models.CharField(max_length=20, choices=TARGET_TYPES)
    target_id = models.IntegerField()
    source_post_id = models.IntegerField(null=True, blank=True)
    title = models.CharField(max_length=255, default='系统通知')
    content = models.TextField(blank=True, default='')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


# 用户资料模型，用于扩展 Django 用户的昵称、头像、联系方式等信息。
class Profile(models.Model):
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE)
    nickname = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.CharField(max_length=255, blank=True)
    avatar = models.FileField(upload_to='avatars/%Y/%m/', blank=True, null=True)
    banned = models.BooleanField(default=False)

    def to_dict(self):
        return {
            'id': self.user.id,
            'username': self.user.username,
            'email': self.user.email,
            'nickname': self.nickname,
            'phone': self.phone,
            'address': self.address,
            'avatar_url': self.avatar.url if self.avatar else '',
            'is_staff': self.user.is_staff,
            'banned': self.banned,
        }


# 推荐大模型接口配置模型，用于保存推荐/问答链路使用的 API 参数。
class ApiConfig(models.Model):
    name = models.CharField(max_length=100)
    api_key = models.CharField(max_length=255)
    model_name = models.CharField(max_length=100)
    base_url = models.CharField(max_length=255, default='https://api.siliconflow.cn/v1/chat/completions')
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'api_key': self.api_key,
            'model_name': self.model_name,
            'base_url': self.base_url,
            'is_primary': self.is_primary,
            'is_active': self.is_active,
        }


# 审核大模型接口配置模型，用于保存内容审核链路使用的 API 参数。
class AuditApiConfig(models.Model):
    name = models.CharField(max_length=100)
    api_key = models.CharField(max_length=255)
    model_name = models.CharField(max_length=100)
    base_url = models.CharField(max_length=255, default='https://api.siliconflow.cn/v1/chat/completions')
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'api_key': self.api_key,
            'model_name': self.model_name,
            'base_url': self.base_url,
            'is_primary': self.is_primary,
            'is_active': self.is_active,
        }


# 提示词配置模型，用于集中存储推荐和审核功能的系统提示词。
class PromptConfig(models.Model):
    recommend_prompt = models.TextField(blank=True, default='')
    audit_prompt = models.TextField(blank=True, default='')
    rag_top_k_per_category = models.PositiveIntegerField(default=5)
    updated_at = models.DateTimeField(auto_now=True)

    def to_dict(self):
        return {
            'id': self.id,
            'recommend_prompt': self.recommend_prompt,
            'audit_prompt': self.audit_prompt,
            'rag_top_k_per_category': self.rag_top_k_per_category,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else '',
        }


# 对话会话模型，用于记录用户与智能助手的一次会话。
class ChatSession(models.Model):
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, null=True, blank=True)
    session_key = models.CharField(max_length=100, null=True, blank=True)
    title = models.CharField(max_length=255, default='新对话')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }


# 对话消息模型，用于记录会话中的每一条用户或助手消息。
class ChatMessage(models.Model):
    session = models.ForeignKey(ChatSession, related_name='messages', on_delete=models.CASCADE)
    role = models.CharField(max_length=50)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def to_dict(self):
        return {
            'id': self.id,
            'role': self.role,
            'content': self.content
        }


# 爬虫运行记录模型，用于保存一次爬虫任务的开始时间、结束时间和日志。
class ScraperRun(models.Model):
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=50, default='running')
    log_text = models.TextField(blank=True)

    def to_dict(self):
        return {
            'id': self.id,
            'start_time': self.start_time.strftime('%Y-%m-%d %H:%M:%S') if self.start_time else '',
            'end_time': self.end_time.strftime('%Y-%m-%d %H:%M:%S') if self.end_time else None,
            'status': self.status,
            'log_text': self.log_text
        }


# 举报模型，用于记录用户对帖子或评论的举报信息。
class Report(models.Model):
    REPORT_TYPES = (
        ('post', 'Post'),
        ('comment', 'Comment'),
    )
    report_type = models.CharField(max_length=10, choices=REPORT_TYPES)
    target_id = models.IntegerField()
    reporter = models.ForeignKey("auth.User", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    handled = models.BooleanField(default=False)


# 推荐方案模型，用于保存从高质量帖子或评论中提取出的装机方案。
class RecommendedScheme(models.Model):
    title = models.CharField(max_length=255, blank=True)
    content = models.TextField()
    source_type = models.CharField(max_length=10) # 'post' or 'comment'
    source_id = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'source_type': self.source_type,
            'source_id': self.source_id,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }


# 硬件权重调整日志模型，用于记录帖子/评论对硬件推荐权重的影响过程。
class HardwareWeightAdjustmentLog(models.Model):
    SENTIMENT_CHOICES = (
        ('positive', 'positive'),
        ('negative', 'negative'),
        ('neutral', 'neutral'),
    )
    SOURCE_TYPES = (
        ('post', 'post'),
        ('comment', 'comment'),
    )

    hardware = models.ForeignKey(Hardware, on_delete=models.CASCADE, related_name='weight_adjust_logs')
    source_type = models.CharField(max_length=10, choices=SOURCE_TYPES)
    source_id = models.IntegerField(db_index=True)
    source_excerpt = models.TextField(blank=True, default='')
    mention_text = models.CharField(max_length=255, blank=True, default='')
    sentiment = models.CharField(max_length=20, choices=SENTIMENT_CHOICES, default='neutral')
    confidence = models.FloatField(default=0.5)
    delta = models.FloatField(default=0.0)
    weight_before = models.FloatField(default=1.0)
    weight_after = models.FloatField(default=1.0)
    reason = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def to_dict(self):
        return {
            'id': self.id,
            'hardware_id': self.hardware_id,
            'hardware_name': self.hardware.name,
            'hardware_model': self.hardware.model or '',
            'source_type': self.source_type,
            'source_id': self.source_id,
            'source_excerpt': self.source_excerpt,
            'mention_text': self.mention_text,
            'sentiment': self.sentiment,
            'confidence': self.confidence,
            'delta': self.delta,
            'weight_before': self.weight_before,
            'weight_after': self.weight_after,
            'reason': self.reason,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }
