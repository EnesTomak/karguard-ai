import axios from "axios";
import type {
  UploadResponse,
  AnalysisRunResponse,
  DashboardResponse,
  SKUProfitability,
  ProductIntelligence,
  SimulationRequest,
  SimulationResult,
  ActionCard,
  ActionEditRequest,
  MCPToolTrace,
} from "../types";

const api = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
});

/* ── Upload ────────────────────────────────────────── */

export async function uploadFiles(files: File[]): Promise<UploadResponse> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  const { data } = await api.post<UploadResponse>("/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

/* ── Analyze ───────────────────────────────────────── */

export async function startAnalysis(runId: string): Promise<AnalysisRunResponse> {
  const { data } = await api.post<AnalysisRunResponse>(`/analyze/${runId}`);
  return data;
}

export async function getAnalysisStatus(runId: string): Promise<AnalysisRunResponse> {
  const { data } = await api.get<AnalysisRunResponse>(`/analyze/${runId}`);
  return data;
}

/* ── Dashboard ─────────────────────────────────────── */

export async function getDashboard(runId: string): Promise<DashboardResponse> {
  const { data } = await api.get<DashboardResponse>(`/dashboard/${runId}`);
  return data;
}

export async function getToolTraces(runId: string): Promise<MCPToolTrace[]> {
  const { data } = await api.get<MCPToolTrace[]>(`/traces/${runId}`);
  return data;
}

/* ── Products ──────────────────────────────────────── */

export async function getProducts(runId: string): Promise<SKUProfitability[]> {
  const { data } = await api.get<SKUProfitability[]>(`/products/${runId}`);
  return data;
}

export async function getProductDetail(runId: string, sku: string): Promise<ProductIntelligence> {
  const { data } = await api.get<ProductIntelligence>(`/products/${runId}/${sku}`);
  return data;
}

/* ── Simulation ────────────────────────────────────── */

export async function runSimulation(
  runId: string,
  sku: string,
  req: SimulationRequest
): Promise<SimulationResult> {
  const { data } = await api.post<SimulationResult>(`/simulate/${runId}/${sku}`, req);
  return data;
}

/* ── Actions ───────────────────────────────────────── */

export async function getActions(runId: string): Promise<ActionCard[]> {
  const { data } = await api.get<ActionCard[]>(`/actions/${runId}`);
  return data;
}

export async function approveAction(actionId: string): Promise<ActionCard> {
  const { data } = await api.post<ActionCard>(`/actions/${actionId}/approve`);
  return data;
}

export async function rejectAction(actionId: string): Promise<ActionCard> {
  const { data } = await api.post<ActionCard>(`/actions/${actionId}/reject`);
  return data;
}

export async function editAction(actionId: string, req: ActionEditRequest): Promise<ActionCard> {
  const { data } = await api.patch<ActionCard>(`/actions/${actionId}/edit`, req);
  return data;
}
