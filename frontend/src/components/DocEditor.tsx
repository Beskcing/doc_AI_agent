/**
 * DOC 富文本编辑器
 * 基于 TinyMCE 的 Word 风格所见即所得编辑器
 */

import { useRef } from 'react'
import { Editor } from '@tinymce/tinymce-react'

// 导入 TinyMCE 主题和图标
import 'tinymce/themes/silver/theme'
import 'tinymce/icons/default'
import 'tinymce/models/dom'

// 导入必要的插件
import 'tinymce/plugins/advlist'
import 'tinymce/plugins/autolink'
import 'tinymce/plugins/lists'
import 'tinymce/plugins/link'
import 'tinymce/plugins/image'
import 'tinymce/plugins/table'
import 'tinymce/plugins/code'
import 'tinymce/plugins/wordcount'

interface DocEditorProps {
  /** 初始 HTML 内容 */
  initialHtml: string
  /** 内容变化回调 */
  onChange?: (html: string) => void
  /** 是否禁用 */
  disabled?: boolean
}

/**
 * DOC 富文本编辑器组件
 * 提供 Word 风格的所见即所得编辑体验
 */
export default function DocEditor({ initialHtml, onChange, disabled }: DocEditorProps) {
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
        font_formats:
          '仿宋_GB2312=仿宋_GB2312,FangSong_GB2312,FangSong,仿宋;' +
          '宋体=宋体,SimSun,SimSun-ExtB;' +
          '黑体=黑体,SimHei;' +
          '楷体_GB2312=楷体_GB2312,KaiTi_GB2312,KaiTi,楷体;' +
          '微软雅黑=微软雅黑,Microsoft YaHei;' +
          'Arial=arial,helvetica,sans-serif;' +
          'Times New Roman=times new roman,times',
        fontsize_formats: '10pt 12pt 14pt 16pt 18pt 22pt 26pt 32pt 36pt',
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
