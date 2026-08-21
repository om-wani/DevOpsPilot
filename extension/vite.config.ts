import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import basicSsl from "@vitejs/plugin-basic-ssl";

// The dev manifest points baseUri at this server, and Azure DevOps is HTTPS, so
// the dev server has to be HTTPS too or the iframe is blocked as mixed content.
export default defineConfig({
  plugins: [react(), basicSsl()],
  base: "./",
  server: { port: 3000, strictPort: true, cors: true },
  build: { outDir: "dist", emptyOutDir: true },
});
