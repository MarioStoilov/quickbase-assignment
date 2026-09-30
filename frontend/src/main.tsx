/**
 * Browser entry point: mounts the application into the page.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./styles.css";

// Id of the element in `index.html` the application renders into.
const ROOT_ELEMENT_ID = "root";

// Thrown when the page lacks the mount element; the bundle is then served with the
// wrong HTML.
const MISSING_ROOT_ERROR = "the page has no element to mount the application into";

const rootElement = document.getElementById(ROOT_ELEMENT_ID);
const hasRootElement = rootElement !== null;
if (!hasRootElement) {
  throw new Error(MISSING_ROOT_ERROR);
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
