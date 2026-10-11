<template>
  <div class="layout-container">
    <aside class="sidebar">
      <button class="new-chat-btn" @click="startNewChat">+ 新建对话</button>
      <div class="session-list">
        <div 
          v-for="session in sessions" 
          :key="session.id" 
          class="session-item"
          :class="{ active: currentSessionId === session.id }"
          @click="loadSession(session.id)"
        >
          <span class="session-title" :title="session.title">{{ session.title }}</span>
          <span class="delete-icon" @click.stop="deleteSession(session.id)">×</span>
        </div>
      </div>
    </aside>

    <div class="chat-container">
      <h2>智能推荐 - AI 助手 <span v-if="currentTitle" class="session-header-title">({{ currentTitle }})</span></h2>
      <div class="chat-box">
        <div v-for="(msg, index) in messages" :key="index" :class="['message', msg.role]">
          <div class="message-content">
            <strong>{{ msg.role === 'user' ? '你' : 'AI 助手' }}:</strong>
            <div class="markdown-body" v-html="renderMarkdown(msg.content)"></div>
            <button
              v-if="msg.role === 'assistant' && msg.failed && msg.retry_message"
              @click="retryFailedMessage(msg)"
              class="retry-btn"
              :disabled="loading"
            >
              {{ loading ? '重试中...' : '重新发送' }}
            </button>
            <div v-if="msg.role === 'assistant' && isAuditUnavailable(msg)" class="audit-warning">
              <span class="warn-triangle"></span>
              <span>审核系统不可用，无法保证准确性</span>
            </div>
            <button v-if="msg.role === 'assistant'" @click="forwardToForum(msg.content)" class="forward-btn">转发到论坛</button>
          </div>
        </div>
      </div>
      <form @submit.prevent="sendMessage" class="input-area">
        <input type="text" v-model="inputText" placeholder="请输入你的电脑配置需求（例如：5000元，主要打游戏）..." :disabled="loading" required />
        <button type="submit" :disabled="loading">{{ loading ? '发送中...' : '发送' }}</button>
      </form>
    </div>
  </div>
</template>

<script>
import axios from 'axios'
import { marked } from 'marked'

