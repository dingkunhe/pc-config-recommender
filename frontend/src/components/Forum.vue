<template>
  <div class="tieba-forum" :class="{ 'system-board': board === 'system' }">
    <div v-if="viewingThread" class="thread-view">
      <div class="breadcrumb"><a href="#" @click.prevent="closeThread">&lt; 返回论坛</a></div>
      <h2 class="thread-title">{{ currentThread.title }}</h2>

      <div class="post-item floor">
        <div class="author-info" :class="{ 'no-avatar': !showAuthorAvatar }">
          <img v-if="showAuthorAvatar && currentThread.author_avatar_url" :src="currentThread.author_avatar_url" class="avatar-img" alt="avatar" />
          <div v-else-if="showAuthorAvatar" class="avatar-placeholder"></div>
          <strong>{{ currentThread.author }}</strong>
        </div>
        <div class="post-body">
          <div class="post-content markdown-body" v-html="renderMarkdown(currentThread.content)"></div>
          <div class="media-grid" v-if="currentThread.images && currentThread.images.length">
            <a v-for="(img, idx) in currentThread.images" :key="`pimg-${idx}`" :href="img.url" target="_blank" rel="noopener noreferrer">
              <img :src="img.url" :alt="img.name" />
            </a>
          </div>
          <div class="attachment-list" v-if="currentThread.attachments && currentThread.attachments.length">
            <a v-for="(att, idx) in currentThread.attachments" :key="`patt-${idx}`" :href="att.url" target="_blank" rel="noopener noreferrer">📎 {{ att.name }}</a>
          </div>
          <div class="post-actions">
            <button v-if="allowLike" @click="togglePostLike(currentThread)" class="like-btn" :class="{ liked: currentThread.is_liked }">
              <svg viewBox="0 0 24 24" class="heart-icon"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>
              <span>{{ currentThread.likes_count || 0 }}</span>
            </button>
            <span class="floor-num">楼主</span>
            <div v-if="hasPostMenuActions(currentThread)" class="action-menu-wrap" @click.stop>
              <button class="more-btn" @click.stop="toggleActionMenu(`thread-post-${currentThread.id}`)">...</button>
              <div v-if="isActionMenuOpen(`thread-post-${currentThread.id}`)" class="action-menu">
                <button v-if="allowReport" @click.stop="report('post', currentThread.id); closeActionMenu()">举报</button>
                <button v-if="canDeletePost(currentThread)" @click.stop="deleteThread(currentThread.id); closeActionMenu()">删除</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="post-item floor" :class="{ 'is-target-floor': highlightCommentId === comment.id }" :data-comment-id="comment.id" v-for="(comment, index) in currentComments" :key="comment.id">
        <div class="author-info" :class="{ 'no-avatar': !showAuthorAvatar }">
          <img v-if="showAuthorAvatar && comment.author_avatar_url" :src="comment.author_avatar_url" class="avatar-img" alt="avatar" />
          <div v-else-if="showAuthorAvatar" class="avatar-placeholder"></div>
          <strong>{{ comment.author }}</strong>
        </div>
        <div class="post-body">
          <div v-if="comment.parent_comment" class="reply-ref">回复 @{{ comment.parent_comment.author }}：{{ comment.parent_comment.content }}</div>
          <div class="post-content markdown-body" v-html="renderMarkdown(comment.content)"></div>
          <div class="media-grid" v-if="comment.images && comment.images.length">
            <a v-for="(img, idx) in comment.images" :key="`cimg-${comment.id}-${idx}`" :href="img.url" target="_blank" rel="noopener noreferrer">
              <img :src="img.url" :alt="img.name" />
            </a>
          </div>
          <div class="attachment-list" v-if="comment.attachments && comment.attachments.length">
            <a v-for="(att, idx) in comment.attachments" :key="`catt-${comment.id}-${idx}`" :href="att.url" target="_blank" rel="noopener noreferrer">📎 {{ att.name }}</a>
          </div>
          <div class="post-actions">
            <button v-if="allowLike" @click="toggleCommentLike(comment)" class="like-btn" :class="{ liked: comment.is_liked }">
              <svg viewBox="0 0 24 24" class="heart-icon"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>
              <span>{{ comment.likes_count || 0 }}</span>
            </button>
            <button @click="setReplyTarget(comment)" class="reply-link-btn">回复</button>
            <span class="floor-num">{{ index + 2 }}楼</span>
            <div v-if="hasCommentMenuActions(comment)" class="action-menu-wrap" @click.stop>
              <button class="more-btn" @click.stop="toggleActionMenu(`thread-comment-${comment.id}`)">...</button>
              <div v-if="isActionMenuOpen(`thread-comment-${comment.id}`)" class="action-menu">
                <button v-if="allowReport" @click.stop="report('comment', comment.id); closeActionMenu()">举报</button>
                <button v-if="canDeleteComment(comment)" @click.stop="deleteComment(currentThread.id, comment.id); closeActionMenu()">删除</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="reply-box" v-if="canCommentCurrentBoard">
        <div v-if="replyTargetComment" class="reply-target-tip">
          正在回复 @{{ replyTargetComment.author }}
          <button type="button" class="cancel-reply-btn" @click="clearReplyTarget">取消</button>
        </div>
        <div class="editor-tools">
          <button type="button" class="tool-btn" @click="toggleEmoji('comment')">😀 表情</button>
          <label class="tool-btn upload-btn">🖼 图片
            <input type="file" multiple accept="image/*" @change="onCommentImagesSelected" />
          </label>
          <label class="tool-btn upload-btn">📎 附件
            <input type="file" multiple @change="onCommentAttachmentsSelected" />
          </label>
        </div>
        <div v-if="showCommentEmoji" class="emoji-panel">
          <button v-for="e in emojis" :key="e" type="button" @click="insertEmoji('comment', e)">{{ e }}</button>
        </div>
        <textarea v-model="commentText" :placeholder="replyTargetComment ? ('回复 @' + replyTargetComment.author + '...') : '写下你的评论...'" rows="4"></textarea>
        <div class="selected-files" v-if="commentImages.length || commentAttachments.length">
          <div v-if="commentImagePreviews.length" class="selected-preview-grid">
            <div class="selected-preview-item" v-for="(item, idx) in commentImagePreviews" :key="`cp-${idx}`">
              <img :src="item.url" :alt="item.file.name" />
              <button type="button" class="remove-file-btn" @click.stop.prevent="removeSelectedFile('commentImage', idx)">×</button>
            </div>
          </div>
          <div v-if="commentAttachments.length" class="selected-attachment-list">
            <div class="attachment-chip" v-for="(f, idx) in commentAttachments" :key="`ca-${idx}`">
              <span>📎 {{ f.name }}</span>
              <button type="button" class="remove-file-btn" @click.stop.prevent="removeSelectedFile('commentAttachment', idx)">×</button>
            </div>
          </div>
        </div>
        <button @click="postComment(currentThread.id)" class="reply-btn">{{ replyTargetComment ? '发布回复' : '回复楼主' }}</button>
      </div>
      <div class="reply-box" v-else>{{ commentDeniedText }}</div>
    </div>

    <div v-else>
      <div class="forum-board-header">
        <div class="forum-board-title">{{ sectionTitle }}</div>
        <div v-if="board === 'system'" class="forum-board-subtitle">官方公告 · 仅管理员发布</div>
      </div>
      <div v-if="board === 'square'" class="square-feed">
        <div v-for="p in pagedPosts" :key="`sq-${p.id}`" class="square-card">
          <div class="square-header">
            <div class="square-user">
              <img v-if="p.author_avatar_url" :src="p.author_avatar_url" class="square-avatar" alt="avatar" />
              <div v-else class="square-avatar placeholder"></div>
              <strong>{{ p.author }}</strong>
            </div>
            <div v-if="hasPostMenuActions(p)" class="action-menu-wrap" @click.stop>
              <button class="more-btn" @click.stop="toggleActionMenu(`list-post-${p.id}`)">...</button>
              <div v-if="isActionMenuOpen(`list-post-${p.id}`)" class="action-menu">
                <button v-if="allowReport" @click.stop="report('post', p.id); closeActionMenu()">举报</button>
                <button v-if="canDeletePost(p)" @click.stop="deleteThread(p.id); closeActionMenu()">删除</button>
              </div>
            </div>
          </div>

          <div class="square-body" @click="openThread(p.id)">
            <div class="square-title">{{ p.title }}</div>
            <div v-if="p.content" class="square-content">{{ getPostDisplayContent(p) }}</div>
            <button
              v-if="isPostContentLong(p.content)"
              class="expand-btn"
              @click.stop.prevent="togglePostExpand(p.id)"
            >
              {{ isPostExpanded(p.id) ? '收起' : '展开' }}
            </button>
            <div class="square-media-grid" v-if="p.images && p.images.length">
              <a v-for="(img, idx) in p.images" :key="`sq-img-${p.id}-${idx}`" :href="img.url" target="_blank" rel="noopener noreferrer" @click.stop>
                <img :src="img.url" :alt="img.name" />
              </a>
            </div>
          </div>

          <div class="square-footer">
            <button class="reply-stat" @click.stop="openThread(p.id)">💬 {{ p.comments_count || 0 }}</button>
            <button v-if="allowLike" @click.stop="togglePostLike(p)" class="like-btn" :class="{ liked: p.is_liked }">
              <svg viewBox="0 0 24 24" class="heart-icon"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>
              <span>{{ p.likes_count || 0 }}</span>
            </button>
          </div>
        </div>
      </div>

      <div v-else-if="board === 'qa'" class="qa-list">
        <div class="qa-head">
          <div>问题</div>
          <div>发帖人 / 时间</div>
          <div>最新回复</div>
          <div></div>
        </div>
        <div v-for="p in pagedPosts" :key="`qa-${p.id}`" class="qa-row">
          <div class="qa-question" @click="openThread(p.id)">{{ p.title }}</div>
          <div class="qa-meta">
            <div class="qa-user">{{ p.author || '-' }}</div>
            <div class="qa-time">{{ formatDateTime(p.created_at) }}</div>
          </div>
          <div class="qa-meta">
            <div class="qa-user">{{ p.latest_reply_author || '暂无回复' }}</div>
            <div class="qa-time">{{ p.latest_reply_at ? formatDateTime(p.latest_reply_at) : '-' }}</div>
          </div>
          <div>
            <div v-if="hasPostMenuActions(p)" class="action-menu-wrap" @click.stop>
              <button class="more-btn" @click.stop="toggleActionMenu(`list-post-${p.id}`)">...</button>
              <div v-if="isActionMenuOpen(`list-post-${p.id}`)" class="action-menu">
                <button v-if="allowReport" @click.stop="report('post', p.id); closeActionMenu()">举报</button>
                <button v-if="canDeletePost(p)" @click.stop="deleteThread(p.id); closeActionMenu()">删除</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <ul v-else class="thread-list">
        <li v-for="p in pagedPosts" :key="p.id" class="thread-row">
          <div class="thread-main" @click="openThread(p.id)">
            <a href="#" class="thread-title-link">{{ p.title }}</a>
            <div class="thread-desc">
              {{ p.author }}
              <span v-if="p.images && p.images.length" class="media-tag">🖼 {{ p.images.length }}</span>
              <span v-if="p.attachments && p.attachments.length" class="media-tag">📎 {{ p.attachments.length }}</span>
            </div>
            <div v-if="p.content" class="thread-preview">{{ getPostDisplayContent(p) }}</div>
            <button
              v-if="isPostContentLong(p.content)"
              class="expand-btn"
              @click.stop.prevent="togglePostExpand(p.id)"
            >
              {{ isPostExpanded(p.id) ? '收起' : '展开' }}
            </button>
          </div>
          <div class="thread-meta">
            <button v-if="allowLike" @click.stop="togglePostLike(p)" class="like-btn" :class="{ liked: p.is_liked }">
              <svg viewBox="0 0 24 24" class="heart-icon"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>
              <span>{{ p.likes_count || 0 }}</span>
            </button>
            <div v-if="hasPostMenuActions(p)" class="action-menu-wrap" @click.stop>
              <button class="more-btn" @click.stop="toggleActionMenu(`list-post-${p.id}`)">...</button>
              <div v-if="isActionMenuOpen(`list-post-${p.id}`)" class="action-menu">
                <button v-if="allowReport" @click.stop="report('post', p.id); closeActionMenu()">举报</button>
                <button v-if="canDeletePost(p)" @click.stop="deleteThread(p.id); closeActionMenu()">删除</button>
              </div>
            </div>
          </div>
        </li>
      </ul>

      <div class="pagination" v-if="totalItems > 0">
        <div class="pagination-left">
          <span>每页显示</span>
          <select v-model.number="pageSize" class="page-size-select">
            <option :value="4">4</option>
            <option :value="6">6</option>
            <option :value="8">8</option>
          </select>
          <span>条（最多8条）</span>
        </div>
        <div class="pagination-right">
          <button class="page-btn" :disabled="currentPage <= 1" @click="goToPage(currentPage - 1)">上一页</button>
          <span class="page-info">第 {{ currentPage }} / {{ totalPages }} 页，共 {{ totalItems }} 条</span>
          <button class="page-btn" :disabled="currentPage >= totalPages" @click="goToPage(currentPage + 1)">下一页</button>
        </div>
      </div>

      <div class="create-post" v-if="canCreatePost">
        <h3>发帖</h3>
        <form @submit.prevent="createPost">
          <input v-model="newPost.title" class="tb-input" placeholder="请填写标题" />
          <div class="editor-tools">
            <button type="button" class="tool-btn" @click="toggleEmoji('post')">😀 表情</button>
            <label class="tool-btn upload-btn">🖼 图片
              <input type="file" multiple accept="image/*" @change="onPostImagesSelected" />
            </label>
            <label class="tool-btn upload-btn">📎 附件
              <input type="file" multiple @change="onPostAttachmentsSelected" />
            </label>
          </div>
          <div v-if="showPostEmoji" class="emoji-panel">
            <button v-for="e in emojis" :key="`post-${e}`" type="button" @click="insertEmoji('post', e)">{{ e }}</button>
          </div>
          <textarea v-model="newPost.content" class="tb-textarea" placeholder="在此输入内容" rows="5"></textarea>
          <div class="selected-files" v-if="postImages.length || postAttachments.length">
            <div v-if="postImagePreviews.length" class="selected-preview-grid">
              <div class="selected-preview-item" v-for="(item, idx) in postImagePreviews" :key="`pp-${idx}`">
                <img :src="item.url" :alt="item.file.name" />
                <button type="button" class="remove-file-btn" @click.stop.prevent="removeSelectedFile('postImage', idx)">×</button>
              </div>
            </div>
            <div v-if="postAttachments.length" class="selected-attachment-list">
              <div class="attachment-chip" v-for="(f, idx) in postAttachments" :key="`pa-${idx}`">
                <span>📎 {{ f.name }}</span>
                <button type="button" class="remove-file-btn" @click.stop.prevent="removeSelectedFile('postAttachment', idx)">×</button>
              </div>
            </div>
          </div>
          <button type="submit" class="reply-btn">发表</button>
        </form>
      </div>
      <div class="create-post" v-else>{{ createPostDeniedText }}</div>
    </div>
  </div>
