<template>
  <div class="profile-page">
    <div class="panel">
      <h3>个人中心</h3>
      <form @submit.prevent="save">
        <div class="row avatar-row">
          <label>头像</label>
          <div class="avatar-panel">
            <div class="avatar-preview">
              <img v-if="avatarPreview || form.avatar_url" :src="avatarPreview || form.avatar_url" alt="avatar" />
              <span v-else>暂无头像</span>
            </div>
            <div class="avatar-actions">
              <input type="file" ref="avatarInput" accept="image/*" @change="onAvatarSelected" />
              <button type="button" @click="triggerAvatarPicker">选择头像</button>
              <button type="button" class="danger-btn" @click="removeAvatar">移除头像</button>
            </div>
          </div>
        </div>
        <div class="row">
          <label>昵称</label>
          <input v-model="form.nickname" disabled />
          <span style="font-size: 12px; color: #999; margin-left: 8px;">(不可修改)</span>
        </div>
        <div class="row"><label>邮箱</label><input v-model="form.email" /></div>
        <div class="row"><label>电话</label><input v-model="form.phone" /></div>
        <div class="row"><label>地址</label><input v-model="form.address" /></div>
        <div class="row"><label>新密码</label><input type="password" v-model="form.new_password" placeholder="不修改请留空" /></div>
        <div class="row"><label>确认密码</label><input type="password" v-model="form.confirm_password" placeholder="不修改请留空" /></div>
        <div class="actions">
          <button type="submit">保存</button>
        </div>
      </form>
      <div v-if="isAdmin"></div>
        <div v-else class="admin-area">
        <h4>激活管理员账户</h4>
        <div v-if="!showActiveAdminCode">
          <button @click="showActiveAdminCode = true">激活管理员账户</button>
        </div>
        <div v-else class="row">
          <input v-model="activeAdminCode" placeholder="请输入激活码" />
          <button @click="activateAdmin">确认激活</button>
        </div>
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
      form: { nickname: '', email: '', phone: '', address: '', avatar_url: '', new_password: '', confirm_password: '' },
      isAdmin: false,
      showActiveAdminCode: false,
      activeAdminCode: '',
      avatarFile: null,
      avatarPreview: '',
      shouldRemoveAvatar: false,
      auth: authState
    }
  },
  beforeUnmount() {
    if (this.avatarPreview) URL.revokeObjectURL(this.avatarPreview)
  },
  async mounted(){
    await this.loadProfile()
  },
  methods: {
    triggerAvatarPicker() {
      if (this.$refs.avatarInput) this.$refs.avatarInput.click()
    },
    onAvatarSelected(e) {
      const file = e?.target?.files?.[0]
      if (!file) return
      if (!file.type.startsWith('image/')) {
        alert('请选择图片文件')
        e.target.value = ''
        return
      }
      if (file.size > 5 * 1024 * 1024) {
        alert('头像大小不能超过 5MB')
        e.target.value = ''
        return
      }
      this.avatarFile = file
      this.shouldRemoveAvatar = false
      if (this.avatarPreview) URL.revokeObjectURL(this.avatarPreview)
      this.avatarPreview = URL.createObjectURL(file)
    },
    removeAvatar() {
      this.avatarFile = null
      this.shouldRemoveAvatar = true
      if (this.avatarPreview) {
        URL.revokeObjectURL(this.avatarPreview)
        this.avatarPreview = ''
      }
      this.form.avatar_url = ''
      if (this.$refs.avatarInput) this.$refs.avatarInput.value = ''
    },
    async loadProfile(){
      try{
        const res = await axios.get('/api/profile/', { withCredentials: true })
        this.form.nickname = res.data.profile.nickname || ''
        this.form.email = res.data.profile.email || ''
        this.form.phone = res.data.profile.phone || ''
        this.form.address = res.data.profile.address || ''
        this.form.avatar_url = res.data.profile.avatar_url || ''
        this.shouldRemoveAvatar = false
        this.isAdmin = res.data.profile.is_staff === true
        if (this.auth.user) {
          this.auth.user.avatar_url = this.form.avatar_url
          this.auth.user.nickname = this.form.nickname || this.auth.user.nickname
          this.auth.user.email = this.form.email || this.auth.user.email
        }
      }catch(e){
        console.error(e)
      }
    },
    async save(){
      if (this.form.new_password) {
        if (this.form.new_password !== this.form.confirm_password) {
          alert('新密码和确认密码不一致')
          return
        }
      }
      try{
        const fd = new FormData()
        fd.append('nickname', this.form.nickname || '')
        fd.append('email', this.form.email || '')
        fd.append('phone', this.form.phone || '')
        fd.append('address', this.form.address || '')
        fd.append('new_password', this.form.new_password || '')
        if (this.avatarFile) fd.append('avatar', this.avatarFile)
        if (this.shouldRemoveAvatar) fd.append('remove_avatar', '1')

        const res = await axios.post('/api/profile/', fd, { withCredentials: true })
        alert('保存成功')
        this.form.avatar_url = res.data?.profile?.avatar_url || this.form.avatar_url
        if (this.auth.user && res.data?.profile) {
          this.auth.user.avatar_url = res.data.profile.avatar_url || ''
          this.auth.user.nickname = res.data.profile.nickname || this.auth.user.nickname
          this.auth.user.email = res.data.profile.email || this.auth.user.email
          this.auth.user.phone = res.data.profile.phone || this.auth.user.phone
          this.auth.user.address = res.data.profile.address || this.auth.user.address
        }
        this.avatarFile = null
        this.shouldRemoveAvatar = false
        if (this.avatarPreview) {
          URL.revokeObjectURL(this.avatarPreview)
          this.avatarPreview = ''
        }
        if (this.$refs.avatarInput) this.$refs.avatarInput.value = ''
        if (this.form.new_password) {
          this.form.new_password = ''
          this.form.confirm_password = ''
        }
      }catch(e){ alert('保存失败：'+(e.response?.data?.error||e.message)) }
    },

    async activateAdmin() {
      if (!this.activeAdminCode) return
      try {
        const res = await axios.post('/api/activate-admin/', { code: this.activeAdminCode }, { withCredentials: true })
        if (res.data.status === 'ok') {
          alert('激活成功')
          this.isAdmin = true
          this.showActiveAdminCode = false
          // You could also refresh global auth state if needed, but locally isAdmin is enough to show the UI
          await this.loadProfile()
        }
      } catch(e) { 
        alert('激活失败: ' + (e.response?.data?.error || e.message)) 
      }
    }
  }
}
</script>

