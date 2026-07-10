import { CopyOutlined, ReloadOutlined } from "@ant-design/icons";
import { Button, Space, Typography } from "antd";
import { Component } from "react";
import type { CSSProperties, ErrorInfo, ReactNode } from "react";

import { buildDiagnosticText, reportClientError } from "../../lib/diagnostics";

type ErrorBoundaryProps = {
  children: ReactNode;
};

type ErrorBoundaryState = {
  error: Error | null;
  copied: boolean;
  diagnosticText: string;
};

const pageStyle: CSSProperties = {
  minHeight: "100vh",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: 24,
  background: "#0b1118",
  color: "#e5edf8",
};

const panelStyle: CSSProperties = {
  width: "min(760px, 100%)",
  border: "1px solid #263244",
  borderRadius: 8,
  background: "#111827",
  padding: 24,
  boxShadow: "0 18px 56px rgba(0, 0, 0, 0.28)",
};

const diagnosticStyle: CSSProperties = {
  maxHeight: 220,
  overflow: "auto",
  marginTop: 18,
  padding: 14,
  borderRadius: 6,
  border: "1px solid #263244",
  background: "#071626",
  color: "#c9d7ea",
  fontSize: 12,
  lineHeight: 1.6,
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
};

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = {
    error: null,
    copied: false,
    diagnosticText: "",
  };

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return {
      error,
      diagnosticText: buildDiagnosticText({
        event_type: "react_error_boundary",
        message: error.message,
        stack: error.stack,
      }),
    };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    const report = reportClientError({
      event_type: "react_error_boundary",
      message: error.message,
      stack: error.stack,
      extra: { component_stack: info.componentStack },
    });
    this.setState({
      diagnosticText: buildDiagnosticText(report),
    });
  }

  private handleRefresh = (): void => {
    window.location.reload();
  };

  private copyWithFallback(text: string): boolean {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "true");
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand("copy");
    document.body.removeChild(textarea);
    return copied;
  }

  private handleCopy = async (): Promise<void> => {
    const text =
      this.state.diagnosticText ||
      buildDiagnosticText({
        event_type: "react_error_boundary",
        message: this.state.error?.message,
        stack: this.state.error?.stack,
      });

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        this.setState({ copied: true });
        return;
      }
      this.setState({ copied: this.copyWithFallback(text) });
    } catch {
      this.setState({ copied: this.copyWithFallback(text) });
    }
  };

  render(): ReactNode {
    if (!this.state.error) {
      return this.props.children;
    }

    return (
      <main style={pageStyle}>
        <section style={panelStyle} aria-live="assertive">
          <Typography.Title level={2} style={{ color: "#e5edf8", marginTop: 0, marginBottom: 8 }}>
            页面加载失败
          </Typography.Title>
          <Typography.Paragraph style={{ color: "#93a4b8", marginBottom: 20 }}>
            当前页面遇到前端异常，系统已记录诊断信息。刷新后仍失败时，请复制诊断信息发给管理员。
          </Typography.Paragraph>
          <Space wrap>
            <Button icon={<ReloadOutlined />} onClick={this.handleRefresh}>
              刷新页面
            </Button>
            <Button type="primary" icon={<CopyOutlined />} onClick={() => void this.handleCopy()}>
              {this.state.copied ? "已复制" : "复制诊断信息"}
            </Button>
          </Space>
          <pre style={diagnosticStyle}>{this.state.diagnosticText}</pre>
        </section>
      </main>
    );
  }
}
