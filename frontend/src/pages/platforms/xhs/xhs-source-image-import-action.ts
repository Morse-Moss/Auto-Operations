export type XhsSourceImageImportResult = {
  total_source_image_count: number;
  imported_count: number;
  skipped_count: number;
  downloaded_count: number;
  failed_count: number;
};

type NoticeKind = "success" | "warning" | "error";

type XhsSourceImageImportActionDependencies = {
  importImages: () => Promise<XhsSourceImageImportResult>;
  refreshSelectedItem: () => Promise<unknown>;
  setBusy: (busy: boolean) => void;
  setDetailError: (error: string | null) => void;
  setDetailActionMessage: (message: string | null) => void;
  notify: (kind: NoticeKind, message: string) => void;
};

export function getActionErrorMessage(error: unknown): string {
  const responseData = typeof error === "object" && error !== null && "response" in error
    ? (error as { response?: { data?: unknown } }).response?.data
    : null;
  if (typeof responseData === "object" && responseData !== null && "detail" in responseData) {
    const detail = (responseData as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail.trim();
    if (typeof detail === "object" && detail !== null && "message" in detail) {
      const messageText = detail.message;
      if (typeof messageText === "string" && messageText.trim()) return messageText.trim();
    }
  }
  return error instanceof Error ? error.message : "未知错误";
}

export async function runXhsSourceImageImportAction({
  importImages,
  refreshSelectedItem,
  setBusy,
  setDetailError,
  setDetailActionMessage,
  notify,
}: XhsSourceImageImportActionDependencies): Promise<void> {
  setBusy(true);
  setDetailError(null);
  setDetailActionMessage("正在自动补全原文图片...");
  try {
    const result = await importImages();
    if (result.total_source_image_count === 0) {
      throw new Error("原文详情未返回可补全的图片。");
    }

    await refreshSelectedItem();
    const counts = `新增 ${result.imported_count} 张，已存在 ${result.skipped_count} 张，已保存 ${result.downloaded_count} 张，失败 ${result.failed_count} 张。`;
    if (result.failed_count > 0) {
      const summary = `原文图片处理完成（部分失败）：${counts}`;
      setDetailError("部分图片保存失败，请稍后重试。");
      setDetailActionMessage(summary);
      notify("warning", summary);
      return;
    }

    const summary = `原文图片补全完成：${counts}`;
    setDetailError(null);
    setDetailActionMessage(summary);
    notify("success", summary);
  } catch (error) {
    const errorMessage = `自动补全原文图片失败：${getActionErrorMessage(error)}`;
    setDetailError(errorMessage);
    setDetailActionMessage(null);
    notify("error", errorMessage);
  } finally {
    setBusy(false);
  }
}
