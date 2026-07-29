/**
 * 打字机动画工具 - 将流式文本逐字输出
 *
 * 用法：
 *   const tw = createTypewriter(displayRef, sourceRef)
 *   tw.start()        // 开始逐字输出
 *   tw.clear()        // 停止并清空
 *   await tw.drain()  // 等待当前缓冲区输出完毕
 *
 * 双流模式（如 FundModal 的宏观+策略）：
 *   const macro = createTypewriter(macroDisplay, macroSource)
 *   const tier  = createTypewriter(tierDisplay, tierSource)
 *   macro.start(); tier.start()
 *   await tier.drain()
 */

export function createTypewriter(displayRef, sourceRef) {
  let timer = null

  function start() {
    clear(false)
    timer = setInterval(() => {
      const src = sourceRef.value
      const dst = displayRef.value
      if (dst.length < src.length) {
        // 自适应步进：积压多时加速，避免大段内容被动画拖住
        const backlog = src.length - dst.length
        const step = backlog > 200 ? 8 : backlog > 80 ? 4 : 2
        displayRef.value = src.slice(0, Math.min(src.length, dst.length + step))
      } else {
        clear(false)
      }
    }, 30)
  }

  function clear(resetDisplay = true) {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
    if (resetDisplay) {
      displayRef.value = ''
    }
  }

  function drain(timeoutMs = 30000) {
    return new Promise((resolve) => {
      if (displayRef.value.length >= sourceRef.value.length) {
        resolve()
        return
      }
      const start = Date.now()
      const check = () => {
        if (displayRef.value.length >= sourceRef.value.length) {
          resolve()
        } else if (Date.now() - start > timeoutMs) {
          resolve()
        } else {
          setTimeout(check, 50)
        }
      }
      check()
    })
  }

  return { start, clear, drain }
}