export default {

  data() {
    return {
      inputText: '',
      messages: [
        { role: 'assistant', content: '你好！我是你的电脑配置智能推荐助手。请告诉我你的预算、主要用途（比如打游戏、做设计、写代码等），我将为你提供推荐方案。' }
      ],
      loading: false,
      sessions: [],
      currentSessionId: null,
      currentTitle: '',
      lastUserMessage: ''
    }
  },
  mounted() {
    this.fetchSessions();
  },
  methods: {
    isAuditUnavailable(msg) {
      return !!(msg && msg.audit && msg.audit.status === 'unavailable')
    },
    async forwardToForum(content) {
      const title = prompt('请输入你要发布到论坛的动态标题:', '我分享了一套AI推荐的装机配置！');
      if (!title) return;
      
      try {
        // 先调用 AI 格式化内容为表格
        alert('正在调用 AI 进行表格排版，请稍候...');
        const formatRes = await axios.post('http://localhost:8000/api/recommend/format_table/', { content }, { withCredentials: true });
        let finalContent = content;
        if (formatRes.data.status === 'ok') {
            finalContent = formatRes.data.table_content;
        }

        await axios.post('http://localhost:8000/api/posts/', { title, content: finalContent, board: 'square' }, { withCredentials: true });
        alert('转发成功！请前往动态页面查看。');
      } catch (e) {
        alert('转发失败: ' + (e.response?.data?.error || e.message));
      }
    },
    renderMarkdown(text) {
      if (!text) return '';
      return marked.parse(text, { breaks: true });
    },

    async fetchSessions() {
      try {
        const res = await axios.get('http://localhost:8000/api/chat/sessions/', { withCredentials: true });
        this.sessions = res.data.sessions || [];
      } catch (e) {
        console.error("加载历史对话失败: ", e);
      }
    },
    async loadSession(sessionId) {
      if (this.currentSessionId === sessionId) return;
      this.loading = true;
      try {
        const res = await axios.get(`http://localhost:8000/api/chat/sessions/${sessionId}/`, { withCredentials: true });
        this.messages = res.data.messages || [];
        if (this.messages.length === 0) {
            this.messages = [{ role: 'assistant', content: '你好！我是你的电脑配置智能推荐助手...' }];
        }
        this.currentSessionId = sessionId;
        const activeSession = this.sessions.find(s => s.id === sessionId);
        if (activeSession) this.currentTitle = activeSession.title;
        
        this.scrollToBottom();
      } catch (e) {
        console.error("加载该对话详情失败", e);
      } finally {
        this.loading = false;
      }
    },
    startNewChat() {
      this.currentSessionId = null;
      this.currentTitle = '';
      this.messages = [{ role: 'assistant', content: '你好！我是你的电脑配置智能推荐助手。请告诉我你的预算、主要用途（比如打游戏、做设计、写代码等），我将为你提供推荐方案。' }];
    },
    async deleteSession(sessionId) {
      if (!confirm('确认删除此对话记录吗？')) return;
      try {
        await axios.delete('http://localhost:8000/api/chat/sessions/', { 
            data: { id: sessionId },
            withCredentials: true 
        });
        if (this.currentSessionId === sessionId) {
          this.startNewChat();
        }
        this.fetchSessions();
      } catch(e) {
        console.error('删除对话失败', e);
      }
    },
    async sendMessage() {
      if (!this.inputText.trim()) return;
      const userMessage = this.inputText.trim();
      this.lastUserMessage = userMessage;
      this.messages.push({ role: 'user', content: userMessage });
      this.inputText = '';
      this.loading = true;
      this.scrollToBottom();

      try {
        const payload = {
          message: userMessage,
          session_id: this.currentSessionId
        };
        const res = await axios.post('http://localhost:8000/api/recommend/', payload, { withCredentials: true });
        
        if (res.data.reply) {
          this.messages.push({ role: 'assistant', content: res.data.reply, audit: res.data.audit || null });
          if (!this.currentSessionId && res.data.session_id) {
            this.currentSessionId = res.data.session_id;
            this.currentTitle = res.data.session_title;
            this.fetchSessions(); // refresh the sidebar
          }
        } else {
          this.messages.push({
            role: 'assistant',
            content: '抱歉，未能获取到推荐结果。' + (res.data.error || ''),
            failed: true,
            retry_message: userMessage,
          });
        }
      } catch (e) {
        let errMsg = '请求出错：' + e.message;
        if (e.response && e.response.data) {
           if (e.response.data.error) errMsg += ` (${e.response.data.error})`;
           if (e.response.data.details) errMsg += `\n\n【诊断信息】\n${Array.isArray(e.response.data.details) ? e.response.data.details.join('\n') : JSON.stringify(e.response.data.details)}`;
        }
        this.messages.push({
          role: 'assistant',
          content: errMsg,
          failed: true,
          retry_message: userMessage,
        });
      } finally {
        this.loading = false;
        this.scrollToBottom();
      }
    },
    async retryFailedMessage(msg) {
      const retryMessage = (msg && msg.retry_message) || this.lastUserMessage;
      if (!retryMessage || this.loading) return;

      this.loading = true;
      try {
        const payload = {
          message: retryMessage,
          session_id: this.currentSessionId,
          retry: true,
        };
        const res = await axios.post('http://localhost:8000/api/recommend/', payload, { withCredentials: true });

        if (res.data.reply) {
          this.messages.push({ role: 'assistant', content: res.data.reply, audit: res.data.audit || null });
          if (!this.currentSessionId && res.data.session_id) {
            this.currentSessionId = res.data.session_id;
            this.currentTitle = res.data.session_title;
            this.fetchSessions();
          }
        } else {
          this.messages.push({
            role: 'assistant',
            content: '重试后仍未获取到推荐结果。' + (res.data.error || ''),
            failed: true,
            retry_message: retryMessage,
          });
        }
      } catch (e) {
        let errMsg = '重试请求出错：' + e.message;
        if (e.response && e.response.data) {
          if (e.response.data.error) errMsg += ` (${e.response.data.error})`;
          if (e.response.data.details) errMsg += `\n\n【诊断信息】\n${Array.isArray(e.response.data.details) ? e.response.data.details.join('\n') : JSON.stringify(e.response.data.details)}`;
        }
        this.messages.push({
          role: 'assistant',
          content: errMsg,
          failed: true,
          retry_message: retryMessage,
        });
      } finally {
        this.loading = false;
        this.scrollToBottom();
      }
    },
    scrollToBottom() {
      this.$nextTick(() => {
        const chatBox = this.$el.querySelector('.chat-box');
        if (chatBox) chatBox.scrollTop = chatBox.scrollHeight;
      });
    }
  }
}
</script>

