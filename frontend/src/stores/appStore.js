/**
 * 统一入口 — 组合 fund / config / chat 三个 store
 * 组件可直接 import { useFundStore, useConfigStore, useChatStore } from '../stores/appStore'
 */
export { useFundStore } from './fundStore'
export { useConfigStore } from './configStore'
export { useChatStore } from './chatStore'