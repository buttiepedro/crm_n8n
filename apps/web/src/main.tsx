import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./auth";
import { DialogHost } from "./ui/dialogs";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
        <DialogHost />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
