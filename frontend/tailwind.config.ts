import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Node type colors — reference CSS variables so there is a single source of truth.
        // Values here must stay in sync with --node-* in globals.css.
        "node-trigger":   "var(--node-trigger)",
        "node-llm":       "var(--node-llm)",
        "node-tool":      "var(--node-tool)",
        "node-router":    "var(--node-router)",
        "node-retriever": "var(--node-retriever)",
        "node-memory":    "var(--node-memory)",
        "node-output":    "var(--node-output)",
        "node-graph":     "var(--node-graph)",
      },
    },
  },
  plugins: [],
};
export default config;
