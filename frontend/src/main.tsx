import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@fontsource-variable/montserrat/wght.css";
import "@fontsource-variable/montserrat/wght-italic.css";
import "@fontsource-variable/figtree/wght.css";

import App from "./App";
import "./index.css";


createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