<style scoped>
.forward-btn {
  margin-top: 10px;
  background: linear-gradient(135deg,#4d89ea,#3d74d1);
  color: white;
  border: none;
  padding: 7px 12px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  transition: background-color 0.2s;
  align-self: flex-start;
}

.retry-btn {
  margin-top: 10px;
  margin-right: 8px;
  background: #fff7e6;
  color: #ad6800;
  border: 1px solid #ffd591;
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
}
.retry-btn:hover {
  background: #ffe7ba;
}

.audit-warning {
  margin-top: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #fff5f5;
  border: 1px solid #ffd0d0;
  color: #c53030;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.warn-triangle {
  width: 16px;
  height: 14px;
  background: #ef4444;
  clip-path: polygon(50% 0, 0 100%, 100% 100%);
  position: relative;
  display: inline-block;
}
.warn-triangle::after {
  content: '!';
  position: absolute;
  left: 50%;
  top: 62%;
  transform: translate(-50%, -50%);
  color: #fff;
  font-size: 10px;
  font-weight: 800;
}
.forward-btn:hover {
  filter: brightness(.96);
}

.markdown-body {
  font-family: inherit;
  font-size: 14px;
}
.markdown-body p {
  margin: 0 0 10px 0;
}
.markdown-body p:last-child {
  margin-bottom: 0;
}
.markdown-body pre {
  background-color: #2b2b2b;
  color: #f8f8f2;
  padding: 10px;
  border-radius: 5px;
  overflow-x: auto;
}
.markdown-body code {
  background-color: rgba(0, 0, 0, 0.05);
  padding: 2px 4px;
  border-radius: 3px;
  font-family: monospace;
}
.message.assistant .markdown-body code {
  background-color: rgba(255, 255, 255, 0.5);
}
.markdown-body ul, .markdown-body ol {
  margin-top: 5px;
  margin-bottom: 10px;
  padding-left: 20px;
}
.markdown-body a {
  color: #1890ff;
  text-decoration: none;
}

.layout-container {
  display: flex;
  height: 680px;
  max-width: 1120px;
  margin: 0 auto;
  border: 1px solid #e7edf8;
  border-radius: 16px;
  overflow: hidden;
  background: #f7faff;
  box-shadow: 0 14px 34px rgba(77,98,141,.12);
}

.sidebar {
  width: 270px;
  background: linear-gradient(180deg,#ffffff,#f8fbff);
  border-right: 1px solid #e9effa;
  display: flex;
  flex-direction: column;
}

.new-chat-btn {
  margin: 15px;
  padding: 11px;
  background: #edf3ff;
  color: #2d5fc2;
  border: 1px solid #dbe6ff;
  border-radius: 10px;
  cursor: pointer;
  font-weight: bold;
  transition: .2s;
}
.new-chat-btn:hover { background: #e4edff; }

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 10px 10px 10px;
}

.session-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px;
  margin-bottom: 8px;
  background-color: #fff;
  border: 1px solid #edf1f8;
  border-radius: 10px;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.2s;
}
.session-item:hover { background-color: #f6f9ff; }
.session-item.active {
  background-color: #edf3ff;
  border-left: 4px solid #2e64ca;
}
.session-title {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 170px;
  color: #333;
}
.delete-icon {
  color: #999;
  font-size: 18px;
  font-weight: bold;
}
.delete-icon:hover { color: #dc3545; }

.chat-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 18px;
}
.chat-container h2 {
  margin: 0 0 12px;
  color: #253756;
}
.session-header-title { font-size: 14px; color: #666; font-weight: normal; }

.chat-box {
  flex: 1;
  overflow-y: auto;
  margin-bottom: 16px;
  padding: 15px;
  background: linear-gradient(180deg,#ffffff,#f9fbff);
  border: 1px solid #e9effa;
  border-radius: 12px;
}
.message { margin-bottom: 15px; }
.message.user { text-align: right; }
.message.assistant { text-align: left; }
.message-content {
  display: inline-block;
  padding: 10px 14px;
  border-radius: 12px;
  max-width: 85%;
  text-align: left;
  line-height: 1.5;
}
.message.user .message-content { background-color: #dfeaff; border: 1px solid #cddfff; }
.message.assistant .message-content { background-color: #f3f7ff; border: 1px solid #e3ebfa; }
pre { margin: 0; white-space: pre-wrap; word-wrap: break-word; font-family: inherit; }
.input-area { display: flex; gap: 10px; }
input[type="text"] { flex: 1; padding: 12px; border: 1px solid #d6e1f4; border-radius: 10px; font-size: 14px; outline: none; }
input[type="text"]:focus { border-color: #7aa2eb; box-shadow: 0 0 0 3px rgba(76,139,220,.16); }
button[type="submit"] { padding: 10px 20px; background: linear-gradient(135deg,#4d89ea,#3c74d1); color: white; border: none; border-radius: 10px; cursor: pointer; font-size: 14px; }
button:disabled { background-color: #6c757d; cursor: not-allowed; }
</style>