</template>

<script>
import axios from 'axios'
import { marked } from 'marked'
import { authState, searchState } from '../store.js'

export default {
  emits: ['nav-target-consumed'],
  props: {
    navTarget: {
      type: Object,
      default: null
    },
    board: {
      type: String,
      default: 'square'
    },
    sectionTitle: {
      type: String,
      default: '交流广场'
    }
  },
  data() {
    return {
      posts: [],
      search: searchState,
      newPost: { title: '', content: '' },
      auth: authState,
      previewLimit: 140,
      expandedPosts: {},
      commentText: '',
      viewingThread: false,
      currentThread: null,
      currentComments: [],
      postImages: [],
      postAttachments: [],
      commentImages: [],
      commentAttachments: [],
      postImagePreviews: [],
      commentImagePreviews: [],
      replyTargetComment: null,
      highlightCommentId: null,
      showPostEmoji: false,
      showCommentEmoji: false,
      openActionMenuKey: null,
      currentPage: 1,
      pageSize: 8,
      emojis: ['😀', '😂', '😍', '🥳', '😎', '👍', '🔥', '🎉', '💡', '💻', '🚀', '✅']
    }
  },
  mounted() {
    this.load()
    document.addEventListener('click', this.handleGlobalClick)
  },
  watch: {
    navTarget: {
      immediate: true,
      async handler(val) {
        if (!val || !val.postId) return
        await this.navigateByTarget(val)
      }
    },
    board() {
      this.viewingThread = false
      this.currentThread = null
      this.currentComments = []
      this.highlightCommentId = null
      this.currentPage = 1
      this.load()
    },
    pageSize() {
      if (this.pageSize > 8) this.pageSize = 8
      if (this.pageSize < 1) this.pageSize = 1
      this.currentPage = 1
    },
    'search.query'() {
      this.currentPage = 1
    },
    'search.type'() {
      this.currentPage = 1
    },
    totalPages() {
      if (this.currentPage > this.totalPages) {
        this.currentPage = this.totalPages
      }
    }
  },
  beforeUnmount() {
    this.clearImagePreviews('post')
    this.clearImagePreviews('comment')
    document.removeEventListener('click', this.handleGlobalClick)
  },
  methods: {
    handleGlobalClick() {
      this.closeActionMenu()
    },
    toggleActionMenu(key) {
      this.openActionMenuKey = this.openActionMenuKey === key ? null : key
    },
    closeActionMenu() {
      this.openActionMenuKey = null
    },
    isActionMenuOpen(key) {
      return this.openActionMenuKey === key
    },
    canDeletePost(post) {
      return !!(post && (this.isAdmin || this.isAuthor(post.author)))
    },
    canDeleteComment(comment) {
      return !!(comment && (this.isAdmin || this.isAuthor(comment.author)))
    },
    hasPostMenuActions(post) {
      return this.allowReport || this.canDeletePost(post)
    },
    hasCommentMenuActions(comment) {
      return this.allowReport || this.canDeleteComment(comment)
    },
    async navigateByTarget(target) {
      const postId = Number(target.postId)
      const commentId = target.commentId ? Number(target.commentId) : null
      if (!postId) {
        this.$emit('nav-target-consumed')
        return
      }

      await this.openThread(postId)
      this.highlightCommentId = commentId
      this.$emit('nav-target-consumed')

      this.$nextTick(() => {
        if (commentId) {
          const el = this.$el && this.$el.querySelector(`[data-comment-id="${commentId}"]`)
          if (el) {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' })
            return
          }
        }
        const titleEl = this.$el && this.$el.querySelector('.thread-title')
        if (titleEl) titleEl.scrollIntoView({ behavior: 'smooth', block: 'start' })
      })
    },
    async report(type, id) {
      if (!this.auth.loggedIn) return alert('请先登录再操作')
      if (!confirm('确定要举报此' + (type === 'post' ? '动态' : '评论') + '吗？')) return
      try {
        await axios.post('/api/report/', { type, id }, { withCredentials: true })
        alert('举报成功，已提交管理员审核。')
      } catch (err) {
        alert('举报失败：' + (err.response?.data?.error || err.message))
      }
    },
    onPostImagesSelected(e) {
      this.postImages = Array.from(e.target.files || [])
      this.refreshImagePreviews('post')
    },
    onPostAttachmentsSelected(e) { this.postAttachments = Array.from(e.target.files || []) },
    onCommentImagesSelected(e) {
      this.commentImages = Array.from(e.target.files || [])
      this.refreshImagePreviews('comment')
    },
    onCommentAttachmentsSelected(e) { this.commentAttachments = Array.from(e.target.files || []) },
    refreshImagePreviews(target) {
      this.clearImagePreviews(target)
      const files = target === 'post' ? this.postImages : this.commentImages
      const previews = files.map(file => ({ file, url: URL.createObjectURL(file) }))
      if (target === 'post') this.postImagePreviews = previews
      else this.commentImagePreviews = previews
    },
    clearImagePreviews(target) {
      const previews = target === 'post' ? this.postImagePreviews : this.commentImagePreviews
      previews.forEach(item => URL.revokeObjectURL(item.url))
      if (target === 'post') this.postImagePreviews = []
      else this.commentImagePreviews = []
    },
    removeSelectedFile(type, index) {
      if (type === 'postImage') {
        const removed = this.postImagePreviews[index]
        if (removed) URL.revokeObjectURL(removed.url)
        this.postImages.splice(index, 1)
        this.postImagePreviews.splice(index, 1)
      } else if (type === 'commentImage') {
        const removed = this.commentImagePreviews[index]
        if (removed) URL.revokeObjectURL(removed.url)
        this.commentImages.splice(index, 1)
        this.commentImagePreviews.splice(index, 1)
      } else if (type === 'postAttachment') {
        this.postAttachments.splice(index, 1)
      } else if (type === 'commentAttachment') {
        this.commentAttachments.splice(index, 1)
      }
    },
    toggleEmoji(target) {
      if (target === 'post') {
        this.showPostEmoji = !this.showPostEmoji
        this.showCommentEmoji = false
      } else {
        this.showCommentEmoji = !this.showCommentEmoji
        this.showPostEmoji = false
      }
    },
    insertEmoji(target, emoji) {
      if (target === 'post') this.newPost.content = (this.newPost.content || '') + emoji
      else this.commentText = (this.commentText || '') + emoji
    },
    setReplyTarget(comment) {
      this.replyTargetComment = {
        id: comment.id,
        author: comment.author,
        content: comment.content || ''
      }
      this.$nextTick(() => {
        const el = this.$el && this.$el.querySelector('.reply-box textarea')
        if (el) el.focus()
      })
    },
    clearReplyTarget() {
      this.replyTargetComment = null
    },
    async togglePostLike(post) {
      try {
        const res = await axios.post(`/api/posts/${post.id}/like/`, {}, { withCredentials: true })
        post.is_liked = res.data.liked
        post.likes_count = res.data.likes_count
      } catch (err) {
        if (err.response && err.response.status === 401) alert('请先登录再操作')
      }
    },
    async toggleCommentLike(comment) {
      try {
        const res = await axios.post(`/api/comments/${comment.id}/like/`, {}, { withCredentials: true })
        comment.is_liked = res.data.liked
        comment.likes_count = res.data.likes_count
      } catch (err) {
        if (err.response && err.response.status === 401) alert('请先登录再操作')
      }
    },
    async load() {
      try {
        const res = await axios.get('/api/posts/', { params: { board: this.board } })
        this.posts = res.data.posts || []
      } catch (e) { console.error(e) }
    },
    async createPost() {
      if (!this.newPost.title || !this.newPost.title.trim()) return alert('标题不能为空')
      try {
        const fd = new FormData()
        fd.append('title', this.newPost.title)
        fd.append('content', this.newPost.content || '')
        fd.append('board', this.board)
        this.postImages.forEach(f => fd.append('images', f))
        this.postAttachments.forEach(f => fd.append('attachments', f))

        await axios.post('/api/posts/', fd, { withCredentials: true })
        this.newPost.title = ''
        this.newPost.content = ''
        this.postImages = []
        this.postAttachments = []
        this.clearImagePreviews('post')
        this.showPostEmoji = false
        this.load()
      } catch (e) { alert('发布失败：' + (e.response?.data?.error || e.message)) }
    },
    async postComment(postId) {
      if (!this.commentText.trim() && this.commentImages.length === 0 && this.commentAttachments.length === 0) {
        return alert('评论内容和附件不能同时为空')
      }
      try {
        const fd = new FormData()
        fd.append('content', this.commentText)
        if (this.replyTargetComment && this.replyTargetComment.id) {
          fd.append('parent_comment_id', String(this.replyTargetComment.id))
        }
        this.commentImages.forEach(f => fd.append('images', f))
        this.commentAttachments.forEach(f => fd.append('attachments', f))

        await axios.post(`/api/posts/${postId}/comments/`, fd, { withCredentials: true })
        this.commentText = ''
        this.commentImages = []
        this.commentAttachments = []
        this.clearImagePreviews('comment')
        this.showCommentEmoji = false
        this.clearReplyTarget()
        await this.openThread(postId)
      } catch (e) { alert('评论失败：' + (e.response?.data?.error || e.message)) }
    },
    async openThread(postId) {
      try {
        const res = await axios.get(`/api/posts/${postId}/`)
        this.currentThread = res.data.post
        this.currentComments = res.data.comments
        this.viewingThread = true
        this.clearReplyTarget()
        if (this.highlightCommentId) {
          const exists = this.currentComments.some(c => c.id === this.highlightCommentId)
          if (!exists) this.highlightCommentId = null
        }
      } catch (e) { alert('加载失败：' + (e.response?.data?.error || e.message)) }
    },
    async deleteThread(postId) {
      try {
        await axios.delete(`/api/posts/${postId}/`, { withCredentials: true })
        alert('帖子已删除')
        this.viewingThread = false
        this.load()
      } catch (e) { alert('删除失败：' + (e.response?.data?.error || e.message)) }
    },
    async deleteComment(postId, commentId) {
      try {
        await axios.delete(`/api/posts/${postId}/comments/${commentId}/`, { withCredentials: true })
        alert('评论已删除')
        this.openThread(postId)
      } catch (e) { alert('删除失败：' + (e.response?.data?.error || e.message)) }
    },
    closeThread() {
      this.viewingThread = false
      this.currentThread = null
      this.currentComments = []
      this.commentText = ''
      this.commentImages = []
      this.commentAttachments = []
      this.clearImagePreviews('comment')
      this.showCommentEmoji = false
      this.clearReplyTarget()
      this.highlightCommentId = null
      this.load()
    },
    goToPage(page) {
      const p = Number(page) || 1
      if (p < 1) {
        this.currentPage = 1
        return
      }
      if (p > this.totalPages) {
        this.currentPage = this.totalPages
        return
      }
      this.currentPage = p
    },
    renderMarkdown(text) {
      if (!text) return ''
      return marked.parse(text, { breaks: true })
    },
    isPostContentLong(content) {
      return (content || '').length > this.previewLimit
    },
    isPostExpanded(postId) {
      return !!this.expandedPosts[postId]
    },
    getPostDisplayContent(post) {
      const content = post?.content || ''
      if (!this.isPostContentLong(content) || this.isPostExpanded(post.id)) {
        return content
      }
      return content.slice(0, this.previewLimit) + '...'
    },
    togglePostExpand(postId) {
      this.expandedPosts = {
        ...this.expandedPosts,
        [postId]: !this.expandedPosts[postId]
      }
    },
    formatDateTime(v) {
      if (!v) return '-'
      try {
        return new Date(v).toLocaleString()
      } catch (e) {
        return '-'
      }
    },
    isAuthor(authorUsername) {
      return this.auth.user && this.auth.user.username === authorUsername
    }
  },
  computed: {
    filteredPosts() {
      if (!this.search || !this.search.query || !this.search.query.trim()) return this.posts
      const q = this.search.query.trim().toLowerCase()
      return this.posts.filter(p => {
        if (this.search.type === 'title') return (p.title && p.title.toLowerCase().includes(q)) || (p.content && p.content.toLowerCase().includes(q))
        return p.author && p.author.toLowerCase().includes(q)
      })
    },
    totalItems() {
      return this.filteredPosts.length
    },
    totalPages() {
      const safeSize = Math.max(1, Math.min(8, Number(this.pageSize) || 8))
      return Math.max(1, Math.ceil(this.totalItems / safeSize))
    },
    pagedPosts() {
      const safeSize = Math.max(1, Math.min(8, Number(this.pageSize) || 8))
      const safePage = Math.max(1, Math.min(this.currentPage, this.totalPages))
      const start = (safePage - 1) * safeSize
      return this.filteredPosts.slice(start, start + safeSize)
    },
    isAdmin() {
      return this.auth.user && this.auth.user.is_staff
    },
    allowLike() {
      return this.board === 'square'
    },
    allowReport() {
      return this.board !== 'system'
    },
    showAuthorAvatar() {
      return this.board !== 'qa'
    },
    canCreatePost() {
      if (!this.auth.loggedIn) return false
      if (this.board === 'system') return !!this.isAdmin
      return true
    },
    canCommentCurrentBoard() {
      if (!this.auth.loggedIn) return false
      if (this.board === 'system') return !!this.isAdmin
      return true
    },
    createPostDeniedText() {
      if (!this.auth.loggedIn) return '登录后即可发帖'
      if (this.board === 'system') return '仅管理员可在系统通知发布内容'
      return '暂无发帖权限'
    },
    commentDeniedText() {
      if (!this.auth.loggedIn) return '登录后即可回复'
      if (this.board === 'system') return '仅管理员可在系统通知发布内容'
      return '暂无回复权限'
    }
  }
}
</script>

