<template>
  <div class="tieba-forum">
    <!-- Thread View -->
    <div v-if="viewingThread" class="thread-view">
      <div class="breadcrumb">
        <a href="#" @click.prevent="closeThread">&lt; 返回列表</a>
      </div>
      <h2 class="thread-title">{{ currentThread.title }}</h2>
      
      <!-- Original Post -->
      <div class="post-item floor">
        <div class="author-info">
          <div class="avatar-placeholder"></div>
          <strong>{{ currentThread.author }}</strong>
        </div>
        <div class="post-body">
          <div class="post-content">{{ currentThread.content }}</div>
          <div class="media-grid" v-if="currentThread.images && currentThread.images.length">
            <a v-for="(img, idx) in currentThread.images" :key="`p-${idx}`" :href="img.url" target="_blank" rel="noopener noreferrer"><img :src="img.url" :alt="img.name"></a>
          </div>
          <div class="attachment-list" v-if="currentThread.attachments && currentThread.attachments.length">
            <a v-for="(att, idx) in currentThread.attachments" :key="`pa-${idx}`" :href="att.url" target="_blank" rel="noopener noreferrer">📎 {{ att.name }}</a>
          </div>
          <div class="post-actions">
            <span class="floor-num">1¥</span>
            <button v-if="isAdmin || isAuthor(currentThread.author)" @click="deleteThread(currentThread.id)" class="del-btn">删除</button>
          </div>
        </div>
      </div>

      <!-- Comments -->
      <div class="post-item floor" v-for="(c, idx) in currentComments" :key="c.id">
        <div class="author-info">
          <div class="avatar-placeholder"></div>
          <strong>{{ c.author }}</strong>
        </div>
        <div class="post-body">
          <div class="post-content">{{ c.content }}</div>
          <div class="media-grid" v-if="c.images && c.images.length">
            <a v-for="(img, idx) in c.images" :key="`c-${c.id}-${idx}`" :href="img.url" target="_blank" rel="noopener noreferrer"><img :src="img.url" :alt="img.name"></a>
          </div>
          <div class="attachment-list" v-if="c.attachments && c.attachments.length">
            <a v-for="(att, idx) in c.attachments" :key="`ca-${c.id}-${idx}`" :href="att.url" target="_blank" rel="noopener noreferrer">📎 {{ att.name }}</a>
          </div>
          <div class="post-actions">
            <span class="floor-num">{{ idx + 2 }}¥</span>
            <button v-if="isAdmin || isAuthor(c.author)" @click="deleteComment(currentThread.id, c.id)" class="del-btn">删除</button>
          </div>
        </div>
      </div>

      <!-- Reply Box -->
      <div class="reply-box" v-if="auth.loggedIn">
        <div class="editor-tools">
          <button type="button" class="tool-btn" @click="showEmoji = !showEmoji">😀 表情</button>
          <label class="tool-btn upload-btn">🖼 图片
            <input type="file" multiple accept="image/*" @change="onCommentImagesSelected" />
          </label>
          <label class="tool-btn upload-btn">📎 附件
            <input type="file" multiple @change="onCommentAttachmentsSelected" />
          </label>
        </div>
        <div v-if="showEmoji" class="emoji-panel">
          <button v-for="e in emojis" :key="e" type="button" @click="commentText += e">{{ e }}</button>
        </div>
        <textarea v-model="commentText" placeholder="发表你的看法..." rows="4"></textarea>
        <div class="selected-files" v-if="commentImages.length || commentAttachments.length">
          <div v-if="commentImagePreviews.length" class="selected-preview-grid">
            <div class="selected-preview-item" v-for="(item, idx) in commentImagePreviews" :key="`cmp-${idx}`">
              <img :src="item.url" :alt="item.file.name" />
              <button type="button" class="remove-file-btn" @click.stop.prevent="removeSelectedFile('image', idx)">×</button>
            </div>
          </div>
          <div v-if="commentAttachments.length" class="selected-attachment-list">
            <div class="attachment-chip" v-for="(f, idx) in commentAttachments" :key="`cma-${idx}`">
              <span>📎 {{ f.name }}</span>
              <button type="button" class="remove-file-btn" @click.stop.prevent="removeSelectedFile('attachment', idx)">×</button>
            </div>
          </div>
        </div>
        <button @click="postComment(currentThread.id)" class="reply-btn">发表回复</button>
      </div>
      <div v-else class="reply-box">登录后即可回复</div>
    </div>

    <!-- Thread List View -->
    <div v-else class="thread-list-view">
      <div class="filter-bar">
        <span>我的帖子</span>
      </div>
      <div v-if="!auth.loggedIn" style="text-align: center; margin-top: 50px; color: #666;">
        请先登录
      </div>
      <ul v-else-if="posts.length > 0" class="thread-list">
        <li v-for="p in posts" :key="p.id" class="thread-row">
          <div class="thread-main" @click="openThread(p.id)">
            <a href="#" class="thread-title-link">{{ p.title }}</a>
            <div class="thread-desc">{{ p.content.substring(0, 50) }}...</div>
          </div>
          <div class="thread-meta">
            <span class="author-icon">👤</span> {{ p.author }}
            <button @click.stop="deleteThread(p.id)" class="del-btn" style="margin-left: 10px;">删除</button>
          </div>
        </li>
      </ul>
      <div v-else style="text-align: center; margin-top: 50px; color: #666;">
        暂无帖子
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios'
import { authState } from '../store.js'

