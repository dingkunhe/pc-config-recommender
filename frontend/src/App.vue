<template>
  <div id="app" class="layout">
    <template v-if="currentTab === 'login' || currentTab === 'register'">
      <div class="full-screen-auth">
        <div class="auth-box">
          <h2 class="auth-title">{{ currentTab === 'login' ? '用户登录' : '用户注册' }}</h2>
          <div v-if="currentTab === 'login'" class="auth-form">
            <input v-model="loginForm.nickname" placeholder="昵称" class="auth-input" />
            <input v-model="loginForm.password" type="password" placeholder="密码" class="auth-input" />
            <button @click="handleLogin" class="auth-btn">登录</button>
            <div class="auth-switch">没有账号？<a @click="currentTab = 'register'">去注册</a></div>
            <div class="auth-switch"><a @click="switchForumTab('forum_square')" style="color:#999">暂不登录，游客访问</a></div>
          </div>
          
          <div v-else class="auth-form">
            <input v-model="registerForm.nickname" placeholder="昵称 (必填, 注册后不可修改)" class="auth-input" />
            <input v-model="registerForm.password" type="password" placeholder="密码 (必填)" class="auth-input" />
            <input v-model="registerForm.email" type="email" placeholder="邮箱 (必填)" class="auth-input" />
            <input v-model="registerForm.phone" placeholder="手机号 (必填)" class="auth-input" />
            <input v-model="registerForm.address" placeholder="联系地址 (必填)" class="auth-input" />
            <button @click="handleRegister" class="auth-btn">注册</button>
            <div class="auth-switch">已有账号？<a @click="currentTab = 'login'">去登录</a></div>
            <div class="auth-switch"><a @click="switchForumTab('forum_square')" style="color:#999">暂不登录，游客访问</a></div>
          </div>
        </div>
      </div>
    </template>

    <template v-else>
      <aside class="sidebar">
        <div class="logo-area">
          <div class="logo-title">配置推荐论坛</div>
          <div class="logo-subtitle">AI 驱动 · 社区共创</div>
        </div>
        <nav class="nav">
          <button class="recommend-btn" :class="{ active: isForumTab }" @click="forumMenuOpen = !forumMenuOpen">
            全部动态
            <span class="dropdown-arrow">{{ forumMenuOpen ? '▾' : '▸' }}</span>
          </button>
          <div v-show="forumMenuOpen" class="forum-submenu">
            <button class="submenu-btn" :class="{ active: currentTab === 'forum_square' }" @click="switchForumTab('forum_square')">交流广场</button>
            <button class="submenu-btn" :class="{ active: currentTab === 'forum_qa' }" @click="switchForumTab('forum_qa')">Q&amp;A</button>
            <button class="submenu-btn" :class="{ active: currentTab === 'forum_system' }" @click="switchForumTab('forum_system')">系统通知</button>
          </div>
          <button v-if="auth.loggedIn" class="recommend-btn" :class="{ active: currentTab === 'recommend' }" @click="currentTab = 'recommend'">智能推荐</button>
          <button v-if="auth.loggedIn" class="recommend-btn" :class="{ active: currentTab === 'myposts' }" @click="currentTab = 'myposts'">我的帖子</button>
          <button v-if="auth.loggedIn" class="recommend-btn" :class="{ active: currentTab === 'messages' }" @click="currentTab = 'messages'">
            我的消息
            <span v-if="(message.likesUnread + message.repliesUnread + message.systemUnread) > 0" class="alert-icon">!</span>
          </button>
          <button v-if="auth.loggedIn && auth.user && auth.user.is_staff" class="recommend-btn" :class="{ active: currentTab === 'manager' }" @click="currentTab = 'manager'">论坛管理</button>
          <button v-if="auth.loggedIn && auth.user && auth.user.is_staff" class="recommend-btn" :class="{ active: currentTab === 'recommend_manager' }" @click="currentTab = 'recommend_manager'">推荐系统管理</button>
          <button v-if="auth.loggedIn" class="recommend-btn" :class="{ active: currentTab === 'profile' }" @click="currentTab = 'profile'">个人中心</button>
        </nav>
      </aside>
      <div class="main">
        <header class="header">
          <div class="search">
            <select v-model="search.type" class="search-select">
              <option value="title">按名字搜索</option>
              <option value="author">按用户搜索</option>
            </select>
            <input v-model="search.query" :placeholder="searchPlaceholder" class="search-input" />
          </div>
          <div class="header-right">
            <span v-if="auth.loggedIn && auth.user" class="user-chip">
              <img v-if="auth.user.avatar_url" :src="auth.user.avatar_url" class="header-avatar" alt="avatar" />
              <span>{{ auth.user.nickname || auth.user.username }}</span>
            </span>
            <span v-if="!auth.loggedIn" @click="currentTab = 'login'" class="header-action primary">登录/注册</span>
            <span v-else @click="handleLogout" class="header-action danger">退出登录</span>
          </div>
        </header>

        <section class="content">
          <RecommendForm v-if="currentTab === 'recommend'" />
          
           <div v-if="isForumTab" class="panel-card">
            <Forum
              @open-auth="currentTab = 'login'"
              @nav-target-consumed="forumNavTarget = null"
              :nav-target="forumNavTarget"
              :board="currentForumBoard"
              :section-title="currentForumTitle"
            />
          </div>

           <div v-if="currentTab === 'myposts'" class="panel-card">
             <MyPosts />
          </div>

           <div v-if="currentTab === 'messages'" class="panel-card">
             <MyMessages @navigate-forum="handleNavigateForum" />
          </div>

           <div v-if="currentTab === 'manager'" class="panel-card">
             <Manager mode="forum" />
          </div>

           <div v-if="currentTab === 'recommend_manager'" class="panel-card">
             <Manager mode="recommend" />
          </div>
          <Profile v-if="currentTab === 'profile'" />
        </section>
      </div>
    </template>
  </div>
