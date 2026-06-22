import { useMemo } from "react";
import { useNavigate } from "react-router-dom";

import { ContentLibraryShell, useContentLibrary } from "../../../components/content-library";
import { createXhsContentLibraryAdapter } from "./xhs-content-library-adapter";

export function XhsLibraryPage() {
  const navigate = useNavigate();
  const adapter = useMemo(() => createXhsContentLibraryAdapter(navigate), [navigate]);
  const controller = useContentLibrary(adapter);

  return <ContentLibraryShell adapter={adapter} controller={controller} />;
}