export default {
  data() {
    return {
      posts: [],
      auth: authState,
      commentText: '',
      viewingThread: false,
      currentThread: null,
      currentComments: [],
      commentImages: [],
      commentAttachments: [],
      commentImagePreviews: [],
      showEmoji: false,
      emojis: ['😀', '😂', '😍', '🥳', '😎', '👍', '🔥', '🎉', '💡', '💻', '🚀', '✅']
    }
  },
  mounted() { this.load(); },
  beforeUnmount() {
    this.clearCommentImagePreviews()
  },
  methods: {
    async load() {
      if (!this.auth.loggedIn || !this.auth.user) return;
      try {
        const res = await axios.get('/api/posts/', { params: { author: this.auth.user.username } });
        this.posts = res.data.posts
      } catch (e) { console.error(e) }
    },
    onCommentImagesSelected(e) {
      this.commentImages = Array.from(e.target.files || [])
      this.refreshCommentImagePreviews()
    },
    onCommentAttachmentsSelected(e) { this.commentAttachments = Array.from(e.target.files || []) },
    refreshCommentImagePreviews() {
      this.clearCommentImagePreviews()
      this.commentImagePreviews = this.commentImages.map(file => ({ file, url: URL.createObjectURL(file) }))
    },
    clearCommentImagePreviews() {
      this.commentImagePreviews.forEach(item => URL.revokeObjectURL(item.url))
      this.commentImagePreviews = []
    },
    removeSelectedFile(type, index) {
      if (type === 'image') {
        const removed = this.commentImagePreviews[index]
        if (removed) URL.revokeObjectURL(removed.url)
        this.commentImages.splice(index, 1)
        this.commentImagePreviews.splice(index, 1)
      } else {
        this.commentAttachments.splice(index, 1)
      }
    },
    async postComment(postId) {
      if (!this.commentText.trim() && this.commentImages.length === 0 && this.commentAttachments.length === 0) return;
      try {
        const fd = new FormData()
        fd.append('content', this.commentText)
        this.commentImages.forEach(f => fd.append('images', f))
        this.commentAttachments.forEach(f => fd.append('attachments', f))
        await axios.post(`/api/posts/${postId}/comments/`, fd, { withCredentials: true })
        this.commentText = ''
        this.commentImages = []
        this.commentAttachments = []
        this.clearCommentImagePreviews()
        this.showEmoji = false
        alert('评论已发布')
        this.openThread(postId)
      } catch (e) { alert('评论失败：' + (e.response?.data?.error||e.message)) }
    },
    async openThread(postId) {
      try {
        const res = await axios.get(`/api/posts/${postId}/`)
        this.currentThread = res.data.post
        this.currentComments = res.data.comments
        this.viewingThread = true
      } catch (e) { alert('加载失败：' + (e.response?.data?.error||e.message)) }
    },
    async deleteThread(postId) {
      if (!confirm('确定要删除这篇帖子吗？')) return;
      try {
        await axios.delete(`/api/posts/${postId}/`, { withCredentials: true })
        alert('帖子已删除')
        this.viewingThread = false
        this.load()
      } catch (e) { alert('删除失败：' + (e.response?.data?.error||e.message)) }
    },
    async deleteComment(postId, commentId) {
      if (!confirm('确定要删除这条评论吗？')) return;
      try {
        await axios.delete(`/api/posts/${postId}/comments/${commentId}/`, { withCredentials: true })
        alert('评论已删除')
        this.openThread(postId)
      } catch (e) { alert('删除失败：' + (e.response?.data?.error||e.message)) }
    },
    closeThread() {
      this.viewingThread = false
      this.currentThread = null
      this.currentComments = []
      this.commentText = ''
      this.commentImages = []
      this.commentAttachments = []
      this.clearCommentImagePreviews()
      this.showEmoji = false
      this.load()
    },
    isAuthor(authorUsername) {
      return this.auth.user && (this.auth.user.username === authorUsername)
    }
  },
  computed: {
    isAdmin() {
      return this.auth.user && this.auth.user.is_staff
    }
  },
  watch: {
    'auth.loggedIn'(val) {
      if (val) this.load();
    }
  }
}
</script>