</template>

<script>
import RecommendForm from './components/RecommendForm.vue'
import Forum from './components/Forum.vue'
import Profile from './components/Profile.vue'
import MyPosts from './components/MyPosts.vue'
import MyMessages from './components/MyMessages.vue'
import axios from 'axios'
import { authState, searchState, messageState } from './store.js'
import Manager from './components/Manager.vue'

axios.interceptors.response.use(response => response, error => {
  if (error.response && error.response.status === 403 && error.response.data && error.response.data.error.includes('封禁')) {
    alert('你已被封禁，详情咨询管理员');
    authState.loggedIn = false;
    authState.user = null;
    window.location.reload();
  }
  return Promise.reject(error);
});

export default {
  components: { RecommendForm, Forum, Profile, MyPosts, MyMessages, Manager },
  data() {
    return { 
      currentTab: 'login',
      loginForm: { nickname: '', password: '' },
      registerForm: { nickname: '', password: '', email: '', phone: '', address: '' },
      auth: authState,
      search: searchState,
      message: messageState,
      unreadTimer: null,
      forumNavTarget: null,
      forumMenuOpen: true
    }
  },
  computed: {
    isForumTab() {
      return ['forum_square', 'forum_qa', 'forum_system'].includes(this.currentTab)
    },
    currentForumBoard() {
      if (this.currentTab === 'forum_qa') return 'qa'
      if (this.currentTab === 'forum_system') return 'system'
      return 'square'
    },
    currentForumTitle() {
      if (this.currentTab === 'forum_qa') return 'Q&A'
      if (this.currentTab === 'forum_system') return '系统通知'
      return '交流广场'
    },
    searchPlaceholder() {
      if (!this.isForumTab) return '在动态中搜索帖子或用户...'
      return `在${this.currentForumTitle}中搜索帖子或用户...`
    }
  },
  async mounted() {
    this.auth.loading = true;
    try {
      if (!sessionStorage.getItem('has_visited')) {
        // 首次访问该页面时（非刷新），主动清除可能残留的会话状态
        await axios.post('/api/logout/');
        sessionStorage.setItem('has_visited', 'true');
      }

      const res = await axios.get('/api/profile/');
      this.auth.loggedIn = true;
      this.auth.user = res.data.profile;
      await this.fetchUnreadCounts();
      this.startUnreadPolling();
      if (this.currentTab === 'login' || this.currentTab === 'register') {
        this.currentTab = 'forum_square';
      }
    } catch (e) {
      this.auth.loggedIn = false;
      this.auth.user = null;
      this.currentTab = 'login';
    } finally {
      this.auth.loading = false;
    }
  },
  beforeUnmount() {
    this.stopUnreadPolling();
  },
  methods: {
    switchForumTab(tab) {
      this.currentTab = tab
      this.forumMenuOpen = true
    },
    handleNavigateForum(target) {
      if (!target || !target.postId) return
      this.forumNavTarget = { ...target, _ts: Date.now() }
      this.switchForumTab('forum_square')
    },
    async fetchUnreadCounts() {
      if (!this.auth.loggedIn) {
        this.message.likesUnread = 0;
        this.message.repliesUnread = 0;
        this.message.systemUnread = 0;
        return;
      }
      try {
        const res = await axios.get('/api/messages/unread-counts/', { withCredentials: true });
        this.message.likesUnread = res.data.likes_unread || 0;
        this.message.repliesUnread = res.data.replies_unread || 0;
        this.message.systemUnread = res.data.system_unread || 0;
      } catch (e) {
        this.message.likesUnread = 0;
        this.message.repliesUnread = 0;
        this.message.systemUnread = 0;
      }
    },
    startUnreadPolling() {
      this.stopUnreadPolling();
      this.unreadTimer = setInterval(() => {
        this.fetchUnreadCounts();
      }, 15000);
    },
    stopUnreadPolling() {
      if (this.unreadTimer) {
        clearInterval(this.unreadTimer);
        this.unreadTimer = null;
      }
    },
    async handleLogout() {
      try {
        await axios.post('/api/logout/')
      } catch (e) {
        console.error(e)
      } finally {
        this.auth.loggedIn = false
        this.auth.user = null
        this.message.likesUnread = 0
        this.message.repliesUnread = 0
        this.message.systemUnread = 0
        this.forumNavTarget = null
        this.stopUnreadPolling()
        this.currentTab = 'login'
        this.search.query = ''
      }
    },
    async handleLogin() {
      if (!this.loginForm.nickname || !this.loginForm.password) {
        alert('请输入昵称和密码')
        return
      }
      try {
        const res = await axios.post('/api/login/', this.loginForm)
        this.auth.loggedIn = true
        this.auth.user = res.data.user
        this.forumNavTarget = null
        await this.fetchUnreadCounts()
        this.startUnreadPolling()
        this.switchForumTab('forum_square')
        this.search.query = ''
      } catch (e) { alert('登录失败:' + (e.response?.data?.error || e.message)) }
    },
    async handleRegister() {
      if (!this.registerForm.nickname || !this.registerForm.password || !this.registerForm.email || !this.registerForm.phone || !this.registerForm.address) {
        alert('所有个人信息均为必填项')
        return
      }
      try {
        await axios.post('/api/register/', this.registerForm)
        alert('注册成功，请登录')
        this.currentTab = 'login'
      } catch (e) { alert('注册失败:' + (e.response?.data?.error || e.message)) }
    }
  }
}
</script>

