import type { Node, Edge } from "@xyflow/react";

// The data every canvas node carries. `kind` is the spec stage (or "index" for
// the one synthetic ChunkIndex node); `name` is the component; `params` is the
// live config the inspector edits and the exporter reads.
export interface BlockData {
  kind: string;
  name: string;
  params: Record<string, unknown>;
  synthetic?: boolean;
  [key: string]: unknown;
}

export type BlockNode = Node<BlockData>;
export type BlockEdge = Edge;

export interface Problem {
  level: "error" | "warn";
  message: string;
}
