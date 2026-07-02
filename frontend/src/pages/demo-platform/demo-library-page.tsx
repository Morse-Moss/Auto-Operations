import { useMemo } from "react";

import { ContentLibraryShell, useContentLibrary } from "../../components/content-library";
import { PlatformSectionPage } from "../../platform-core/shell/platform-section-page";
import { createDemoPlatformContentLibraryAdapter } from "./demo-content-library-adapter";

export function DemoPlatformLibraryPage() {
  const adapter = useMemo(() => createDemoPlatformContentLibraryAdapter(), []);
  const controller = useContentLibrary(adapter);

  return (
    <PlatformSectionPage
      platformLabel="Demo Platform"
      title="Demo 内容库"
      description="通过本地 fixture 验证 Platform Core 共享内容库路径。"
      safetyMessage="Demo 平台只读"
      safetyDescription="不连接真实账号、Provider、凭据、发布、上传或后台自动化。"
    >
      <ContentLibraryShell adapter={adapter} controller={controller} />
    </PlatformSectionPage>
  );
}