<style scoped>
.layout{display:flex;height:100vh;font-family:"Microsoft YaHei", Arial, Helvetica, sans-serif;background:linear-gradient(180deg,#f5f8ff 0%,#f7f9fc 45%,#f4f6fb 100%);color:#1f2937}
.sidebar{width:248px;background:rgba(255,255,255,.9);backdrop-filter:blur(8px);padding:12px;box-shadow:0 10px 30px rgba(72,94,144,.12);display:flex;flex-direction:column;border-right:1px solid #e8edf7}
.logo-area{padding:18px;border-radius:14px;background:linear-gradient(135deg,#eef4ff,#f7f9ff);border:1px solid #e4ebff}
.logo-title{font-size:21px;font-weight:700;color:#3566d6;text-align:center}
.logo-subtitle{font-size:12px;color:#7a88a1;text-align:center;margin-top:6px}
.nav{margin-top:14px;display:flex;flex-direction:column;flex:1;gap:8px}
.recommend-btn{width:100%;padding:12px 14px;border:none;background:transparent;text-align:left;font-size:15px;cursor:pointer;transition:all .22s ease;display:flex;align-items:center;border-radius:12px;color:#415069}
.recommend-btn:hover,.recommend-btn.active{background:linear-gradient(135deg,#edf3ff,#f5f8ff);color:#3566d6;box-shadow:inset 0 0 0 1px #dae6ff}
.recommend-btn::before{content:"✦";margin-right:10px;color:#9ab2e9;font-size:15px}
.recommend-btn.active::before{color:#3566d6}
.dropdown-arrow{margin-left:auto;font-size:16px;font-weight:800;line-height:1;color:#3e5f9f;background:#e8f0ff;border:1px solid #cfe0ff;border-radius:999px;padding:2px 6px;min-width:20px;text-align:center}
.forum-submenu{display:flex;flex-direction:column;gap:6px;margin:-2px 0 2px 0;padding-left:18px}
.submenu-btn{padding:8px 10px;border:1px solid #e4ebfa;background:#f9fbff;color:#4b5c78;border-radius:10px;text-align:left;cursor:pointer;font-size:13px;transition:all .2s ease}
.submenu-btn:hover,.submenu-btn.active{background:#edf3ff;color:#315ebf;border-color:#d8e4ff}
.alert-icon{margin-left:auto;display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#ef4444;color:#fff;font-size:12px;font-weight:700;line-height:1}
.main{flex:1;display:flex;flex-direction:column}
.header{height:68px;background:rgba(255,255,255,.85);backdrop-filter:blur(6px);display:flex;align-items:center;justify-content:space-between;padding:0 22px;box-shadow:0 2px 18px rgba(86,102,136,.08);z-index:10;border-bottom:1px solid #e8edf7}
.search{display:flex;align-items:center;gap:10px}
.search-select,.search-input{border:1px solid #d7e1f4;background:#fff;outline:none;transition:all .2s ease;border-radius:12px}
.search-select{padding:9px 12px;cursor:pointer;color:#374151}
.search-input{width:420px;padding:9px 14px}
.search-input:focus,.search-select:focus{border-color:#85a7ea;box-shadow:0 0 0 3px rgba(76,139,220,.15)}
.header-right{display:flex;align-items:center;gap:10px}
.user-chip{background:#eef3ff;color:#365fbc;border:1px solid #dbe6ff;padding:4px 10px;border-radius:999px;font-size:13px;display:inline-flex;align-items:center;gap:8px}
.header-avatar{width:24px;height:24px;border-radius:50%;object-fit:cover;border:1px solid #d6e2fb}
.header-action{cursor:pointer;font-weight:700;padding:8px 12px;border-radius:10px;transition:all .2s ease}
.header-action.primary{color:#3566d6;background:#eef3ff}
.header-action.primary:hover{background:#e4edff}
.header-action.danger{color:#dc2626;background:#fff0f0}
.header-action.danger:hover{background:#ffe5e5}
.content{flex:1;padding:20px;overflow:auto}
.panel-card{background:rgba(255,255,255,.95);padding:20px;border-radius:16px;border:1px solid #e8edf7;box-shadow:0 10px 25px rgba(82,98,128,.08)}

.full-screen-auth {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: radial-gradient(circle at 20% 20%, #eaf1ff, #f7f9ff 45%, #f0f2f8 100%);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}
.auth-box {
  background: rgba(255,255,255,.95);
  padding: 40px;
  border-radius: 18px;
  box-shadow: 0 18px 45px rgba(73,94,138,.16);
  border: 1px solid #e7ecf8;
  width: 400px;
}
.auth-title {
  text-align: center;
  margin-bottom: 30px;
  color: #1f2b46;
}
.auth-form {
  display: flex;
  flex-direction: column;
}
.auth-input {
  padding: 12px;
  margin-bottom: 15px;
  border: 1px solid #d9e2f2;
  border-radius: 10px;
  font-size: 14px;
  background:#fbfcff;
}
.auth-input:focus {
  border-color: #7ea3ea;
  box-shadow: 0 0 0 3px rgba(91,136,220,0.15);
  outline: none;
}
.auth-btn {
  background: linear-gradient(135deg,#4c8bdc,#3b74d4);
  color: white;
  border: none;
  padding: 12px;
  border-radius: 10px;
  font-size: 16px;
  cursor: pointer;
  margin-top: 10px;
  box-shadow: 0 8px 20px rgba(76,139,220,0.28);
}
.auth-btn:hover {
  filter: brightness(.96);
}
.auth-switch {
  text-align: center;
  margin-top: 15px;
  font-size: 14px;
  color: #666;
}
.auth-switch a {
  color: #4c8bdc;
  cursor: pointer;
  text-decoration: none;
}
.auth-switch a:hover {
  text-decoration: underline;
}
</style>
