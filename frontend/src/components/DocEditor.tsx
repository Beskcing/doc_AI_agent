/**
 * DOC 富文本编辑器
 * 基于 TinyMCE 的 Word 风格所见即所得编辑器
 *
 * TinyMCE 通过 tinymceScriptSrc 从 public 目录加载，
 * 插件/主题由 TinyMCE 自动从同目录加载，无需 npm import。
 */

import { useRef } from 'react'
import { Editor } from '@tinymce/tinymce-react'

interface DocEditorProps {
  /** 初始 HTML 内容 */
  initialHtml: string
  /** 内容变化回调 */
  onChange?: (html: string) => void
  /** 是否禁用 */
  disabled?: boolean
  /** 编辑器初始化完成回调，返回 editor 实例 */
  onEditorInit?: (editor: any) => void
  /** 编辑器加载后跳转到指定文本位置（如"第3段 / 3.1 条款"） */
  jumpToText?: string | null
}

/**
 * DOC 富文本编辑器组件
 * 提供 Word 风格的所见即所得编辑体验
 */
export default function DocEditor({ initialHtml, onChange, disabled, onEditorInit, jumpToText }: DocEditorProps) {
  const editorRef = useRef<any>(null)

  const handleEditorChange = (content: string) => {
    onChange?.(content)
  }

  return (
    <Editor
      tinymceScriptSrc="/tinymce/tinymce.min.js"
      licenseKey="gpl"
      value={initialHtml}
      onInit={(_evt, editor) => {
        editorRef.current = editor
        onEditorInit?.(editor)
        // 审查面板跳转：定位到指定文本位置
        if (jumpToText) {
          setTimeout(() => {
            try {
              const body = editor.getBody()
              const text = body.innerText || body.textContent || ''
              // 尝试在编辑器内容中搜索 location 描述的关键词
              const searchTerms = jumpToText
                .replace(/^第\d+段\s*[/]\s*/, '')  // 去掉"第N段 / "前缀
                .replace(/条款|段落|章节/g, '')
                .trim()
              if (searchTerms) {
                const idx = text.indexOf(searchTerms)
                if (idx >= 0) {
                  // 找到了匹配文本，滚动到对应位置
                  const range = document.createRange()
                  const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT)
                  let charCount = 0
                  let targetNode: Node | null = null
                  let targetOffset = 0
                  while (walker.nextNode()) {
                    const node = walker.currentNode
                    const nodeLen = (node.textContent || '').length
                    if (charCount + nodeLen > idx) {
                      targetNode = node
                      targetOffset = idx - charCount
                      break
                    }
                    charCount += nodeLen
                  }
                  if (targetNode) {
                    range.setStart(targetNode, Math.max(0, targetOffset))
                    range.collapse(true)
                    editor.selection.setRng(range)
                    editor.selection.scrollIntoView()
                  }
                }
              }
            } catch {
              // 定位失败静默处理
            }
            // 清除已使用的跳转标记
            sessionStorage.removeItem('review_jump_location')
          }, 500)  // 延迟等待编辑器完全渲染
        }
      }}
      onEditorChange={handleEditorChange}
      disabled={disabled}
      init={{
        height: 600,
        language: 'zh_CN',
        language_url: '/tinymce/langs/zh_CN.js',
        menubar: 'file edit view insert format tools table',
        plugins: [
          'advlist', 'autolink', 'lists', 'link', 'image',
          'table', 'code', 'wordcount',
        ],
        toolbar: [
          'undo redo | styles fontfamily fontsize | bold italic underline strikethrough | forecolor backcolor',
          'alignleft aligncenter alignright alignjustify | bullist numlist outdent indent | table | removeformat code',
        ].join(' | '),
        content_style: `
          body {
            font-family: "仿宋_GB2312", "FangSong_GB2312", "仿宋", FangSong, serif;
            font-size: 16pt;
            line-height: 1.5;
            margin: 2cm;
          }
          h1 { font-family: "黑体", SimHei, sans-serif; font-size: 16pt; font-weight: bold; }
          h2 { font-family: "黑体", SimHei, sans-serif; font-size: 16pt; font-weight: bold; }
          h3 { font-family: "黑体", SimHei, sans-serif; font-size: 16pt; font-weight: bold; }
          h4 { font-family: "黑体", SimHei, sans-serif; font-size: 16pt; font-weight: bold; }
          h5 { font-family: "黑体", SimHei, sans-serif; font-size: 16pt; font-weight: bold; }
          table { border-collapse: collapse; width: 100%; }
          table td, table th { border: 1px solid #000; padding: 4px 8px; }
        `,
        font_family_formats:
          '仿宋_GB2312=仿宋_GB2312,FangSong_GB2312,FangSong,仿宋;' +
          '宋体=宋体,SimSun,SimSun-ExtB;' +
          '黑体=黑体,SimHei;' +
          '楷体_GB2312=楷体_GB2312,KaiTi_GB2312,KaiTi,楷体;' +
          '微软雅黑=微软雅黑,Microsoft YaHei;' +
          'Arial=arial,helvetica,sans-serif;' +
          'Times New Roman=times new roman,times',
        font_size_formats: '初号=42pt 小初=36pt 一号=26pt 小一=24pt 二号=22pt 小二=18pt 三号=16pt 小三=15pt 四号=14pt 小四=12pt 五号=10.5pt 小五=9pt 六号=7.5pt 小六=6.5pt 七号=5.5pt 八号=5pt',
        style_formats: [
          { title: '正文', format: 'p' },
          { title: '一级标题', format: 'h1' },
          { title: '二级标题', format: 'h2' },
          { title: '三级标题', format: 'h3' },
          { title: '四级标题', format: 'h4' },
          { title: '五级标题', format: 'h5' },
        ],
        // 表格默认配置
        table_default_attributes: {
          border: '1',
          cellpadding: '4',
          cellspacing: '0',
          style: 'border-collapse: collapse;',
        },
        // 粘贴处理
        paste_data_images: true,
        // 自动保存
        autosave_ask_before_unload: true,
        // 品牌标识
        branding: false,
        // 状态栏
        statusbar: true,
        // 占位符
        placeholder: '在此编辑文档内容...',
      }}
    />
  )
}
