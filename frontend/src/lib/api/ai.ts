import { http } from "./client";
import type {
  Draft,
  DescribeImagePayload,
  GenerateNotePayload,
  GenerateCoverPayload,
  GenerateImagePayload,
  GenerateImageResult,
  GenerateImageTaskResult,
  GeneratedImageAsset,
  GenerateTagsPayload,
  GenerateTitlePayload,
  DoubaoMainModelConfigResult,
  ModelCapability,
  ModelCapabilityDefault,
  ModelConfig,
  ModelConfigPayload,
  ModelType,
  Paginated,
  PolishTextPayload,
  RewriteDraftPayload
} from "../../types";

export async function rewriteDraftWithAi(payload: RewriteDraftPayload): Promise<Draft> {
  const response = await http.post<Draft>("/ai/rewrite-note", payload);
  return response.data;
}

export async function generateNoteWithAi(payload: GenerateNotePayload): Promise<Draft> {
  const response = await http.post<Draft>("/ai/generate-note", payload);
  return response.data;
}

export async function generateTitleOptions(payload: GenerateTitlePayload): Promise<{ items: string[] }> {
  const response = await http.post<{ items: string[] }>("/ai/generate-title", payload);
  return response.data;
}

export async function generateTagOptions(payload: GenerateTagsPayload): Promise<{ items: string[] }> {
  const response = await http.post<{ items: string[] }>("/ai/generate-tags", payload);
  return response.data;
}

export async function polishTextWithAi(payload: PolishTextPayload): Promise<{ text: string }> {
  const response = await http.post<{ text: string }>("/ai/polish-text", payload);
  return response.data;
}

export async function fetchGeneratedImageAssets(): Promise<Paginated<GeneratedImageAsset>> {
  const response = await http.get<Paginated<GeneratedImageAsset>>("/ai/images/assets");
  return response.data;
}

export async function deleteGeneratedImageAsset(assetId: number): Promise<void> {
  await http.delete(`/ai/images/assets/${assetId}`);
}

export async function generateCoverWithAi(payload: GenerateCoverPayload): Promise<GeneratedImageAsset> {
  const response = await http.post<GeneratedImageAsset>("/ai/images/generate-cover", payload);
  return response.data;
}

export async function generateImageWithAi(payload: GenerateImagePayload, silent = false): Promise<GenerateImageResult> {
  const response = await http.post<GenerateImageResult>("/ai/images/generate", payload, { timeout: 600000, _silent: silent } as never);
  return response.data;
}

export async function startImageGenerationTask(payload: GenerateImagePayload): Promise<GenerateImageTaskResult> {
  const response = await http.post<GenerateImageTaskResult>("/ai/images/generate-async", payload);
  return response.data;
}

export async function describeImageWithAi(payload: DescribeImagePayload): Promise<{ text: string }> {
  const response = await http.post<{ text: string }>("/ai/images/describe", payload);
  return response.data;
}

export async function fetchModelConfigs(modelType?: ModelType): Promise<Paginated<ModelConfig>> {
  const response = await http.get<Paginated<ModelConfig>>("/model-configs", {
    params: modelType ? { model_type: modelType } : undefined
  });
  return response.data;
}

export async function createModelConfig(payload: ModelConfigPayload): Promise<ModelConfig> {
  const response = await http.post<ModelConfig>("/model-configs", payload);
  return response.data;
}

export async function fetchModelCapabilityDefaults(): Promise<{ items: ModelCapabilityDefault[] }> {
  const response = await http.get<{ items: ModelCapabilityDefault[] }>("/model-configs/capability-defaults");
  return response.data;
}

export async function setModelCapabilityDefault(
  capability: ModelCapability,
  modelConfigId: number
): Promise<ModelCapabilityDefault> {
  const response = await http.put<ModelCapabilityDefault>(`/model-configs/capability-defaults/${capability}`, {
    model_config_id: modelConfigId
  });
  return response.data;
}

export async function configureDoubaoMainModels(apiKey: string): Promise<DoubaoMainModelConfigResult> {
  const response = await http.post<DoubaoMainModelConfigResult>("/model-configs/doubao-main", { api_key: apiKey });
  return response.data;
}

export async function setDefaultModelConfig(configId: number): Promise<ModelConfig> {
  const response = await http.post<ModelConfig>(`/model-configs/${configId}/set-default`);
  return response.data;
}

export async function updateModelConfig(configId: number, payload: Partial<ModelConfigPayload>): Promise<ModelConfig> {
  const response = await http.patch<ModelConfig>(`/model-configs/${configId}`, payload);
  return response.data;
}

export async function testModelConfig(
  configId: number,
  capability?: ModelCapability
): Promise<{ id: number; status: string; message: string }> {
  const response = await http.post<{ id: number; status: string; message: string }>(`/model-configs/${configId}/test`, undefined, {
    params: capability ? { capability } : undefined
  });
  return response.data;
}

export async function deleteModelConfig(configId: number): Promise<{ id: number; status: string }> {
  const response = await http.delete<{ id: number; status: string }>(`/model-configs/${configId}`);
  return response.data;
}
