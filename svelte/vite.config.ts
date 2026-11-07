import { createReadStream, existsSync, statSync } from "node:fs";
import { extname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vite";

const publicData = resolve(fileURLToPath(new URL("../../public/data", import.meta.url)));
const localData = resolve(fileURLToPath(new URL("./static/data", import.meta.url)));
const dataRoot = existsSync(publicData) ? publicData : localData;
const contentTypes: Record<string, string> = {
  ".atlas": "text/plain; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".jpg": "image/jpeg",
  ".ogg": "audio/ogg",
  ".png": "image/png",
  ".skel": "application/octet-stream",
};

export default defineConfig({
  plugins: [
    {
      name: "workspace-public-data",
      configureServer(server) {
        server.middlewares.use((request, response, next) => {
          if (!request.url?.startsWith("/data/")) {
            next();
            return;
          }

          if (request.method !== "GET" && request.method !== "HEAD") {
            response.statusCode = 405;
            response.end("Method not allowed");
            return;
          }

          let pathname: string;
          try {
            pathname = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
          } catch {
            response.statusCode = 400;
            response.end("Invalid asset path");
            return;
          }
          const relativePath = pathname.slice("/data/".length);
          const filePath = resolve(dataRoot, `.${sep}${relativePath}`);
          if (!filePath.startsWith(`${dataRoot}${sep}`)) {
            response.statusCode = 403;
            response.end("Forbidden");
            return;
          }
          let info;
          try {
            info = statSync(filePath);
          } catch (error) {
            if (
              error instanceof Error &&
              "code" in error &&
              (error.code === "ENOENT" || error.code === "ENOTDIR")
            ) {
              next();
              return;
            }
            console.error(`Unable to inspect asset path ${filePath}:`, error);
            response.statusCode = 500;
            response.end("Unable to read asset");
            return;
          }
          if (!info.isFile()) {
            next();
            return;
          }
          response.setHeader(
            "Content-Type",
            contentTypes[extname(filePath).toLowerCase()] ?? "application/octet-stream",
          );
          response.setHeader("Content-Length", info.size);
          if (request.method === "HEAD") {
            response.end();
            return;
          }
          const stream = createReadStream(filePath);
          stream.on("error", (error) => {
            console.error(`Unable to stream asset ${filePath}:`, error);
            if (!response.headersSent) response.statusCode = 500;
            response.end("Unable to read asset");
          });
          stream.pipe(response);
        });
      },
    },
    sveltekit(),
  ],
});
