/// <reference types="vitest/config" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// `vitest/config`'s `defineConfig` is `vite`'s own `defineConfig` with the
// `test` block's types merged in, so this file still works as the app's
// normal Vite config (dev/build/preview) — Task 79 only adds the `test`
// key below, nothing else changes.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: true,
  },
});
