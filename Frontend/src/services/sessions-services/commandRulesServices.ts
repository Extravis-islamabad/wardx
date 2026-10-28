/** Wraps /api/v1/command-rules/*: deny rules the gateway enforces on typed commands. */
import { apiClient } from '@/lib/apiClient';
import type { ApiResponse } from '@/types/api';

export interface CommandRule {
  id: string;
  pattern: string;
  description: string | null;
  account_id: string | null;
  target_id: string | null;
  platform: string | null;
  is_active: boolean;
  created_at: string;
}

export interface RuleInput {
  pattern: string;
  description?: string;
  account_id?: string;
  target_id?: string;
  platform?: string;
}

export type RuleUpdatePayload = Partial<RuleInput & { is_active: boolean }>;

export interface RuleTestResult {
  blocked: boolean;
  rule_id: string | null;
  description: string | null;
}

const BASE = 'command-rules';

export const commandRulesService = {
  async list(): Promise<ApiResponse<CommandRule[]>> {
    const { data } = await apiClient.get<ApiResponse<CommandRule[]>>(BASE);
    return data;
  },

  async create(payload: RuleInput): Promise<ApiResponse<CommandRule>> {
    const { data } = await apiClient.post<ApiResponse<CommandRule>>(BASE, payload);
    return data;
  },

  async update(id: string, payload: RuleUpdatePayload): Promise<ApiResponse<CommandRule>> {
    const { data } = await apiClient.patch<ApiResponse<CommandRule>>(`${BASE}/${id}`, payload);
    return data;
  },

  async remove(id: string): Promise<ApiResponse<null>> {
    const { data } = await apiClient.delete<ApiResponse<null>>(`${BASE}/${id}`);
    return data;
  },

  async test(command: string, account_id?: string): Promise<ApiResponse<RuleTestResult>> {
    const { data } = await apiClient.post<ApiResponse<RuleTestResult>>(`${BASE}/test`, { command, account_id });
    return data;
  },
};

export default commandRulesService;
