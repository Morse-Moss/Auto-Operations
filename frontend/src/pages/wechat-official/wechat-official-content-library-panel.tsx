import { Select, Space, Typography } from "antd";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ContentLibraryShell, useContentLibrary } from "../../components/content-library";
import { createWechatOfficialContentLibraryAdapter } from "./wechat-official-content-library-adapter";
import { WECHAT_DRAFT_TEMPLATES } from "./wechat-official-draft-templates";

const { Text } = Typography;

export function WechatOfficialContentLibraryPanel() {
  const navigate = useNavigate();
  const [templateKey, setTemplateKey] = useState(WECHAT_DRAFT_TEMPLATES[0].template_key);
  const selectedTemplate = WECHAT_DRAFT_TEMPLATES.find((template) => template.template_key === templateKey) || WECHAT_DRAFT_TEMPLATES[0];
  const adapter = useMemo(() => createWechatOfficialContentLibraryAdapter(navigate, selectedTemplate), [navigate, selectedTemplate]);
  const controller = useContentLibrary(adapter);

  return (
    <ContentLibraryShell
      adapter={adapter}
      controller={controller}
      toolbarExtras={(
        <Space wrap align="center">
          <Text type="secondary">草稿模板</Text>
          <Select
            value={templateKey}
            onChange={setTemplateKey}
            style={{ width: 160 }}
            options={WECHAT_DRAFT_TEMPLATES.map((template) => ({ value: template.template_key, label: template.template_name }))}
          />
        </Space>
      )}
    />
  );
}
