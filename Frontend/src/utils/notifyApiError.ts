import axios from 'axios';
import type { ApiErrorBody } from '@/types/api';
import { notify } from './notify';

/** The server's own words for a failure: validation errors joined, else the error message. */
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const body = error.response?.data as ApiErrorBody | undefined;
    if (body?.error) {
      const errors = body.error.details?.errors as { loc: string[]; msg: string }[] | undefined;
      if (errors?.length) {
        return errors.map((e) => `${e.loc.slice(1).join('.')}: ${e.msg}`).join('; ');
      }
      return body.error.message;
    }
    return error.message;
  }
  return error instanceof Error ? error.message : 'Something went wrong';
}

export const apiErrorStatus = (error: unknown): number | undefined =>
  axios.isAxiosError(error) ? error.response?.status : undefined;

export const notifyApiError = (error: unknown) => notify.error(errorMessage(error));
