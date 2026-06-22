import { useMemo } from "react";
import { useNavigate } from "react-router-dom";

import { ContentLibraryShell, useContentLibrary } from "../../components/content-library";
import { createWechatOfficialContentLibraryAdapter } from "./wechat-official-content-library-adapter";

export function WechatOfficialContentLibraryPanel() {
  const navigate = useNavigate();
  const adapter = useMemo(() => createWechatOfficialContentLibraryAdapter(navigate), [navigate]);
  const controller = useContentLibrary(adapter);

  return <ContentLibraryShell adapter={adapter} controller={controller} />;
}
