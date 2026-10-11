import { defineConfig } from "tsup";

// Web Bot Auth TypeScript SDK (`wb-auth`) build config.
// The package is `"type": "module"`, so `.js` is ESM and CommonJS MUST use
// `.cjs` — emitting CJS as `.js` makes `require("wb-auth")` return `{}`.
//   ESM -> dist/index.js   (+ index.d.ts)
//   CJS -> dist/index.cjs  (+ index.d.cts)
export default defineConfig({
	entry: ["src/index.ts"],
	format: ["esm", "cjs"],
	dts: true,
	outExtension({ format }) {
		return format === "esm" ? { js: ".js" } : { js: ".cjs" };
	},
	clean: true,
	sourcemap: true,
	target: "node20",
});
