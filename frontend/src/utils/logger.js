const isDebug = import.meta.env.DEV

const logger = {
  debug: (...args) => {
    if (isDebug) console.debug(...args)
  },
  info: (...args) => {
    if (isDebug) console.info(...args)
  },
  warn: (...args) => console.warn(...args),
  error: (...args) => console.error(...args),
}

export default logger