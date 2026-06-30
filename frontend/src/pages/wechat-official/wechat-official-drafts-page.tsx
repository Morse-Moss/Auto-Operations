import { WechatOfficialDraftWorkbench } from "./wechat-official-draft-workbench";
import { PlatformSectionPage } from "../../platform-core/shell/platform-section-page";

export function WechatOfficialDraftsPage() {
  return (
    <PlatformSectionPage
      platformLabel="微信公众号"
      title="公众号草稿工坊"
      description="基于内容库素材生成和管理公众号二创草稿。"
      safetyMessage="草稿工坊只做本地编辑、dry-run 校验与图片整理"
      safetyDescription="不上传公众号素材，不预览发送，不群发发布。"
    >
      <WechatOfficialDraftWorkbench />
    </PlatformSectionPage>
  );
}
