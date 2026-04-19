import type { Flow, FlowNode, FlowEdge } from "@/types/ir";

export interface GeneratedFile {
  name: string;
  content: string;
}

export function generateCodePreview(flow: Flow): GeneratedFile[] {
  const files: GeneratedFile[] = [];

  // Generate main.py
  files.push({
    name: "main.py",
    content: generateMainPy(flow),
  });

  // Generate ir.py with embedded flow
  files.push({
    name: "ir.py",
    content: generateIrPy(flow),
  });

  // Generate runtime.py
  files.push({
    name: "runtime.py",
    content: generateRuntimePy(flow),
  });

  // Generate pyproject.toml
  files.push({
    name: "pyproject.toml",
    content: generatePyproject(flow),
  });

  // Generate README.md
  files.push({
    name: "README.md",
    content: generateReadme(flow),
  });

  return files;
}

function generateMainPy(flow: Flow): string {
  return `#!/usr/bin/env python3
"""
CLI entry point for ${flow.name}.

Usage:
    run-agent "Your input here"
    python -m agent_app.main "Your input here"
"""

import argparse
import asyncio
import json
import sys

from agent_app.runtime import run_flow


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="${flow.description || flow.name}"
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Input text for the agent",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )

    args = parser.parse_args()

    # Get input data
    if args.input:
        input_data = {"input": args.input}
    else:
        print("Enter input (Ctrl+D to finish):", file=sys.stderr)
        input_data = {"input": sys.stdin.read().strip()}

    # Run the flow
    try:
        result = asyncio.run(run_flow(input_data))

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            final = result.get("final_output")
            if isinstance(final, dict):
                output = final.get("output", final)
            else:
                output = final
            print(output)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
`;
}

function generateIrPy(flow: Flow): string {
  const fallbackNodes = flow.nodes.map((node) => {
    const plainId = node.id.includes("::") ? node.id.split("::")[1] : node.id;
    return {
      id: plainId,
      type: node.type,
      name: node.name,
      params: node.params,
    };
  });
  const fallbackEdges = flow.edges.map((edge) => {
    const source = edge.source.includes("::") ? edge.source.split("::")[1] : edge.source;
    const target = edge.target.includes("::") ? edge.target.split("::")[1] : edge.target;
    return { source, target, condition: edge.condition || null };
  });

  const agents = (flow.agents && flow.agents.length > 0)
    ? flow.agents
    : [{
        id: "main",
        name: "Main Agent",
        graph: {
          nodes: fallbackNodes,
          edges: fallbackEdges,
          root: fallbackNodes[0]?.id || "start",
        },
        llm: { provider: "auto", model: "gpt-4o-mini", temperature: 0.7, system_prompt: null },
        tools_allowlist: [],
        memory_namespace: null,
        budgets: { max_tokens: null, max_tool_calls: null, max_steps: null, max_depth: 5 },
      }];

  const irData = {
    ir_version: "2",
    flow: {
      id: flow.id,
      name: flow.name,
      version: flow.version,
      engine_preference: flow.engine_preference,
      description: flow.description || "",
    },
    agents,
    entrypoints: flow.entrypoints && flow.entrypoints.length > 0
      ? flow.entrypoints
      : [{ name: "main", agent_id: agents[0].id, description: "" }],
    handoffs: flow.handoffs || [],
    resources: flow.resources || { shared_memory_namespaces: [], global_tools: [] },
  };

  const irJson = JSON.stringify(irData, null, 2);

  return `"""Flow IR definition."""

import json
from typing import Any

# Embedded flow IR
FLOW_IR_JSON = """
${irJson}
"""


def get_flow_ir() -> dict[str, Any]:
    """Get the flow IR as a dictionary."""
    return json.loads(FLOW_IR_JSON)


def get_node(node_id: str) -> dict[str, Any] | None:
    """Get a node by ID."""
    ir = get_flow_ir()
    for node in ir["nodes"]:
        if node["id"] == node_id:
            return node
    return None


def get_topological_order() -> list[str]:
    """Get nodes in topological order."""
    ir = get_flow_ir()
    nodes = {n["id"] for n in ir["nodes"]}
    adjacency: dict[str, list[str]] = {nid: [] for nid in nodes}

    for edge in ir["edges"]:
        adjacency[edge["source"]].append(edge["target"])

    in_degree: dict[str, int] = {nid: 0 for nid in nodes}
    for edge in ir["edges"]:
        in_degree[edge["target"]] += 1

    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    result: list[str] = []

    while queue:
        queue.sort()
        node = queue.pop(0)
        result.append(node)
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return result
`;
}

