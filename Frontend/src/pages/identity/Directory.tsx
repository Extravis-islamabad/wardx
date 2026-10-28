import { ErrorState, PageShell } from '@/components';
import { DirectoryConfigForm, DirectorySyncPanel, DirectoryTestUser } from '@/features/identity/components';
import { useDirectoryConfig } from '@/features/identity/hooks';

export default function Directory() {
  const config = useDirectoryConfig();
  const data = config.data;
  return (
    <PageShell
      title="Directory sign-in"
      description="Let people sign in with their LDAP / Active Directory account. Local WardX accounts keep working and always win a name clash. MFA, lockout and auditing apply to directory users too."
    >
      {config.isError ? (
        <ErrorState error={config.error} onRetry={() => void config.refetch()} />
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_380px]">
          <div>{!config.isLoading && <DirectoryConfigForm config={data ?? null} />}</div>
          <div>
            {data && <DirectoryTestUser />}
            {data && <DirectorySyncPanel config={data} />}
          </div>
        </div>
      )}
    </PageShell>
  );
}
