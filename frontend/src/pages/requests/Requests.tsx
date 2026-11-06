import React, { useState, useEffect } from 'react';
import { requestsApi } from '@/api';
import { useAuth } from '@/context/AuthContext';
import { ErrorCard } from '@/components/common/ErrorCard';
import { TableSkeleton } from '@/components/common/Skeleton';
import { EmptyState } from '@/components/common/EmptyState';
import { Modal } from '@/components/common/Modal';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import type { RequestOut } from '@/types/api';
import {
  Inbox,
  Check,
  X,
  Trash2,
  Clock,
  Film,
  Tv,
  CheckCircle2,
  XCircle,
  AlertCircle,
  MessageSquare,
} from 'lucide-react';

const STATUS_FILTERS = [
  { id: '', label: 'All Requests' },
  { id: 'pending', label: 'Pending' },
  { id: 'approved', label: 'Approved' },
  { id: 'denied', label: 'Denied' },
  { id: 'failed', label: 'Failed' },
];

export const Requests: React.FC = () => {
  const { isAdmin } = useAuth();
  const [requests, setRequests] = useState<RequestOut[]>([]);
  const [selectedStatus, setSelectedStatus] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  // Action state
  const [actionItem, setActionItem] = useState<{ id: number; action: 'approve' | 'deny'; title: string } | null>(null);
  const [note, setNote] = useState('');
  const [actionSubmitting, setActionSubmitting] = useState(false);

  // Delete state
  const [deleteId, setDeleteId] = useState<number | null>(null);

  useEffect(() => {
    loadRequests();
  }, [selectedStatus]);

  const loadRequests = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await requestsApi.getRequests(selectedStatus || undefined);
      setRequests(data);
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  };

  const handleActionSubmit = async () => {
    if (!actionItem) return;
    setActionSubmitting(true);
    setError(null);
    try {
      if (actionItem.action === 'approve') {
        await requestsApi.approve(actionItem.id, note || undefined);
      } else {
        await requestsApi.deny(actionItem.id, note || undefined);
      }
      setActionItem(null);
      setNote('');
      await loadRequests();
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setActionSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteId) return;
    setError(null);
    try {
      await requestsApi.deleteRequest(deleteId);
      setDeleteId(null);
      await loadRequests();
    } catch (err: unknown) {
      setError(err as Error);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'approved':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300 px-2.5 py-0.5 text-xs font-semibold">
            <CheckCircle2 className="h-3 w-3 text-emerald-500" /> Approved
          </span>
        );
      case 'denied':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-red-100 text-red-800 dark:bg-red-950/60 dark:text-red-300 px-2.5 py-0.5 text-xs font-semibold">
            <XCircle className="h-3 w-3 text-red-500" /> Denied
          </span>
        );
      case 'failed':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300 px-2.5 py-0.5 text-xs font-semibold">
            <AlertCircle className="h-3 w-3 text-amber-500" /> Failed
          </span>
        );
      case 'pending':
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-indigo-100 text-indigo-800 dark:bg-indigo-950/60 dark:text-indigo-300 px-2.5 py-0.5 text-xs font-semibold">
            <Clock className="h-3 w-3 text-indigo-500" /> Pending Review
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
            <Inbox className="h-6 w-6 text-brand-600 dark:text-brand-400" />
            Media Requests
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {isAdmin ? 'Review, approve, or deny requested movies and TV series.' : 'Track the status of your requested media.'}
          </p>
        </div>

        {/* Status Filters */}
        <div className="inline-flex flex-wrap rounded-xl bg-slate-200/70 p-1 dark:bg-slate-800/80 gap-1">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => setSelectedStatus(f.id)}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                selectedStatus === f.id
                  ? 'bg-white text-brand-700 shadow-xs dark:bg-slate-900 dark:text-brand-300'
                  : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <ErrorCard error={error} onDismiss={() => setError(null)} />

      {/* Requests List */}
      {loading ? (
        <TableSkeleton rows={4} />
      ) : requests.length > 0 ? (
        <div className="space-y-3">
          {requests.map((req) => (
            <div
              key={req.id}
              className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-xs hover:border-slate-300 dark:hover:border-slate-700 transition"
            >
              <div className="flex items-center gap-3.5 min-w-0">
                <div className="h-16 w-11 rounded-lg overflow-hidden bg-slate-100 dark:bg-slate-800 shrink-0">
                  {req.poster_url ? (
                    <img
                      src={req.poster_url}
                      alt={req.title}
                      className="h-full w-full object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <div className="h-full w-full flex items-center justify-center text-slate-400">
                      {req.media_type === 'series' ? <Tv className="h-5 w-5" /> : <Film className="h-5 w-5" />}
                    </div>
                  )}
                </div>

                <div className="space-y-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-slate-900 dark:text-white truncate">
                      {req.title}
                    </span>
                    {req.year && (
                      <span className="text-xs text-slate-500 shrink-0">({req.year})</span>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <span className="capitalize font-medium text-brand-600 dark:text-brand-400">
                      {req.media_type === 'series' ? 'TV Series' : 'Movie'}
                    </span>
                    <span>•</span>
                    <span>Requested by {req.requested_by || 'user'}</span>
                    {req.created_at && (
                      <>
                        <span>•</span>
                        <span>{new Date(req.created_at).toLocaleDateString()}</span>
                      </>
                    )}
                  </div>

                  {req.note && (
                    <div className="flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-400 bg-slate-50 dark:bg-slate-950 px-2.5 py-1 rounded-md">
                      <MessageSquare className="h-3 w-3 text-slate-400 shrink-0" />
                      <span className="italic">{req.note}</span>
                    </div>
                  )}
                </div>
              </div>

              <div className="flex items-center justify-between sm:justify-end gap-3 shrink-0 pt-2 sm:pt-0 border-t sm:border-t-0 border-slate-100 dark:border-slate-800">
                <div>{getStatusBadge(req.status)}</div>

                <div className="flex items-center gap-1.5">
                  {isAdmin && req.status === 'pending' && (
                    <>
                      <button
                        type="button"
                        onClick={() => setActionItem({ id: req.id, action: 'approve', title: req.title })}
                        className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white px-2.5 py-1 text-xs font-semibold shadow-xs transition"
                        title="Approve Request"
                      >
                        <Check className="h-3.5 w-3.5" /> Approve
                      </button>
                      <button
                        type="button"
                        onClick={() => setActionItem({ id: req.id, action: 'deny', title: req.title })}
                        className="inline-flex items-center gap-1 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-red-50 hover:text-red-600 text-slate-700 dark:text-slate-300 px-2.5 py-1 text-xs font-semibold transition"
                        title="Deny Request"
                      >
                        <X className="h-3.5 w-3.5" /> Deny
                      </button>
                    </>
                  )}

                  <button
                    type="button"
                    onClick={() => setDeleteId(req.id)}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/40 transition"
                    title="Delete Request"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={Inbox}
          title="No requests found"
          description={selectedStatus ? `No requests found with status "${selectedStatus}".` : "There are no media requests yet. Browse the Discover page to add requests."}
        />
      )}

      {/* Approve / Deny Modal with optional note */}
      <Modal
        isOpen={!!actionItem}
        onClose={() => setActionItem(null)}
        title={`${actionItem?.action === 'approve' ? 'Approve' : 'Deny'} Request: ${actionItem?.title}`}
      >
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-semibold uppercase text-slate-600 dark:text-slate-400 mb-1.5">
              Optional Note for the User
            </label>
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. Adding to queue now / Missing suitable release"
              className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-3.5 py-2 text-xs text-slate-900 dark:text-white"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setActionItem(null)}
              className="rounded-xl px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800 transition"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleActionSubmit}
              disabled={actionSubmitting}
              className={`rounded-xl px-4 py-2 text-xs font-semibold text-white shadow-xs transition ${
                actionItem?.action === 'approve'
                  ? 'bg-emerald-600 hover:bg-emerald-500'
                  : 'bg-red-600 hover:bg-red-500'
              }`}
            >
              {actionSubmitting ? 'Processing...' : `Confirm ${actionItem?.action === 'approve' ? 'Approval' : 'Denial'}`}
            </button>
          </div>
        </div>
      </Modal>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={!!deleteId}
        onClose={() => setDeleteId(null)}
        onConfirm={handleDelete}
        title="Delete Request"
        description="Are you sure you want to remove this media request? This will not delete any already downloaded media."
        confirmLabel="Delete"
        isDestructive
      />
    </div>
  );
};