function generateRuntimePy(flow: Flow): string {
  return `"""Runtime execution for the agent flow."""

import os
from dataclasses import dataclass, field
from typing import Any

from agent_app.ir import get_flow_ir, get_node, get_topological_order


@dataclass
class ExecutionContext:
    """Context for flow execution."""
    user_input: dict[str, Any] = field(default_factory=dict)
    node_outputs: dict[str, Any] = field(default_factory=dict)
    current_value: Any = None
    variables: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if "input" in self.user_input and self.current_value is None:
            self.current_value = self.user_input["input"]

    def set_node_output(self, node_id: str, output: Any) -> None:
        self.node_outputs[node_id] = output
        self.current_value = output

    def render_template(self, template: str) -> str:
        context = {
            "input": self.user_input.get("input", ""),
            "current": str(self.current_value) if self.current_value else "",
            **self.variables,
        }
        for node_id, output in self.node_outputs.items():
            context[f"node.{node_id}"] = str(output) if output else ""

        result = template
        for key, value in context.items():
            result = result.replace(f"{{{key}}}", str(value))
        return result


async def execute_node(
    node: dict[str, Any],
    context: ExecutionContext,
    flow_engine: str,
) -> dict[str, Any]:
    """Execute a single node."""
    node_type = node["type"]
    params = node.get("params", {})
    engine = params.get("engine") or flow_engine

    if node_type == "LLM":
        return await _execute_llm(node, context, engine)
    elif node_type == "Retriever":
        return await _execute_retriever(node, context, engine)
    elif node_type == "Tool":
        return await _execute_tool(node, context, engine)
    elif node_type == "Router":
        return _execute_router(node, context)
    elif node_type == "Memory":
        return _execute_memory(node, context)
    elif node_type == "Output":
        return _execute_output(node, context)
    else:
        raise ValueError(f"Unknown node type: {node_type}")


async def _execute_llm(node: dict, context: ExecutionContext, engine: str) -> dict:
    """Execute LLM node."""
    params = node.get("params", {})
    prompt_template = params.get("prompt_template", "{input}")
    prompt = context.render_template(prompt_template)

    system_prompt = params.get("system_prompt")
    if system_prompt:
        system_prompt = context.render_template(system_prompt)

    # Import based on engine
    if engine == "llamaindex":
        from llama_index.llms.openai import OpenAI
        from llama_index.core.llms import ChatMessage, MessageRole

        messages = []
        if system_prompt:
            messages.append(ChatMessage(role=MessageRole.SYSTEM, content=system_prompt))
        messages.append(ChatMessage(role=MessageRole.USER, content=prompt))

        llm = OpenAI(
            model=params.get("model", "gpt-3.5-turbo"),
            temperature=params.get("temperature", 0.7),
            max_tokens=params.get("max_tokens"),
        )
        response = await llm.achat(messages)
        return {"output": response.message.content}
    else:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        llm = ChatOpenAI(
            model=params.get("model", "gpt-3.5-turbo"),
            temperature=params.get("temperature", 0.7),
            max_tokens=params.get("max_tokens"),
        )
        response = await llm.ainvoke(messages)
        return {"output": response.content}


async def _execute_retriever(node: dict, context: ExecutionContext, engine: str) -> dict:
    """Execute Retriever node."""
    params = node.get("params", {})
    query_template = params.get("query_template", "{input}")
    query = context.render_template(query_template)

    # Placeholder - implement with your vector store
    return {"documents": [], "query": query}


async def _execute_tool(node: dict, context: ExecutionContext, engine: str) -> dict:
    """Execute Tool node."""
    params = node.get("params", {})
    tool_name = params.get("tool_name", "unknown")
    tool_input = {"input": context.current_value, **context.variables}

    # Placeholder - implement tool execution
    return {"tool_name": tool_name, "input": tool_input, "result": "placeholder"}


def _execute_router(node: dict, context: ExecutionContext) -> dict:
    """Execute Router node."""
    params = node.get("params", {})
    current = str(context.current_value).lower() if context.current_value else ""

    selected = params.get("default_route")
    for condition, target in params.get("routes", {}).items():
        if condition.lower() in current:
            selected = target
            break

    return {"selected_route": selected}


def _execute_memory(node: dict, context: ExecutionContext) -> dict:
    """Execute Memory node."""
    params = node.get("params", {})
    return {"memory_stored": {"type": params.get("memory_type", "buffer")}}


def _execute_output(node: dict, context: ExecutionContext) -> dict:
    """Execute Output node."""
    params = node.get("params", {})
    output_template = params.get("output_template", "{result}")
    output = context.render_template(output_template)
    return {"output": output, "format": params.get("format", "text")}


async def run_flow(input_data: dict[str, Any]) -> dict[str, Any]:
    """Run the flow with given input."""
    ir = get_flow_ir()
    flow = ir["flow"]
    flow_engine = flow.get("engine_preference", "langchain")

    context = ExecutionContext(user_input=input_data)
    execution_order = get_topological_order()

    results: dict[str, Any] = {}

    for node_id in execution_order:
        node = get_node(node_id)
        if node is None:
            raise ValueError(f"Node not found: {node_id}")

        output = await execute_node(node, context, flow_engine)
        context.set_node_output(node_id, output)
        results[node_id] = output

    return {
        "final_output": context.current_value,
        "node_outputs": results,
    }
`;
}

