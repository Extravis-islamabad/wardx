import { PlusOutlined } from '@ant-design/icons';
import { Input, Select } from 'antd';
import { useState } from 'react';
import { Button, ConfirmModal, PageShell } from '@/components';
import { PERMISSIONS } from '@/constants/enums/permissions';
import { useAuth } from '@/context/AuthContext';
import { usePagination } from '@/hooks';
import { EmergencyRevealModal, RequestAccessModal, RevealModal } from '@/features/access/components';
import { AccountFormModal, AccountsTable, SetSecretModal } from '@/features/inventory/components';
import { useAccounts, useDeleteAccount } from '@/features/inventory/hooks';
import { useSafes } from '@/features/safes/hooks';
import { PICKER_PAGE } from '@/constants/globals';
import { ConnectModal } from '@/features/sessions/components';
import type { Checkout } from '@/services/access-services';
import type { Account } from '@/services/inventory-services';
import { notify } from '@/utils/notify';

export default function Accounts() {
  const { canAccess } = useAuth();
  const canManage = canAccess({ permission: PERMISSIONS.ACCOUNTS_MANAGE });
  const canBreakGlass = canAccess({ permission: PERMISSIONS.ACCESS_EMERGENCY });
  const [breakingGlass, setBreakingGlass] = useState<Account | null>(null);
  const [breakGlassOpen, setBreakGlassOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [safeId, setSafeId] = useState<string | undefined>();
  const safes = useSafes(PICKER_PAGE);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Account | null>(null);
  const [settingSecret, setSettingSecret] = useState<Account | null>(null);
  const [accessing, setAccessing] = useState<Account | null>(null);
  const [revealing, setRevealing] = useState<Checkout | null>(null);
  const [connecting, setConnecting] = useState<Account | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Account | null>(null);
  const { page, page_size, setPage, paginationFor } = usePagination();
  const accounts = useAccounts({ page, page_size, search: search || undefined, safe_id: safeId });
  const { mutateAsync: removeAccount } = useDeleteAccount();

  return (
    <PageShell
      title="Privileged accounts"
      actions={
        <>
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            className="min-w-44"
            placeholder="All safes"
            aria-label="Safe"
            value={safeId}
            loading={safes.isLoading}
            onChange={(v) => {
              setSafeId(v);
              setPage(1);
            }}
            options={safes.data?.data?.map((s) => ({ value: s.id, label: s.name }))}
          />
          <Input.Search
            allowClear
            placeholder="User, target or address"
            onSearch={(v) => {
              setSearch(v);
              setPage(1);
            }}
          />
          {canBreakGlass && (
            <Button
              variant="danger"
              onClick={() => {
                setBreakingGlass(null);
                setBreakGlassOpen(true);
              }}
            >
              Break glass
            </Button>
          )}
          {canManage && (
            <Button
              variant="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setEditing(null);
                setFormOpen(true);
              }}
            >
              Add account
            </Button>
          )}
        </>
      }
    >
      <AccountsTable
        query={accounts}
        pagination={paginationFor(accounts.data?.total)}
        canManage={canManage}
        safePermissions={Object.fromEntries(safes.data?.data?.map((s) => [s.id, s.my_permissions]) ?? [])}
        onEmergency={
          canBreakGlass
            ? (a) => {
                setBreakingGlass(a);
                setBreakGlassOpen(true);
              }
            : undefined
        }
        onAccess={setAccessing}
        onConnect={setConnecting}
        onSetSecret={setSettingSecret}
        onEdit={(a) => {
          setEditing(a);
          setFormOpen(true);
        }}
        onDelete={setDeleteTarget}
      />
      {canManage && (
        <AccountFormModal
          open={formOpen}
          account={editing}
          onClose={() => {
            setFormOpen(false);
            setEditing(null);
          }}
        />
      )}
      <SetSecretModal account={settingSecret} onClose={() => setSettingSecret(null)} />
      <RequestAccessModal account={accessing} onClose={() => setAccessing(null)} onCheckedOut={setRevealing} />
      <RevealModal checkout={revealing} onClose={() => setRevealing(null)} />
      {canBreakGlass && (
        <EmergencyRevealModal
          open={breakGlassOpen}
          account={breakingGlass}
          onClose={() => {
            setBreakGlassOpen(false);
            setBreakingGlass(null);
          }}
        />
      )}
      {connecting && <ConnectModal account={connecting} onClose={() => setConnecting(null)} />}
      <ConfirmModal
        open={deleteTarget !== null}
        danger
        title="Delete account and its stored secrets?"
        confirmLabel="Delete"
        onCancel={() => setDeleteTarget(null)}
        onConfirm={async () => {
          if (!deleteTarget) return;
          try {
            await removeAccount(deleteTarget.id);
            notify.success('Account deleted');
            setDeleteTarget(null);
          } catch {
            // apiClient's interceptor already toasted the failure.
          }
        }}
      />
    </PageShell>
  );
}