<style scoped>
.tieba-forum {
  font-family: "Microsoft YaHei", sans-serif;
  color: #26344b;
}
.filter-bar {
  font-size: 18px;
  font-weight: 700;
  padding-bottom: 10px;
  border-bottom: 1px solid #e7edf8;
  margin-bottom: 15px;
}
.thread-list {
  list-style: none;
  padding: 0;
}
.thread-row {
  display: flex;
  justify-content: space-between;
  padding: 14px 12px;
  border-bottom: 1px solid #edf1f8;
  border-radius: 12px;
  transition: background .2s ease;
}
.thread-row:hover {
  background: #f8faff;
}
.thread-main {
  cursor: pointer;
  flex: 1;
}
.thread-title-link {
  color: #2d5fc2;
  font-size: 16px;
  text-decoration: none;
  font-weight: 700;
}
.thread-title-link:hover {
  color: #1f4ca4;
}
.thread-desc {
  color: #71809c;
  font-size: 13px;
  margin-top: 5px;
}
.thread-meta {
  width: 150px;
  text-align: right;
  color: #8491aa;
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

.reply-btn {
  background: linear-gradient(135deg,#4d89ea,#3d74d1);
  color: white;
  border: none;
  padding: 10px 20px;
  cursor: pointer;
  border-radius: 10px;
  font-size: 14px;
}

.thread-view {
  background: white;
  border-radius: 14px;
}
.breadcrumb {
  margin-bottom: 15px;
}
.breadcrumb a {
  color: #3566d6;
  text-decoration: none;
}
.thread-title {
  border-bottom: 1px solid #e7edf8;
  padding-bottom: 15px;
  margin-bottom: 0;
}
.floor {
  display: flex;
  border-bottom: 1px solid #edf1f8;
}
.author-info {
  width: 130px;
  background: #f7f9ff;
  padding: 15px;
  text-align: center;
  border-right: 1px solid #e7edf8;
}
.avatar-placeholder {
  width: 80px;
  height: 80px;
  background: linear-gradient(135deg,#dde6fa,#c8d6f5);
  border-radius: 50%;
  margin: 0 auto 10px;
}
.post-body {
  flex: 1;
  padding: 15px;
  display: flex;
  flex-direction: column;
}
.post-content {
  flex: 1;
  font-size: 14px;
}
.post-actions {
  text-align: right;
  margin-top: 15px;
  color: #8998b2;
  font-size: 12px;
}
.floor-num {
  margin-right: 10px;
}
.del-btn {
  background: #fff1f1;
  border: 1px solid #ffdcdc;
  color: #d83434;
  border-radius: 8px;
  padding: 4px 10px;
  cursor: pointer;
}
.reply-box {
  margin-top: 20px;
  padding: 15px;
  border-radius: 12px;
  background: #f9fbff;
  border: 1px solid #e7edf8;
}
.reply-box textarea {
  width: 100%;
  padding: 10px;
  border: 1px solid #d7e1f3;
  border-radius: 10px;
  box-sizing: border-box;
  margin-bottom: 10px;
}
.editor-tools { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.tool-btn { border: 1px solid #d6e2f8; background: #f3f7ff; color: #34589e; border-radius: 8px; padding: 6px 10px; cursor: pointer; font-size: 13px; }
.upload-btn input { display: none; }
.emoji-panel { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; padding: 8px; border: 1px solid #e7edf8; border-radius: 10px; background: #fff; }
.emoji-panel button { border: none; background: #f5f7ff; border-radius: 8px; padding: 4px 8px; cursor: pointer; font-size: 18px; }
.selected-files { color: #5d6b87; font-size: 12px; margin-bottom: 10px; }
.selected-preview-grid { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
.selected-preview-item { position: relative; width: 84px; height: 84px; border-radius: 10px; overflow: hidden; border: 1px solid #dfe7f7; }
.selected-preview-item img { width: 100%; height: 100%; object-fit: cover; }
.selected-attachment-list { display: flex; flex-wrap: wrap; gap: 8px; }
.attachment-chip { display: inline-flex; align-items: center; gap: 6px; background: #f4f7ff; border: 1px solid #dbe5fb; border-radius: 999px; padding: 4px 10px; }
.remove-file-btn { position: absolute; top: 4px; right: 4px; border: none; background: rgba(231,73,73,.95); color: #fff; width: 20px; height: 20px; border-radius: 50%; cursor: pointer; line-height: 20px; padding: 0; font-size: 12px; z-index: 2; box-shadow: 0 2px 6px rgba(0,0,0,.2); }
.remove-file-btn:hover { background: #cf2f2f; }
.media-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 10px; margin-top: 12px; }
.media-grid img { width: 100%; height: 100px; object-fit: cover; border-radius: 10px; border: 1px solid #e8edf7; }
.attachment-list { display: flex; flex-direction: column; gap: 6px; margin-top: 10px; }
.attachment-list a { color: #2d5fc2; text-decoration: none; font-size: 13px; }
.attachment-list a:hover { text-decoration: underline; }
</style>