<style scoped>
.profile-page {
  background: rgba(255,255,255,.96);
  padding: 20px;
  border-radius: 16px;
  border: 1px solid #e8edf7;
  box-shadow: 0 12px 28px rgba(83,99,130,.1);
}
.panel{position:relative;background:#fff;padding:22px;border-radius:12px;max-width:700px;border:1px solid #edf1f8}
.panel h3{margin-top:0;color:#253756}
.row{display:flex;align-items:center;margin:12px 0;gap:10px}
.row label{width:70px;color:#4a5a76;font-weight:600}
.row input{flex:1;padding:9px 12px;border:1px solid #d7e1f3;border-radius:10px;background:#fbfcff}
.avatar-row{align-items:flex-start}
.avatar-panel{display:flex;gap:12px;align-items:center;flex:1}
.avatar-preview{width:84px;height:84px;border-radius:50%;overflow:hidden;border:1px solid #d7e1f3;background:#f4f8ff;display:flex;align-items:center;justify-content:center;color:#7a88a1;font-size:12px}
.avatar-preview img{width:100%;height:100%;object-fit:cover}
.avatar-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.avatar-actions input{display:none}
.row input:focus{outline:none;border-color:#7da2e9;box-shadow:0 0 0 3px rgba(76,139,220,.15)}
.actions{display:flex;gap:8px;margin-top:14px}
.actions button,.admin-area button{background:linear-gradient(135deg,#4c8bdc,#3a74d1);color:#fff;border:none;padding:8px 14px;border-radius:10px;cursor:pointer}
.danger-btn{background:linear-gradient(135deg,#f06a6a,#dc4e4e)!important}
.admin-area{margin-top:20px;padding-top:14px;border-top:1px dashed #e5eaf6}
.admin-area h4{margin:0 0 10px;color:#2f4062}
</style>
