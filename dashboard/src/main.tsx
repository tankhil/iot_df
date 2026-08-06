import { createRoot } from "react-dom/client";

import { App } from "./App";
import { ErrorBoundary } from "./ErrorBoundary";
import "./styles.css";

const root = document.getElementById("root");

if (!root) {
  throw new Error("React root element #root was not found");
}

createRoot(root).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
);
