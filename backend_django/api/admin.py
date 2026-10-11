from django.contrib import admin
from .models import Hardware, PriceHistory, Post, Comment

admin.site.register(Hardware)
admin.site.register(PriceHistory)
admin.site.register(Post)
admin.site.register(Comment)
