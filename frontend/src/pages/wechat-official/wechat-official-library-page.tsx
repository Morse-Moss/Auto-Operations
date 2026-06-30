import { WechatOfficialContentLibraryPanel } from "./wechat-official-content-library-panel";
import { PlatformSectionPage } from "../../platform-core/shell/platform-section-page";

export function WechatOfficialLibraryPage() {
  return (
    <PlatformSectionPage
      platformLabel="微信公众号"
      title="公众号内容库"
      description="管理已入库的公众号文章，补全素材、拆解爆点并生成独立草稿。"
      safetyMessage="内容库只处理素材、分析和草稿生产"
      safetyDescription="真实公众号发布、素材上传、预览发送、群发发布仍保持阻断。"
    >
      <WechatOfficialContentLibraryPanel />
    </PlatformSectionPage>
  );
}
