import type { AvatarProps, TagProps } from "antd";
import type { ReactNode } from "react";

export type PlatformAccountAction = {
  key: string;
  label: ReactNode;
  onClick?: () => void;
  href?: string;
  disabled?: boolean;
  danger?: boolean;
  type?: "primary" | "default" | "dashed" | "link" | "text";
};

export type PlatformAccountMetric = {
  key: string;
  title: ReactNode;
  value: string | number;
  span?: number;
  groupSeparator?: string;
  suffix?: ReactNode;
  prefix?: ReactNode;
};

export type PlatformAccountCardTag = {
  key: string;
  label: ReactNode;
  color?: TagProps["color"];
};

export type PlatformAccountCardItem = {
  key: string;
  title: ReactNode;
  subtitle?: ReactNode;
  avatar?: AvatarProps["src"];
  avatarText?: ReactNode;
  status?: PlatformAccountCardTag;
  badge?: PlatformAccountCardTag;
  metrics?: PlatformAccountMetric[];
  description?: ReactNode;
  tags?: PlatformAccountCardTag[];
  actions?: PlatformAccountAction[];
};

export type PlatformAccountsShellItem = PlatformAccountCardItem;
