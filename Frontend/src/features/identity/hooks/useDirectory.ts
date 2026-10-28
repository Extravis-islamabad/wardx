import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { directoryService, type DirectoryConfigInput } from '@/services/identity-services';
import { identityKeys } from './identityKeys';

export function useDirectoryConfig() {
  return useQuery({
    queryKey: identityKeys.directory(),
    queryFn: async () => (await directoryService.get()).data,
  });
}

export function useSaveDirectoryConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: DirectoryConfigInput) => directoryService.save(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: identityKeys.directory() }),
  });
}

/** Looks a login name up with the service account; no password needed. */
export function useTestDirectoryUser() {
  return useMutation({
    mutationFn: async (username: string) => (await directoryService.test(username)).data,
  });
}

export function useRunDirectorySync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ dryRun, force }: { dryRun: boolean; force?: boolean }) =>
      (await directoryService.sync(dryRun, force)).data,
    onSuccess: (result) => {
      if (!result.dry_run) void qc.invalidateQueries({ queryKey: identityKeys.directory() });
      void qc.invalidateQueries({ queryKey: identityKeys.usersAll() });
    },
  });
}
