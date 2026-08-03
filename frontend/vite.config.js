import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig(({ mode }) => {
    const apiProxyTarget = loadEnv(mode, ".", "").VITE_DEV_API_PROXY_TARGET || "http://127.0.0.1:8015";
    return {
        plugins: [react()],
        build: {
            outDir: "dist",
            emptyOutDir: true,
        },
        server: {
            proxy: {
                "/api": apiProxyTarget,
            },
        },
    };
});
