"""切片策略单元测试"""

from langchain_core.documents import Document

from src.rag.chunking_strategy import StandardsChunker


class TestStandardsChunker:
    """StandardsChunker 测试"""

    def setup_method(self):
        self.chunker = StandardsChunker(chunk_size=700, chunk_overlap_ratio=0.15)

    def test_short_document_no_split(self):
        """短文档不切片"""
        doc = Document(page_content="短文档", metadata={"source": "test.md"})
        result = self.chunker.split_documents([doc])
        assert len(result) == 1
        assert result[0].page_content == "短文档"

    def test_split_by_headings(self):
        """按标题边界切片"""
        content = "## 第一章\n" + "这是一段足够长的内容。" * 200 + "\n\n## 第二章\n" + "这是另一段足够长的内容。" * 200
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = self.chunker.split_documents([doc])
        assert len(result) >= 2

    def test_long_section_split_by_paragraphs(self):
        """超长章节按段落切片"""
        paragraphs = [f"这是第 {i} 段的内容，包含足够的文字来满足切片条件。" * 10 for i in range(20)]
        content = "\n\n".join(paragraphs)
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = self.chunker.split_documents([doc])
        assert len(result) > 1

    def test_metadata_preserved(self):
        """元数据保留"""
        doc = Document(
            page_content="内容" * 200,
            metadata={"source": "test.md", "section_title": "第一章"},
        )
        result = self.chunker.split_documents([doc])
        for chunk in result:
            assert chunk.metadata.get("source") == "test.md"

    def test_chunk_indices(self):
        """chunk 索引正确"""
        paragraphs = [f"段落 {i} 内容" * 20 for i in range(10)]
        content = "\n\n".join(paragraphs)
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = self.chunker.split_documents([doc])
        for i, chunk in enumerate(result):
            assert chunk.metadata.get("chunk_index") == i
