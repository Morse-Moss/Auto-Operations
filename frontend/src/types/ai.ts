export type ModelType = "text" | "image";
export type ModelCapability = "text" | "vision" | "image_generation";

export type ModelConfig = {
  id: number;
  name: string;
  model_type: ModelType;
  provider: string;
  model_name: string;
  base_url: string;
  has_api_key: boolean;
  is_default: boolean;
  supported_capabilities: ModelCapability[];
  assigned_capabilities: ModelCapability[];
};

export type ModelCapabilityDefault = {
  capability: ModelCapability;
  model_config: ModelConfig | null;
  status: "configured" | "not_configured" | "invalid";
};

export type ModelConfigPayload = {
  name: string;
  model_type: ModelType;
  provider: string;
  model_name: string;
  base_url: string;
  api_key: string;
  is_default: boolean;
};

export type DoubaoMainModelConfigResult = {
  text: ModelConfig;
  vision: ModelConfig;
};

export type RewriteDraftPayload = {
  draft_id: number;
  mode?: "safe" | "polish" | "seed";
  instruction?: string;
};

export type GenerateNotePayload = {
  platform?: "xhs";
  topic: string;
  reference?: string;
  instruction?: string;
};

export type GenerateTitlePayload = {
  title?: string;
  body: string;
  count?: number;
};

export type GenerateTagsPayload = {
  title?: string;
  body: string;
  count?: number;
};

export type PolishTextPayload = {
  text: string;
  instruction?: string;
};

export type GeneratedImageAsset = {
  id: number;
  draft_id?: number | null;
  prompt: string;
  model_name: string;
  params: Record<string, unknown>;
  file_path: string;
  created_at: string;
};

export type GenerateCoverPayload = {
  prompt: string;
  draft_id?: number;
  size?: string;
  style?: string;
};

export type GenerateImagePayload = {
  prompt: string;
  reference_images?: string[];
  save_to_assets?: boolean;
  aspect_ratio?: "auto" | "1:1" | "3:4" | "4:3" | "9:16" | "16:9";
};

export type GenerateImageResult = {
  url: string;
  raw?: unknown;
  asset?: GeneratedImageAsset;
};

export type GenerateImageTaskResult = {
  task_id: number;
  status: string;
  progress: number;
  payload: Record<string, unknown>;
};

export type UserImageFile = {
  file_name: string;
  url: string;
  size: number;
};

export type DescribeImagePayload = {
  image_url: string;
  instruction?: string;
};

export type ImageUtilityFile = {
  file_name: string;
  file_path: string;
  download_url: string;
  width: number;
  height: number;
  media_type: string;
};

export type ComposeImagePayload = {
  title: string;
  body?: string;
  width?: number;
  height?: number;
  background_color?: string;
  accent_color?: string;
};

export type ResizeImagePayload = {
  source_file_name: string;
  width?: number;
  height?: number;
  mode?: "cover" | "contain";
  format?: "png" | "jpeg";
  quality?: number;
};
