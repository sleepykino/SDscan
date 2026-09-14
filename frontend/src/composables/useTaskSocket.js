import { onBeforeUnmount, ref } from 'vue'
import { taskWsUrl } from '../api'

/**
 * 任务 WebSocket：自动重连，事件通过 onEvent 回调分发。
 */
export function useTaskSocket(taskId, onEvent) {
  const connected = ref(false)
  let ws = null
  let retry = 0
  let closed = false
  let timer = null

  function connect() {
    ws = new WebSocket(taskWsUrl(taskId))

    ws.onopen = () => {
      connected.value = true
      retry = 0
    }
    ws.onmessage = (evt) => {
      try {
        onEvent(JSON.parse(evt.data))
      } catch (e) {
        // 忽略无法解析的心跳/噪声
      }
    }
    ws.onclose = () => {
      connected.value = false
      if (!closed && retry < 5) {
        retry += 1
        timer = setTimeout(connect, 2000 * retry)
      }
    }
    ws.onerror = () => ws?.close()
  }

  function close() {
    closed = true
    if (timer) clearTimeout(timer)
    ws?.close()
  }

  connect()
  onBeforeUnmount(close)

  return { connected, close }
}
