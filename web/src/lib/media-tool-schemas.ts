/** Client-side media tool schemas for form rendering and validation. */

export interface ToolField {
  key: string;
  label: string;
  type: "text" | "textarea" | "select" | "number" | "boolean";
  required: boolean;
  placeholder?: string;
  options?: string[];
}

export interface ToolSchema {
  name: string;
  displayName: string;
  description: string;
  fields: ToolField[];
  validate: (spec: Record<string, unknown>) => { valid: boolean; errors: Record<string, string> };
}

export const TOOL_SCHEMAS: Record<string, ToolSchema> = {
  mermaid: {
    name: "mermaid",
    displayName: "Mermaid",
    description: "Flowcharts, sequence diagrams, and other Mermaid.js diagrams",
    fields: [
      { key: "diagram", label: "Diagram", type: "textarea", required: true, placeholder: "graph TD\n  A-->B" },
      { key: "theme", label: "Theme", type: "select", required: false, options: ["default", "dark", "forest", "neutral"] },
      { key: "format", label: "Format", type: "select", required: false, options: ["png", "svg"] },
      { key: "width", label: "Width", type: "number", required: false, placeholder: "800" },
      { key: "height", label: "Height", type: "number", required: false, placeholder: "600" },
    ],
    validate: (spec) => {
      const errors: Record<string, string> = {};
      if (!spec.diagram) errors.diagram = "Diagram markup is required";
      return { valid: Object.keys(errors).length === 0, errors };
    },
  },
  nano_banana_pro: {
    name: "nano_banana_pro",
    displayName: "Nano Banana Pro",
    description: "AI-generated images from text prompts (Gemini)",
    fields: [
      { key: "prompt", label: "Prompt", type: "textarea", required: true, placeholder: "A colorful illustration of..." },
    ],
    validate: (spec) => {
      const errors: Record<string, string> = {};
      if (!spec.prompt) errors.prompt = "Image prompt is required";
      return { valid: Object.keys(errors).length === 0, errors };
    },
  },
  ray_so: {
    name: "ray_so",
    displayName: "Ray.so",
    description: "Beautiful code snippet screenshots via ray.so",
    fields: [
      { key: "code", label: "Code", type: "textarea", required: true, placeholder: "console.log('hello')" },
      { key: "language", label: "Language", type: "select", required: false, options: ["auto", "python", "javascript", "typescript", "go", "rust", "java", "bash"] },
      { key: "theme", label: "Theme", type: "select", required: false, options: ["candy", "breeze", "midnight", "sunset", "raindrop"] },
      { key: "padding", label: "Padding", type: "select", required: false, options: ["16", "32", "64", "128"] },
      { key: "title", label: "Title", type: "text", required: false, placeholder: "main.py" },
    ],
    validate: (spec) => {
      const errors: Record<string, string> = {};
      if (!spec.code) errors.code = "Code snippet is required";
      return { valid: Object.keys(errors).length === 0, errors };
    },
  },
  playwright: {
    name: "playwright",
    displayName: "Playwright",
    description: "Browser screenshots of any webpage",
    fields: [
      { key: "url", label: "URL", type: "text", required: true, placeholder: "https://example.com" },
      { key: "selector", label: "CSS Selector", type: "text", required: false, placeholder: ".main-content" },
      { key: "width", label: "Width", type: "number", required: false, placeholder: "1280" },
      { key: "height", label: "Height", type: "number", required: false, placeholder: "720" },
      { key: "full_page", label: "Full Page", type: "boolean", required: false },
    ],
    validate: (spec) => {
      const errors: Record<string, string> = {};
      if (!spec.url) errors.url = "URL is required";
      return { valid: Object.keys(errors).length === 0, errors };
    },
  },
};

export function getToolSchema(name: string): ToolSchema | undefined {
  return TOOL_SCHEMAS[name];
}

export function getAvailableTools(): ToolSchema[] {
  return Object.values(TOOL_SCHEMAS);
}
