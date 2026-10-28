/** Response envelopes shared by every WardX endpoint. Domain types live beside their service. */
export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message: string | null;
}

export interface Paginated<T> {
  success: boolean;
  data: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ApiErrorBody {
  success: false;
  status_code: number;
  error: { code: string; message: string; details: Record<string, unknown> };
}

export interface PageQuery {
  page?: number;
  page_size?: number;
  [key: string]: string | number | boolean | undefined;
}

export interface UserBrief {
  id: string;
  username: string;
  full_name: string | null;
}