function generatePyproject(flow: Flow): string {
  return `[project]
name = "${flow.id}-agent"
version = "${flow.version}"
description = "${flow.description || flow.name}"
requires-python = ">=3.11"

dependencies = [
    "pydantic>=2.5.0",
]

[project.optional-dependencies]
langchain = [
    "langchain>=0.1.0",
    "langchain-openai>=0.0.5",
]
llamaindex = [
    "llama-index>=0.10.0",
    "llama-index-llms-openai>=0.1.0",
]
all = [
    "${flow.id}-agent[langchain,llamaindex]",
]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
]

[project.scripts]
run-agent = "agent_app.main:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/agent_app"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
`;
}

function generateReadme(flow: Flow): string {
  const nodeTypes = Array.from(new Set(flow.nodes.map((n) => n.type)));

  return `# ${flow.name}

${flow.description || "An AI agent flow exported from Agent Compiler."}

## Version
${flow.version}

## Flow Structure
- **Nodes**: ${flow.nodes.length} (${nodeTypes.join(", ")})
- **Edges**: ${flow.edges.length}
- **Engine Preference**: ${flow.engine_preference}

## Setup

1. Install dependencies:
\`\`\`bash
pip install -e ".[all]"
\`\`\`

2. Set your API key:
\`\`\`bash
export OPENAI_API_KEY="your-key-here"
\`\`\`

## Usage

### Command Line
\`\`\`bash
run-agent "Your input here"
\`\`\`

### Python
\`\`\`python
import asyncio
from agent_app.main import run_flow

result = asyncio.run(run_flow({"input": "Your input here"}))
print(result)
\`\`\`

## Testing
\`\`\`bash
pytest tests/
\`\`\`

## Generated by Agent Compiler
This project was automatically generated from a flow definition.
`;
}
