/**
 * 回归：SSE 帧分隔（与 planning.ts takeNextSseBlock 逻辑一致）
 * 运行：node scripts/test-macro-sse-frames.mjs
 */
function takeNextSseBlock(buffer) {
  const lfIdx = buffer.indexOf('\n\n')
  const crlfIdx = buffer.indexOf('\r\n\r\n')
  let sep = -1
  let sepLen = 2
  if (lfIdx !== -1 && (crlfIdx === -1 || lfIdx <= crlfIdx)) {
    sep = lfIdx
    sepLen = 2
  } else if (crlfIdx !== -1) {
    sep = crlfIdx
    sepLen = 4
  }
  if (sep < 0) return null
  return {
    block: buffer.slice(0, sep),
    rest: buffer.slice(sep + sepLen),
  }
}

function parseFrame(block) {
  let eventType = 'message'
  let dataStr = ''
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith('event: ')) eventType = line.slice(7).trim()
    else if (line.startsWith('data: ')) dataStr = line.slice(6)
  }
  return { eventType, data: dataStr ? JSON.parse(dataStr) : null }
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg)
}

// LF 帧（后端默认）
let buf =
  'event: status\ndata: {"phase":"running","message":"x"}\n\n' +
  'event: node\ndata: {"type":"part","part_index":0,"title":"P1"}\n\n'
let frames = []
while (true) {
  const t = takeNextSseBlock(buf)
  if (!t) break
  frames.push(parseFrame(t.block))
  buf = t.rest
}
assert(frames.length === 2, `expected 2 frames, got ${frames.length}`)
assert(frames[0].eventType === 'status', 'frame0 event')
assert(frames[1].data.title === 'P1', 'frame1 title')

// 纯 CRLF 帧
buf = 'event: node\r\ndata: {"type":"volume","part_index":0,"volume_index":0,"title":"V1"}\r\n\r\n'
frames = []
while (true) {
  const t = takeNextSseBlock(buf)
  if (!t) break
  frames.push(parseFrame(t.block))
  buf = t.rest
}
assert(frames.length === 1 && frames[0].data.title === 'V1', 'crlf frame')

// 半包：不应抛出
assert(takeNextSseBlock('event: node\ndata: {') === null, 'partial')

console.log('macro sse frame tests: ok')
