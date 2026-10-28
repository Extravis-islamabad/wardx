import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { commandRulesService, type RuleInput, type RuleUpdatePayload } from '@/services/sessions-services';
import { sessionsKeys } from './sessionsKeys';

export function useCommandRules() {
  return useQuery({
    queryKey: sessionsKeys.commandRules(),
    queryFn: async () => (await commandRulesService.list()).data,
  });
}

export function useCreateCommandRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: RuleInput) => commandRulesService.create(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: sessionsKeys.commandRules() }),
  });
}

export function useUpdateCommandRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: RuleUpdatePayload }) =>
      commandRulesService.update(id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: sessionsKeys.commandRules() }),
  });
}

export function useDeleteCommandRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => commandRulesService.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: sessionsKeys.commandRules() }),
  });
}

/** Dry-runs a command against the active rules; changes nothing. */
export function useTestCommand() {
  return useMutation({
    mutationFn: async (command: string) => (await commandRulesService.test(command)).data,
  });
}
