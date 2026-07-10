import React from "react";
import ReactDOM from "react-dom/client";

import { AppProviders } from "./app/providers";
import { AppRouter } from "./app/router";
import { ErrorBoundary } from "./components/ui/error-boundary";
import "./global.css";
import { installGlobalDiagnosticsHandlers } from "./lib/diagnostics";

installGlobalDiagnosticsHandlers();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ErrorBoundary>
      <AppProviders>
        <AppRouter />
      </AppProviders>
    </ErrorBoundary>
  </React.StrictMode>
);
