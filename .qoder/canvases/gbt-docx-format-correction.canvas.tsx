import { Callout, Divider, Grid, H1, H2, Pill, Stat, Stack, Table, Text } from 'qoder/canvas';

export default function GbtDocxFormatCorrection() {
  const docs = [
    {
      name: 'GB_T_23347-2021CN',
      title: '橄榄油、油橄榄果渣油',
      paragraphs: 232,
      headings: 60,
      coverLength: 5,
      prefaceBody: 148,
    },
    {
      name: 'GB_T_11856.2-2023CN',
      title: '蒸馏酒质量要求 第2部分: 白兰地',
      paragraphs: 581,
      headings: 195,
      coverLength: 6,
      prefaceBody: 346,
    },
    {
      name: 'GB_8538-2022CN',
      title: '食品安全国家标准 天然矿泉水检验方法',
      paragraphs: 4472,
      headings: 2447,
      coverLength: 4,
      prefaceBody: 1811,
    },
  ];

  const totalParagraphs = docs.reduce((sum, d) => sum + d.paragraphs, 0);
  const totalHeadings = docs.reduce((sum, d) => sum + d.headings, 0);

  return (
    <Stack gap={20}>
      <H1>GB/T 文档格式修正报告</H1>

      <Grid columns={3} gap={16}>
        <Stat label="处理文档数" value="3" tone="primary" />
        <Stat label="总段落数" value={totalParagraphs.toLocaleString()} />
        <Stat label="编号标题总数" value={totalHeadings.toLocaleString()} />
      </Grid>

      <Divider />

      <H2>工作流程</H2>
      <Table
        headers={['步骤', '操作', '输出']}
        rows={[
          ['Task 1', '分析三份 MinerU 文档当前格式', 'output/json/ + output/markdown/'],
          ['Task 2', '应用 GB/T 标准格式化', 'GB_T_*.docx / GB_*.docx'],
          ['Task 3', '验证修正后格式参数', 'output_verify/json/ + output_verify/markdown/'],
          ['Task 4', '更新 AGENTS.md + Git 提交', 'commit 56b3128'],
        ]}
      />

      <Callout type="warning" title="关键 Bug 修复">
        <Stack gap={8}>
          <Text>
            <strong>问题：</strong>classify_paragraph() 硬编码「前言」位置为 cover_start+5，但不同文档封面结构差异大（3-6 段）。
          </Text>
          <Text>
            <strong>修复：</strong>新增 _find_preface_index() 动态扫描「前言」位置；重构 apply_cover_format() 改为基于内容检测（国家标准、GB编号、日期、代替行、英文标题）。
          </Text>
        </Stack>
      </Callout>

      <Divider />

      <H2>文档详情</H2>
      <Table
        headers={['标准号', '中文名称', '段落数', '封面段数', '前言正文段数', '编号标题数']}
        rows={docs.map(d => [
          d.name,
          d.title,
          d.paragraphs.toLocaleString(),
          d.coverLength.toString(),
          d.prefaceBody.toLocaleString(),
          d.headings.toLocaleString(),
        ])}
      />

      <Divider />

      <H2>验证结果</H2>
      <Grid columns={2} gap={16}>
        <Stack gap={8}>
          <Pill tone="success">页面设置</Pill>
          <Text>A4 纵向，25mm 边距</Text>
        </Stack>
        <Stack gap={8}>
          <Pill tone="success">字体</Pill>
          <Text>宋体 + Times New Roman，10.5pt</Text>
        </Stack>
        <Stack gap={8}>
          <Pill tone="success">正文对齐</Pill>
          <Text>两端对齐 (JUSTIFY)，首行缩进 21pt</Text>
        </Stack>
        <Stack gap={8}>
          <Pill tone="success">编号标题</Pill>
          <Text>两空格分隔，两端对齐，不加粗</Text>
        </Stack>
        <Stack gap={8}>
          <Pill tone="success">前言标题</Pill>
          <Text>16pt 黑体，居中 (CENTER)</Text>
        </Stack>
        <Stack gap={8}>
          <Pill tone="success">封面</Pill>
          <Text>左对齐 (LEFT)，动态长度检测</Text>
        </Stack>
      </Grid>

      <Divider />

      <H2>输出文件</H2>
      <Stack gap={8}>
        <Pill tone="info">GB_T_23347-2021CN.docx</Pill>
        <Pill tone="info">GB_T_11856.2-2023CN.docx</Pill>
        <Pill tone="info">GB_8538-2022CN.docx</Pill>
      </Stack>

      <Text tone="secondary" size="small">生成时间：2026-07-08 | Commit: 56b3128</Text>
    </Stack>
  );
}
