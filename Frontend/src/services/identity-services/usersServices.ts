/** Wraps /api/v1/users/*: local and directory WardX users. */
import { apiClient } from '@/lib/apiClient';
import type { ApiResponse, PageQuery, Paginated } from '@/types/api';
import type { User } from '@/services/auth-services';

export interface UserCreatePayload {
  username: string;
  password: string;
  email?: string;
  full_name?: string;
  role: string;
}

export type UserUpdatePayload = Partial<Pick<User, 'role' | 'is_active' | 'email' | 'full_name'>>;

const BASE = 'users';

export const usersService = {
  async list(params: PageQuery): Promise<Paginated<User>> {
    const { data } = await apiClient.get<Paginated<User>>(BASE, { params });
    return data;
  },

  async create(payload: UserCreatePayload): Promise<ApiResponse<User>> {
    const { data } = await apiClient.post<ApiResponse<User>>(BASE, payload);
    return data;
  },

  async update(id: string, payload: UserUpdatePayload): Promise<ApiResponse<User>> {
    const { data } = await apiClient.patch<ApiResponse<User>>(`${BASE}/${id}`, payload);
    return data;
  },

  async resetPassword(id: string, new_password: string): Promise<ApiResponse<null>> {
    const { data } = await apiClient.post<ApiResponse<null>>(`${BASE}/${id}/reset-password`, { new_password });
    return data;
  },

  /** Break-glass: only to a local, MFA-enrolled user, and never to yourself. */
  async grantEmergency(id: string): Promise<ApiResponse<null>> {
    const { data } = await apiClient.put<ApiResponse<null>>(`${BASE}/${id}/permissions/access.emergency`);
    return data;
  },

  async revokeEmergency(id: string): Promise<ApiResponse<null>> {
    const { data } = await apiClient.delete<ApiResponse<null>>(`${BASE}/${id}/permissions/access.emergency`);
    return data;
  },

  async resetMfa(id: string): Promise<ApiResponse<null>> {
    const { data } = await apiClient.post<ApiResponse<null>>(`${BASE}/${id}/mfa/reset`);
    return data;
  },
};

export default usersService;
