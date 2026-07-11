from pathlib import Path


def test_model_config_frontend_exposes_explicit_capability_routing_contract():
    types_source = Path("frontend/src/types/index.ts").read_text(encoding="utf-8")
    api_source = Path("frontend/src/lib/api.ts").read_text(encoding="utf-8")

    assert (
        'export type ModelCapability = "text" | "vision" | "image_generation"'
        in types_source
    )
    assert "supported_capabilities: ModelCapability[]" in types_source
    assert "assigned_capabilities: ModelCapability[]" in types_source
    assert "export type ModelCapabilityDefault" in types_source
    assert "fetchModelCapabilityDefaults" in api_source
    assert "setModelCapabilityDefault" in api_source
    assert "capability" in api_source


def test_model_config_page_uses_capability_routes_instead_of_type_defaults():
    page_source = Path(
        "frontend/src/pages/models/model-config-page.tsx"
    ).read_text(encoding="utf-8")

    assert "能力路由" in page_source
    assert "文本生成" in page_source
    assert "图片理解" in page_source
    assert "图片生成" in page_source
    assert "fetchModelCapabilityDefaults" in page_source
    assert "setModelCapabilityDefault" in page_source
    assert "assigned_capabilities" in page_source
    assert "图片生成连接测试会真实调用上游，可能消耗上游额度。" in page_source
    assert "setDefaultModelConfig" not in page_source
    assert "设为该类型默认模型" not in page_source
