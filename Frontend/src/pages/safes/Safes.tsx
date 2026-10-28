import { PlusOutlined } from '@ant-design/icons';
import { Input } from 'antd';
import { useState } from 'react';
import { Button, PageShell } from '@/components';
import { PERMISSIONS } from '@/constants/enums/permissions';
import { useAuth } from '@/context/AuthContext';
import { usePagination } from '@/hooks';
import { SafeFormModal, SafeMembersDrawer, SafesTable } from '@/features/safes/components';
import { useSafes } from '@/features/safes/hooks';
import type { Safe } from '@/services/safes-services';

export default function Safes() {
  const { canAccess } = useAuth();
  const canManage = canAccess({ permission: PERMISSIONS.SAFES_MANAGE });
  const [search, setSearch] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Safe | null>(null);
  const [viewing, setViewing] = useState<Safe | null>(null);
  const { page, page_size, setPage, paginationFor } = usePagination();
  const safes = useSafes({ page, page_size, search: search || undefined });

  return (
    <PageShell
      title="Safes"
      description="Every account lives in one safe; its members decide who may list, use, retrieve or manage it."
      actions={
        <>
          <Input.Search
            allowClear
            placeholder="Safe name"
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
              Create safe
            </Button>
          )}
        </>
      }
    >
      <SafesTable
        query={safes}
        pagination={paginationFor(safes.data?.total)}
        canManage={canManage}
        onEdit={(s) => {
          setEditing(s);
          setFormOpen(true);
        }}
        onMembers={setViewing}
      />
      {canManage && (
        <SafeFormModal
          open={formOpen}
          safe={editing}
          onClose={() => {
            setFormOpen(false);
            setEditing(null);
          }}
        />
      )}
      <SafeMembersDrawer safe={viewing} onClose={() => setViewing(null)} />
    </PageShell>
  );
}
