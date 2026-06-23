from backend.app.services.xhs_content_normalizer import normalize_xhs_generated_content


def test_removes_repeated_title_from_body_start():
    result = normalize_xhs_generated_content(
        title="SaaS 工具怎么选？",
        body="SaaS 工具怎么选？\n\n正文第一段...",
        tags=[],
    )

    assert result.title == "SaaS 工具怎么选？"
    assert result.body == "正文第一段..."
    assert "removed_repeated_title" in result.warnings


def test_removes_markdown_title_and_bold_symbols():
    result = normalize_xhs_generated_content(
        title="浴缸怎么选",
        body="# 浴缸怎么选\n\n**重点**\n- 尺寸\n* 材质",
        tags=[],
    )

    assert result.body == "重点\n尺寸\n材质"
    assert "#" not in result.body
    assert "**" not in result.body


def test_removes_introductory_content_prefixes():
    result = normalize_xhs_generated_content(
        title="标题",
        body="以下是适合小红书发布的内容：\n正文：\n第一段内容",
        tags=[],
    )

    assert result.body == "第一段内容"


def test_deduplicates_tags_without_fabricating_new_tags():
    result = normalize_xhs_generated_content(
        title="标题",
        body="正文",
        tags=[{"name": "浴缸"}, {"id": "1", "name": "浴缸"}, {"name": "装修"}, {"name": ""}],
    )

    assert result.tags == [{"name": "浴缸"}, {"name": "装修"}]


def test_strips_hashtag_prefix_and_space_before_deduplicating_tags():
    result = normalize_xhs_generated_content(
        title="标题",
        body="正文",
        tags=["# 浴缸", "浴缸", {"name": "# 装修"}],
    )

    assert result.tags == [{"name": "浴缸"}, {"name": "装修"}]


def test_preserves_xhs_hashtag_line_in_body():
    result = normalize_xhs_generated_content(
        title="标题",
        body="#浴缸 #装修\n正文",
        tags=[],
    )

    assert result.body == "#浴缸 #装修\n正文"
