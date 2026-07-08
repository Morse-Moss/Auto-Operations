import { App, ConfigProvider, theme } from "antd";
import zhCN from "antd/locale/zh_CN";
import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";

type ThemeMode = "dark" | "light";

const ThemeContext = createContext<{ mode: ThemeMode; toggle: () => void }>({
  mode: "dark",
  toggle: () => {},
});

export function useThemeMode() {
  return useContext(ThemeContext);
}

const darkTokens = {
  colorPrimary: "#2f7df6",
  colorBgBase: "#0b1118",
  colorBgContainer: "#111827",
  colorBgElevated: "#162033",
  colorBorder: "#263244",
  colorBorderSecondary: "#1f2a3a",
  colorText: "#e5edf8",
  colorTextSecondary: "#93a4b8",
  borderRadius: 6,
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
};

const lightTokens = {
  colorPrimary: "#1f6feb",
  colorBgBase: "#f4f7fb",
  colorBgContainer: "#ffffff",
  colorBgElevated: "#ffffff",
  colorBorder: "#dce4ef",
  colorBorderSecondary: "#e8eef6",
  colorText: "#111827",
  colorTextSecondary: "#667085",
  borderRadius: 6,
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
};

const darkComponents = {
  Layout: { siderBg: "#071626", headerBg: "#111827", bodyBg: "#0b1118" },
  Menu: {
    darkItemBg: "#071626",
    darkSubMenuItemBg: "#071626",
    darkItemSelectedBg: "rgba(47, 125, 246, 0.2)",
    darkItemSelectedColor: "#82b4ff",
  },
  Card: { colorBgContainer: "#111827", colorBorderSecondary: "#263244" },
  Table: { colorBgContainer: "#111827", headerBg: "#162033", borderColor: "#263244" },
};

const lightComponents = {
  Layout: { siderBg: "#ffffff", headerBg: "#ffffff", bodyBg: "#f4f7fb" },
  Menu: {
    itemSelectedBg: "#eaf2ff",
    itemSelectedColor: "#1f6feb",
    itemHoverBg: "#f2f6fc",
  },
  Card: { colorBgContainer: "#ffffff", colorBorderSecondary: "#dce4ef" },
  Table: { colorBgContainer: "#ffffff", headerBg: "#f7f9fc", borderColor: "#e8eef6" },
};

type AppProvidersProps = { children: ReactNode };

export function AppProviders({ children }: AppProvidersProps) {
  const [mode, setMode] = useState<ThemeMode>(() => {
    const saved = localStorage.getItem("theme-mode");
    return saved === "light" ? "light" : "dark";
  });

  useEffect(() => {
    localStorage.setItem("theme-mode", mode);
    document.documentElement.dataset.theme = mode;
    document.body.dataset.theme = mode;
    document.body.style.background = mode === "dark" ? "#0b1118" : "#f4f7fb";
  }, [mode]);

  const toggle = () => setMode((m) => (m === "dark" ? "light" : "dark"));
  const isDark = mode === "dark";

  return (
    <ThemeContext.Provider value={{ mode, toggle }}>
      <ConfigProvider
        locale={zhCN}
        theme={{
          algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
          token: isDark ? darkTokens : lightTokens,
          components: isDark ? darkComponents : lightComponents,
        }}
      >
        <App>{children}</App>
      </ConfigProvider>
    </ThemeContext.Provider>
  );
}
