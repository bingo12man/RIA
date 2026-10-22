import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api/reminders": {
        target: "http://127.0.0.1:8011",
        changeOrigin: true,
        rewrite: path => path.replace(/^\/api/, ""),
      },
      "/api/speak": {
      target: "http://127.0.0.1:8012",
      changeOrigin: true,
      rewrite: path => path.replace(/^\/api/, ""),
    },
    "/api/audio": {
        target: "http://127.0.0.1:8012",
        changeOrigin: true,
        rewrite: path => path.replace(/^\/api/, ""),
      },
      "/api/command": {
        target: "http://127.0.0.1:8012",
        changeOrigin: true,
        rewrite: path => path.replace(/^\/api/, "")
      }
    },
  },
});