<style scoped>
.tieba-forum { font-family: "Microsoft YaHei", sans-serif; color: #243145; }
.forum-board-header { margin-bottom: 12px; }
.forum-board-title { font-size: 18px; font-weight: 700; color: #2f4776; margin-bottom: 12px; }
.forum-board-subtitle { font-size: 12px; color: #6b7a95; margin-top: -8px; }

.square-feed { display: flex; flex-direction: column; gap: 14px; }
.square-card { background: #fff; border: 1px solid #e6ecf9; border-radius: 14px; padding: 14px 16px 12px; box-shadow: 0 6px 16px rgba(54,85,145,.07); }
.square-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.square-user { display: inline-flex; align-items: center; gap: 10px; color: #2f4266; }
.square-avatar { width: 42px; height: 42px; border-radius: 50%; object-fit: cover; border: 1px solid #dfe8fa; }
.square-avatar.placeholder { background: linear-gradient(135deg,#dde6fa,#c8d6f5); }
.square-body { cursor: pointer; }
.square-title { font-size: 18px; line-height: 1.45; color: #223857; font-weight: 700; margin-bottom: 8px; }
.square-content { font-size: 15px; line-height: 1.7; color: #334866; white-space: pre-wrap; word-break: break-word; }
.square-media-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; margin-top: 12px; }
.square-media-grid img { width: 100%; height: 110px; object-fit: cover; border-radius: 10px; border: 1px solid #e5ebf8; }
.square-footer { border-top: 1px solid #edf1f8; margin-top: 12px; padding-top: 10px; display: flex; align-items: center; justify-content: space-between; }
.reply-stat { border: none; background: transparent; color: #5f6f8f; font-size: 15px; cursor: pointer; }
.reply-stat:hover { color: #34589e; }

.qa-list { border: 1px solid #e6ecf9; background: #fff; border-radius: 12px; overflow: visible; position: relative; z-index: 1; }
.qa-head,.qa-row { display: grid; grid-template-columns: 1fr 210px 220px 62px; align-items: center; column-gap: 12px; }
.qa-head { background: #f7f9fe; color: #53627e; font-weight: 700; padding: 9px 12px; font-size: 13px; border-bottom: 1px solid #edf1f8; }
.qa-row { padding: 12px; border-top: 1px dashed #e8edf7; color: #4a5b78; position: relative; overflow: visible; }
.qa-row:first-of-type { border-top: none; }
.qa-question { font-size: 16px; line-height: 1.5; color: #2d3f61; cursor: pointer; }
.qa-question:hover { color: #2d5fc2; text-decoration: underline; text-underline-offset: 2px; }
.qa-meta { color: #6b7b98; font-size: 13px; line-height: 1.45; }
.qa-user { font-weight: 700; color: #405276; }
.qa-time { color: #7f8ca5; }
.qa-list .action-menu-wrap { z-index: 30; }
.qa-list .action-menu { z-index: 50; }

.thread-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 12px; }
.thread-row { display: flex; justify-content: space-between; gap: 14px; padding: 16px 16px 14px; border: 1px solid #e6ecf9; border-radius: 14px; background: linear-gradient(180deg,#ffffff 0%,#fbfdff 100%); box-shadow: 0 6px 16px rgba(54,85,145,.07); transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease; }
.thread-row:hover { transform: translateY(-1px); box-shadow: 0 10px 24px rgba(54,85,145,.12); border-color: #d6e2fb; }
.thread-row:nth-child(odd) { border-left: 4px solid #cfe0ff; }
.thread-row:nth-child(even) { border-left: 4px solid #d9e8ff; }
.thread-main { cursor: pointer; flex: 1; min-width: 0; }
.thread-title-link { color: #2d5fc2; font-size: 16px; text-decoration: none; font-weight: 700; }
.thread-title-link:hover { color: #1e4ea9; text-decoration: underline; text-underline-offset: 2px; }
.thread-desc { color: #6a7894; font-size: 13px; margin-top: 7px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.thread-preview { margin-top: 10px; color: #3f4e68; font-size: 13px; line-height: 1.7; white-space: pre-wrap; word-break: break-word; background: #f7faff; border: 1px solid #e8eefc; border-radius: 10px; padding: 9px 11px; }
.expand-btn { margin-top: 8px; border: 1px solid #d6e2f8; background: #f3f7ff; color: #34589e; padding: 4px 11px; border-radius: 999px; cursor: pointer; font-size: 12px; font-weight: 600; }
.expand-btn:hover { background: #e9f1ff; border-color: #bfd2f7; }
.media-tag { background: #edf3ff; color: #3f63b6; border-radius: 999px; padding: 2px 8px; font-size: 12px; }
.thread-meta { width: 210px; text-align: right; color: #8a96ae; font-size: 13px; display: flex; justify-content: flex-end; gap: 8px; align-items: center; padding-left: 12px; border-left: 1px dashed #e3e9f6; }

.pagination { margin-top: 16px; display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; padding: 10px 12px; border: 1px solid #e6ecf9; border-radius: 12px; background: #fff; }
.pagination-left { display: inline-flex; align-items: center; gap: 8px; color: #52627f; font-size: 13px; }
.pagination-right { display: inline-flex; align-items: center; gap: 10px; }
.page-size-select { border: 1px solid #d6e2f8; background: #f8fbff; color: #2f4776; border-radius: 8px; padding: 4px 8px; }
.page-btn { border: 1px solid #d6e2f8; background: #f3f7ff; color: #34589e; border-radius: 8px; padding: 6px 12px; cursor: pointer; }
.page-btn:hover:not(:disabled) { background: #e9f1ff; }
.page-btn:disabled { cursor: not-allowed; opacity: .5; }
.page-info { color: #60708d; font-size: 13px; }

.create-post { margin-top: 30px; background: #f9fbff; padding: 18px; border: 1px solid #e7edf8; border-radius: 14px; }
.tb-input,.tb-textarea,.reply-box textarea { width: 100%; padding: 10px 12px; border: 1px solid #d7e1f3; border-radius: 10px; box-sizing: border-box; }
.tb-textarea,.reply-box textarea { resize: vertical; margin-bottom: 10px; }
.reply-btn { background: linear-gradient(135deg,#4a87ea,#3a72d2); color: white; border: none; padding: 10px 20px; cursor: pointer; border-radius: 10px; font-size: 14px; box-shadow: 0 8px 18px rgba(69,119,209,.22); }

.thread-view { background: white; border-radius: 14px; }
.breadcrumb { margin-bottom: 15px; }
.breadcrumb a { color: #3566d6; text-decoration: none; }
.thread-title { border-bottom: 1px solid #e8edf7; padding-bottom: 15px; margin-bottom: 0; }
.floor { display: flex; border-bottom: 1px solid #edf1f8; }
.floor.is-target-floor { background: #fff7e8; box-shadow: inset 4px 0 0 #f59e0b; animation: floorFlash 1.4s ease; }
.author-info { width: 130px; background: #f7f9ff; padding: 15px; text-align: center; border-right: 1px solid #e8edf7; }
.author-info.no-avatar { width: 130px; display: flex; align-items: center; justify-content: center; }
.avatar-placeholder { width: 80px; height: 80px; background: linear-gradient(135deg,#dde6fa,#c8d6f5); border-radius: 50%; margin: 0 auto 10px; }
.avatar-img { width: 80px; height: 80px; border-radius: 50%; object-fit: cover; margin: 0 auto 10px; display: block; border: 1px solid #dfe8fa; }
.post-body { flex: 1; padding: 15px; display: flex; flex-direction: column; }
.post-content { flex: 1; font-size: 14px; }
.reply-ref { margin-bottom: 8px; color: #4b5a7a; font-size: 13px; background: #f3f7ff; border: 1px solid #dfe9ff; border-radius: 8px; padding: 6px 10px; }
.post-actions { text-align: right; margin-top: 15px; color: #8b98b2; font-size: 12px; display: flex; justify-content: flex-end; gap: 8px; align-items: center; }
.floor-num { margin-right: 4px; }

.like-btn { display: inline-flex; align-items: center; gap: 4px; background: #f5f7fd; border: 1px solid #e5ebf7; cursor: pointer; color: #8a8a8a; font-size: 14px; padding: 4px 8px; border-radius: 8px; }
.like-btn:hover { background: #edf3ff; }
.heart-icon { width: 18px; height: 18px; fill: #8a8a8a; }
.like-btn.liked { color: #fe2c55; }
.like-btn.liked .heart-icon { fill: #fe2c55; }

.report-btn { border: 1px solid #ffe7bf; background: #fff8eb; color: #d48806; padding: 4px 8px; border-radius: 8px; cursor: pointer; }
.del-btn,.del-btn-list { background: #fff0f0; border: 1px solid #ffd9d9; color: #d93333; border-radius: 8px; padding: 4px 10px; cursor: pointer; }
.reply-link-btn { border: 1px solid #d6e2f8; background: #f3f7ff; color: #34589e; padding: 4px 10px; border-radius: 8px; cursor: pointer; }
.action-menu-wrap { position: relative; }
.more-btn { border: 1px solid #d6e2f8; background: #f5f8ff; color: #3f5d98; border-radius: 8px; padding: 2px 10px; cursor: pointer; font-weight: 700; letter-spacing: 1px; }
.more-btn:hover { background: #eaf1ff; }
.action-menu { position: absolute; right: 0; top: calc(100% + 6px); min-width: 88px; background: #fff; border: 1px solid #dfe7f7; border-radius: 10px; box-shadow: 0 8px 20px rgba(31,52,96,.16); z-index: 20; padding: 6px; display: flex; flex-direction: column; gap: 4px; }
.action-menu button { border: none; background: #f7f9ff; color: #2f4776; border-radius: 8px; padding: 6px 10px; text-align: left; cursor: pointer; font-size: 13px; }
.action-menu button:hover { background: #edf3ff; }

.reply-box { margin-top: 20px; padding: 15px; background: #f9fbff; border: 1px solid #e7edf8; border-radius: 12px; }
.reply-target-tip { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; padding: 8px 10px; border-radius: 8px; background: #edf3ff; border: 1px solid #d8e5ff; color: #355a9f; font-size: 13px; }
.cancel-reply-btn { border: 1px solid #c7d8fa; background: #fff; color: #4062a4; padding: 2px 8px; border-radius: 6px; cursor: pointer; }
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

.system-board .thread-row { border-left: 4px solid #bac9e8; background: linear-gradient(180deg,#ffffff 0%,#f8fbff 100%); box-shadow: 0 4px 12px rgba(39,70,125,.08); }
.system-board .thread-row:hover { transform: none; box-shadow: 0 6px 14px rgba(39,70,125,.1); }
.system-board .thread-title-link { color: #1f3f76; font-weight: 800; }
.system-board .thread-preview { background: #fbfdff; border: 1px solid #dde6f8; color: #334766; }
.system-board .thread-meta { border-left: 1px solid #e4ebf8; }
.system-board .post-actions { background: #f7faff; border-top: 1px solid #e4ecfb; padding-top: 10px; margin-top: 12px; }
.system-board .thread-title { border-bottom: 2px solid #dbe6fa; color: #233f70; }

@keyframes floorFlash {
  0% { background: #ffe9c2; }
  100% { background: #fff7e8; }
}
</style>


