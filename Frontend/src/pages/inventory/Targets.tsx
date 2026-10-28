import { PlusOutlined } from '@ant-design/icons';
import { Input } from 'antd';
import { useState } from 'react';
import { Button, ConfirmModal, PageShell } from '@/components';
import { PERMISSIONS } from '@/constants/enums/permissions';
import { useAuth } from '@/context/AuthContext';
import { usePagination } from '@/hooks';
import { HostKeyModal, TargetFormModal, TargetsTable } from '@/features/inventory/components';
import { useDeleteTarget, useResetTargetHostKey, useTargets } from '@/features/inventory/hooks';
import type { Target } from '@/services/inventory-services';
import { notify } from '@/utils/notify';

export default function Targets() {
  const { canAccess } = useAuth();
  const canManage = canAccess({ permission: PERMISSIONS.TARGETS_MANAGE });
  const [search, setSearch] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Target | null>(null);
  const [resetTarget, setResetTarget] = useState<Target | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Target | null>(null);
  const { page, page_size, setPage, paginationFor } = usePagination();
  const targets = useTargets({ page, page_size, search: search || undefined });
  const { mutateAsync: removeTarget } = useDeleteTarget();
  const { mutateAsync: resetHostKey } = useResetTargetHostKey();
  const [hostKeyTarget, setHostKeyTarget] = useState<Target | null>(null);

  return (
    <PageShell
      title="Targets"
      actions={
        <>
          <Input.Search
            allowClear
            placeholder="Name or address"
            onSearch={(v) => {
              setSearch(v);
              setPage(1);
            }}
          />
          {canManage && (
            <Button
              variant="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setEditing(null);
                setFormOpen(true);
              }}
            >
              Add target
            </Button>
          )}
        </>
      }
    >
      <TargetsTable
        query={targets}
        pagination={paginationFor(targets.data?.total)}
        canManage={canManage}
        onEdit={(t) => {
          setEditing(t);
          setFormOpen(true);
        }}
        onResetHostKey={setResetTarget}
        onLearnHostKey={canManage ? setHostKeyTarget : undefined}
        onDelete={setDeleteTarget}
      />
      {canManage && <HostKeyModal target={hostKeyTarget} onClose={() => setHostKeyTarget(null)} />}
      {canManage && (
        <TargetFormModal
          open={formOpen}
          target={editing}
          onClose={() => {
            setFormOpen(false);
            setEditing(null);
          }}
        />
      )}
      <ConfirmModal
        open={resetTarget !== null}
        danger
        title="Reset the pinned host key?"
        description="Only after confirming the device's key really changed."
        confirmLabel="Reset"
        onCancel={() => setResetTarget(null)}
        onConfirm={async () => {
          if (!resetTarget) return;
          try {
            await resetHostKey(resetTarget.id);
            notify.success('Host key cleared; the next session pins the key the device presents');
            setResetTarget(null);
          } catch {
            // apiClient's interceptor already toasted the failure.
          }
        }}
      />
      <ConfirmModal
        open={deleteTarget !== null}
        danger
        title="Delete target?"
        description="Its accounts and stored secrets are deleted too."
        confirmLabel="Delete"
        onCancel={() => setDeleteTarget(null)}
        onConfirm={async () => {
          if (!deleteTarget) return;
          try {
            await removeTarget(deleteTarget.id);
            notify.success('Target deleted');
            setDeleteTarget(null);
          } catch {
            // apiClient's interceptor already toasted the failure.
          }
        }}
      />
    </PageShell>
  );
}
