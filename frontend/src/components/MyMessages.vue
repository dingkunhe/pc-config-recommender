<template>
  <div class="messages-page">
    <div class="messages-header">
      <h3>我的消息</h3>
    </div>

    <div class="tabs">
      <button :class="{ active: activeTab === 'likes' }" @click="activeTab = 'likes'">
        收到点赞
        <span v-if="message.likesUnread > 0" class="alert-icon">!</span>
      </button>
      <button :class="{ active: activeTab === 'system' }" @click="activeTab = 'system'">
        系统通知
        <span v-if="message.systemUnread > 0" class="alert-icon">!</span>
      </button>
      <button :class="{ active: activeTab === 'replies' }" @click="activeTab = 'replies'">
        收到回复
        <span v-if="(message.repliesUnread + message.systemUnread) > 0" class="alert-icon">!</span>
      </button>
    </div>

    <div class="tab-panel likes-panel" v-if="activeTab === 'likes'">
      <div v-if="likes.length === 0" class="empty">暂无“收到点赞”数据</div>
      <div v-else class="likes-list">
        <div class="like-item clickable-item" v-for="item in likes" :key="item.id" @click="jumpFromLike(item)">
          <div class="like-main">
            <strong>{{ item.actor_name }}</strong>
            <span> 赞了你的{{ item.target_type === 'post' ? '帖子' : '评论' }}</span>
            <span class="dot" v-if="!item.is_read">未读</span>
          </div>
          <div class="like-sub" :title="item.target_text">{{ item.target_text || '内容已删除' }}</div>
          <div class="jump-tip">点击跳转到对应帖子/楼层</div>
          <div class="like-time">{{ formatTime(item.created_at) }}</div>
        </div>
      </div>
    </div>

    <div class="tab-panel" v-if="activeTab === 'system'">
      <div v-if="systemList.length === 0" class="empty">暂无“系统通知”数据</div>
      <div v-else class="likes-list">
        <div class="like-item" v-for="item in systemList" :key="item.id">
          <div class="like-main">
            <strong>{{ item.title || '系统通知' }}</strong>
            <span class="dot" v-if="!item.is_read">未读</span>
          </div>
          <div class="like-sub" :title="item.content">{{ item.content || '无详细内容' }}</div>
          <div class="like-time">{{ formatTime(item.created_at) }}</div>
        </div>
      </div>
    </div>

    <div class="tab-panel replies-panel" v-if="activeTab === 'replies'">
      <div v-if="replies.length === 0" class="empty">暂无“收到回复”数据</div>
      <div v-else class="likes-list">
        <div class="like-item clickable-item" v-for="item in replies" :key="item.id" @click="jumpFromReply(item)">
          <div class="like-main">
            <strong>{{ item.actor_name }}</strong>
            <span> 回复了你的{{ item.target_type === 'post' ? '帖子' : '发言' }}</span>
            <span class="dot" v-if="!item.is_read">未读</span>
          </div>
          <div class="like-sub" :title="item.target_text">原内容：{{ item.target_text || '内容已删除' }}</div>
          <div class="like-sub" :title="item.reply_text">回复内容：{{ item.reply_text || '回复内容为空或已删除' }}</div>
          <div class="jump-tip">点击跳转到对应帖子/楼层</div>
          <div class="like-time">{{ formatTime(item.created_at) }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios'
import { messageState } from '../store.js'

export default {
  emits: ['navigate-forum'],
  data() {
    return {
      activeTab: 'likes',
      likes: [],
      replies: [],
      systemList: [],
      message: messageState
    }
  },
  async mounted() {
    await this.loadLikes()
    await this.markLikesRead()
  },
  watch: {
    async activeTab(val) {
      if (val === 'likes') {
        await this.loadLikes()
        await this.markLikesRead()
      } else if (val === 'system') {
        await this.loadSystem()
        await this.markSystemRead()
      } else if (val === 'replies') {
        await this.loadReplies()
        await this.markRepliesRead()
      }
    }
  },
  methods: {
    emitNavigateTarget(target) {
      if (!target || !target.postId) {
        alert('无法定位对应帖子，可能内容已删除')
        return
      }
      this.$emit('navigate-forum', target)
    },
    jumpFromLike(item) {
      if (!item) return
      if (item.target_type === 'post') {
        this.emitNavigateTarget({ postId: item.target_id })
        return
      }
      this.emitNavigateTarget({ postId: item.source_post_id, commentId: item.target_id })
    },
    jumpFromReply(item) {
      if (!item) return
      if (item.source_post_id && item.reply_comment_id) {
        this.emitNavigateTarget({ postId: item.source_post_id, commentId: item.reply_comment_id })
        return
      }
      if (item.target_type === 'comment') {
        this.emitNavigateTarget({ postId: item.source_post_id, commentId: item.target_id })
        return
      }
      this.emitNavigateTarget({ postId: item.target_id })
    },
    formatTime(iso) {
      if (!iso) return ''
      return new Date(iso).toLocaleString()
    },
    async loadLikes() {
      try {
        const res = await axios.get('/api/messages/likes/', { withCredentials: true })
        this.likes = res.data.likes || []
        this.message.likesUnread = res.data.likes_unread || 0
      } catch (e) {
        this.likes = []
      }
    },
    async markLikesRead() {
      try {
        await axios.post('/api/messages/likes/mark-read/', {}, { withCredentials: true })
        this.message.likesUnread = 0
        this.likes = this.likes.map(i => ({ ...i, is_read: true }))
      } catch (e) {
        // ignore
      }
    },
    async loadReplies() {
      try {
        const res = await axios.get('/api/messages/replies/', { withCredentials: true })
        this.replies = res.data.replies || []
        this.message.repliesUnread = res.data.replies_unread || 0
      } catch (e) {
        this.replies = []
      }
    },
    async markRepliesRead() {
      try {
        await axios.post('/api/messages/replies/mark-read/', {}, { withCredentials: true })
        this.message.repliesUnread = 0
        this.replies = this.replies.map(i => ({ ...i, is_read: true }))
      } catch (e) {
        // ignore
      }
    },
    async loadSystem() {
      try {
        const res = await axios.get('/api/messages/system/', { withCredentials: true })
        this.systemList = res.data.system || []
        this.message.systemUnread = res.data.system_unread || 0
      } catch (e) {
        this.systemList = []
      }
    },
    async markSystemRead() {
      try {
        await axios.post('/api/messages/system/mark-read/', {}, { withCredentials: true })
        this.message.systemUnread = 0
        this.systemList = this.systemList.map(i => ({ ...i, is_read: true }))
      } catch (e) {
        // ignore
      }
    }
  }
}
</script>

<style scoped>
.messages-page {
  background: rgba(255,255,255,.96);
  border: 1px solid #e7edf8;
  border-radius: 16px;
  box-shadow: 0 12px 30px rgba(82,99,130,.1);
  padding: 20px;
}
.messages-header {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 14px;
}
.messages-header h3 {
  margin: 0;
  color: #2f4062;
}
.tabs {
  display: flex;
  gap: 10px;
  border-bottom: 1px solid #e7edf8;
  padding-bottom: 10px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.tabs button {
  border: 1px solid transparent;
  background: #f7f9fe;
  color: #3b4d6d;
  border-radius: 10px;
  padding: 9px 14px;
  cursor: pointer;
  transition: .2s ease;
}
.tabs button.active {
  color: #315ebf;
  border-color: #d8e4ff;
  background: #edf3ff;
  font-weight: 700;
}
.alert-icon {
  margin-left: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #ef4444;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
}
.tab-panel {
  min-height: 260px;
  border: 1px solid #edf1f8;
  border-radius: 12px;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 14px;
}
.likes-panel {
  display: block;
  padding: 14px;
}
.replies-panel {
  display: block;
  padding: 14px;
}
.likes-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.like-item {
  border: 1px solid #e9effa;
  border-radius: 10px;
  padding: 10px 12px;
  background: #fbfdff;
}
.clickable-item {
  cursor: pointer;
  transition: .2s ease;
}
.clickable-item:hover {
  border-color: #cddcfa;
  background: #f3f8ff;
}
.like-main {
  color: #2f4062;
}
.dot {
  margin-left: 8px;
  color: #ef4444;
  font-size: 12px;
}
.like-sub {
  color: #5a6985;
  margin-top: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.like-time {
  color: #8b97ae;
  font-size: 12px;
  margin-top: 6px;
}
.jump-tip {
  color: #3566d6;
  font-size: 12px;
  margin-top: 6px;
}
.empty {
  color: #8b97ae;
}
</style>
