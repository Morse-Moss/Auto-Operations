import { WechatOfficialDiscoveryPanel } from "./wechat-official-discovery-panel";
import { PlatformSectionPage } from "../../platform-core/shell/platform-section-page";

export function WechatOfficialDiscoveryPage() {
  return (
    <PlatformSectionPage
      platformLabel="微信公众号"
      title="公众号爆文发现"
      description="通过关键词、公众号或文章 URL 收集爆文候选，并把确认后的候选交给内容库。"
      safetyMessage="Redfox 是内容数据源，不是公众号发布通道"
      safetyDescription="爆文发现只收集候选并交给内容库；不补全正文、不拆解爆点、不创建草稿、不触发发布相关动作。"
    >
      <WechatOfficialDiscoveryPanel />
    </PlatformSectionPage>
  );
}
