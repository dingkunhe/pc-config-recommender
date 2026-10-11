import { reactive } from 'vue'

export const authState = reactive({
  loggedIn: false,
  user: null,
  loading: false
})

export const searchState = reactive({
  query: '',
  type: 'title'
})

export const messageState = reactive({
  likesUnread: 0,
  repliesUnread: 0,
  systemUnread: 0
})
