/**
 * Types for Project Templates
 */

export type Engine = "llamaindex" | "langgraph";

export interface TemplateTag {
  label: string;
  color: string;
}

export interface TemplateParam {
  name: string;
  type: "boolean" | "string" | "integer" | "select";
  description: string;
  default: unknown;
  required: boolean;
  options?: string[] | null;
}

export interface TemplateDTO {
  id: string;
  name: string;
  description: string;
  tags: TemplateTag[];
  preview_type: "blank" | "rag" | "simple_agent" | "supervisor_workers";
  default_engine: Engine;
  supported_engines: Engine[];
  params?: TemplateParam[];
}

export interface CreateProjectRequest {
  name: string;
  template_id: string;
  engine: Engine;
  params?: Record<string, unknown>;
}

export interface CreateProjectResponse {
  id: string;
  name: string;
  template_id: string;
  engine: string;
  created_at: string;
}

// Curated LLM model list — must mirror backend registry._CURATED_MODELS
export const CURATED_MODELS: string[] = [
  // OpenAI
  "gpt-4o",
  "gpt-4o-mini",
  "o3-mini",
  // Anthropic
  "claude-opus-4-6",
  "claude-sonnet-4-6",
  "claude-haiku-4-5-20251001",
  // Google
  "gemini-2.5-pro",
  "gemini-2.5-flash",
  "gemini-2.0-flash",
];

// Fallback templates when API is unavailable
export const FALLBACK_TEMPLATES: TemplateDTO[] = [
  {
    id: "blank",
    name: "Blank Project",
    description: "Start with an empty canvas and build your agent from scratch.",
    tags: [{ label: "Minimal", color: "#6b7280" }],
    preview_type: "blank",
    default_engine: "langgraph",
    supported_engines: ["llamaindex", "langgraph"],
  },
  {
    id: "rag_agent",
    name: "RAG Agent Project",
    description: "Pre-configured retrieval-augmented generation pipeline with grounding and citations.",
    tags: [
      { label: "RAG", color: "#3b82f6" },
      { label: "Citations", color: "#10b981" },
      { label: "Grounding", color: "#8b5cf6" },
    ],
    preview_type: "rag",
    default_engine: "langgraph",
    supported_engines: ["llamaindex", "langgraph"],
  },
  {
    id: "simple_agent",
    name: "Simple Agent Project",
    description: "Basic agent with LLM and tool calling capabilities. Perfect for getting started.",
    tags: [
      { label: "Tools", color: "#f59e0b" },
      { label: "Agent", color: "#ec4899" },
    ],
    preview_type: "simple_agent",
    default_engine: "langgraph",
    supported_engines: ["llamaindex", "langgraph"],
  },
  {
    id: "oncology_research_team",
    name: "Oncology Research Team",
    description: "Multi-agent oncology team with supervisor, genomics, pathology, and trials specialists.",
    tags: [
      { label: "Multi-Agent", color: "#7c3aed" },
      { label: "Oncology", color: "#dc2626" },
      { label: "Research", color: "#0ea5e9" },
    ],
    preview_type: "supervisor_workers",
    default_engine: "langgraph",
    supported_engines: ["langgraph"],
  },
  {
    id: "pharma_research_copilot",
    name: "Pharma Research Copilot (RAG + Tools + QA)",
    description:
      "RAG with citations + tool execution (PubMed/SQL/API/Python/S3) + strict validation + synthesis + recovery. Optional vector DB (Qdrant/Pinecone) adds a 7th vector_indexer agent.",
    tags: [
      { label: "Multi-Agent", color: "#7c3aed" },
      { label: "Pharma/RAG", color: "#0ea5e9" },
      { label: "QA", color: "#10b981" },
      { label: "Policy/Retry", color: "#f59e0b" },
      { label: "Vector DB", color: "#6366f1" },
    ],
    preview_type: "supervisor_workers",
    default_engine: "langgraph",
    supported_engines: ["langgraph"],
    params: [
      {
        name: "model",
        type: "select",
        description: "Default LLM model for all agents",
        default: "gpt-4o-mini",
        required: false,
        options: CURATED_MODELS,
      },
      {
        name: "strict_schema",
        type: "boolean",
        description: "If true, schema validation errors fail execution",
        default: false,
        required: false,
        options: null,
      },
      {
        name: "vector_db_provider",
        type: "select",
        description: "Vector database provider for semantic indexing/search (adds vector_indexer agent)",
        default: "none",
        required: false,
        options: ["none", "qdrant", "pinecone"],
      },
    ],
  },
];
