import React, { useState, useEffect } from 'react';
import { indexersApi } from '@/api';
import { ErrorCard } from '@/components/common/ErrorCard';
import { TableSkeleton } from '@/components/common/Skeleton';
import { EmptyState } from '@/components/common/EmptyState';
import { Modal } from '@/components/common/Modal';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import type { Indexer, IndexerSchema } from '@/types/api';
import {
  Search,
  Plus,
  Play,
  Trash2,
  CheckCircle2,
  XCircle,
  Globe,
  Lock,
  Radio,
} from 'lucide-react';

export const Indexers: React.FC = () => {
  const [indexers, setIndexers] = useState<Indexer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  // Testing indexers
  const [testing, setTesting] = useState(false);
  const [testResults, setTestResults] = useState<Record<number, { isValid: boolean; errors?: string[] }>>({});

  // Add Indexer Modal
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [schemas, setSchemas] = useState<IndexerSchema[]>([]);
  const [schemasLoading, setSchemasLoading] = useState(false);
  const [schemaSearch, setSchemaSearch] = useState('');
  const [privacyFilter, setPrivacyFilter] = useState<'all' | 'public' | 'private'>('all');
  const [protocolFilter, setProtocolFilter] = useState<'all' | 'torrent' | 'usenet'>('all');

  const [selectedSchema, setSelectedSchema] = useState<IndexerSchema | null>(null);
  const [formFields, setFormFields] = useState<Record<string, unknown>>({});
  const [addingIndexer, setAddingIndexer] = useState(false);

  // Delete confirm
  const [deleteId, setDeleteId] = useState<number | null>(null);

  useEffect(() => {
    loadIndexers();
  }, []);

  const loadIndexers = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await indexersApi.getIndexers();
      setIndexers(data);
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = async (id: number, currentEnabled: boolean) => {
    try {
      await indexersApi.setEnabled(id, !currentEnabled);
      setIndexers((prev) =>
        prev.map((idx) => (idx.id === id ? { ...idx, enabled: !currentEnabled } : idx))
      );
    } catch (err: unknown) {
      setError(err as Error);
    }
  };

  const handleTestAll = async () => {
    setTesting(true);
    setError(null);
    try {
      const res = await indexersApi.testAll();
      const mapped: Record<number, { isValid: boolean; errors?: string[] }> = {};
      for (const item of res) {
        mapped[item.id] = { isValid: item.isValid, errors: item.errors };
      }
      setTestResults(mapped);
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setTesting(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteId) return;
    try {
      await indexersApi.deleteIndexer(deleteId);
      setDeleteId(null);
      await loadIndexers();
    } catch (err: unknown) {
      setError(err as Error);
    }
  };

  const openAddModal = async () => {
    setAddModalOpen(true);
    setSelectedSchema(null);
    setFormFields({});
    if (schemas.length === 0) {
      setSchemasLoading(true);
      try {
        const list = await indexersApi.getSchemas();
        setSchemas(list);
      } catch (err: unknown) {
        setError(err as Error);
      } finally {
        setSchemasLoading(false);
      }
    }
  };

  const handleSelectSchema = (schema: IndexerSchema) => {
    setSelectedSchema(schema);
    const initial: Record<string, unknown> = {};
    if (schema.required_fields) {
      for (const f of schema.required_fields) {
        initial[f.name] = f.value ?? '';
      }
    }
    setFormFields(initial);
  };

  const handleCreateIndexer = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedSchema) return;

    setAddingIndexer(true);
    setError(null);
    try {
      await indexersApi.createIndexer({
        definition_name: selectedSchema.name,
        fields: formFields,
      });
      setAddModalOpen(false);
      setSelectedSchema(null);
      await loadIndexers();
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setAddingIndexer(false);
    }
  };

  const filteredSchemas = schemas.filter((s) => {
    if (privacyFilter !== 'all' && s.privacy !== privacyFilter) return false;
    if (protocolFilter !== 'all' && s.protocol !== protocolFilter) return false;
    if (schemaSearch.trim()) {
      const q = schemaSearch.toLowerCase();
      return (
        s.name.toLowerCase().includes(q) ||
        (s.description && s.description.toLowerCase().includes(q))
      );
    }
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
            <Radio className="h-6 w-6 text-brand-600 dark:text-brand-400" />
            Indexers & Trackers
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            An indexer is a search engine for torrents and media releases that feeds downloads to Radarr and Sonarr automatically.
          </p>
        </div>

        <div className="flex items-center gap-2.5 self-start sm:self-auto">
          <button
            type="button"
            onClick={handleTestAll}
            disabled={testing || indexers.length === 0}
            className="flex items-center gap-1.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3.5 py-2 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition disabled:opacity-50"
          >
            <Play className={`h-3.5 w-3.5 ${testing ? 'animate-spin' : ''}`} />
            {testing ? 'Testing...' : 'Test All'}
          </button>
          <button
            type="button"
            onClick={openAddModal}
            className="flex items-center gap-1.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white px-4 py-2 text-xs font-semibold shadow-xs transition"
          >
            <Plus className="h-4 w-4" /> Add Indexer
          </button>
        </div>
      </div>

      <ErrorCard error={error} onDismiss={() => setError(null)} />

      {/* Indexers List */}
      {loading ? (
        <TableSkeleton rows={3} />
      ) : indexers.length > 0 ? (
        <div className="space-y-3">
          {indexers.map((idx) => {
            const test = testResults[idx.id];
            return (
              <div
                key={idx.id}
                className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-xs"
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`h-3 w-3 rounded-full ${
                      idx.enabled ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-700'
                    }`}
                  />
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-slate-900 dark:text-white">{idx.name}</span>
                      <span className="rounded bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[10px] font-semibold text-slate-600 dark:text-slate-300 uppercase">
                        {idx.protocol}
                      </span>
                      {idx.privacy && (
                        <span className="rounded bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[10px] font-semibold text-slate-600 dark:text-slate-300 capitalize flex items-center gap-1">
                          {idx.privacy === 'private' ? <Lock className="h-2.5 w-2.5" /> : <Globe className="h-2.5 w-2.5" />}
                          {idx.privacy}
                        </span>
                      )}
                    </div>
                    {idx.status && <div className="text-xs text-slate-500 mt-0.5">{idx.status}</div>}

                    {test && (
                      <div className="mt-1 flex items-center gap-1.5 text-xs">
                        {test.isValid ? (
                          <span className="text-emerald-600 font-semibold flex items-center gap-1">
                            <CheckCircle2 className="h-3 w-3" /> Connection OK
                          </span>
                        ) : (
                          <span className="text-red-600 font-semibold flex items-center gap-1">
                            <XCircle className="h-3 w-3" /> Test failed: {test.errors?.join(', ') || 'Unreachable'}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-3 self-end sm:self-auto">
                  <label className="flex items-center gap-2 text-xs font-semibold text-slate-700 dark:text-slate-300 cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={idx.enabled}
                      onChange={() => handleToggle(idx.id, idx.enabled)}
                      className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500 dark:border-slate-700 dark:bg-slate-800"
                    />
                    <span>{idx.enabled ? 'Enabled' : 'Disabled'}</span>
                  </label>

                  <button
                    type="button"
                    onClick={() => setDeleteId(idx.id)}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/40 transition"
                    title="Remove indexer"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : error ? null : (
        <EmptyState
          icon={Radio}
          title="No indexers configured"
          description="Indexers allow your apps to find downloads. Click 'Add Indexer' to enable public or private torrent search."
          actionLabel="Add an Indexer"
          onAction={openAddModal}
        />
      )}

      {/* Add Indexer Modal */}
      <Modal
        isOpen={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        title={selectedSchema ? `Configure ${selectedSchema.name}` : 'Add Indexer from Catalogue'}
        maxWidth="lg"
      >
        {!selectedSchema ? (
          <div className="space-y-4">
            {/* Search and Filters */}
            <div className="space-y-2">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <input
                  type="search"
                  value={schemaSearch}
                  onChange={(e) => setSchemaSearch(e.target.value)}
                  placeholder="Search indexers (e.g. 1337x, RARBG, TorrentGalaxy)..."
                  className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 pl-9 pr-3 py-2 text-xs"
                />
              </div>

              <div className="flex flex-wrap items-center gap-2 text-xs">
                <div className="flex items-center gap-1 rounded-lg bg-slate-100 dark:bg-slate-800 p-0.5">
                  {(['all', 'public', 'private'] as const).map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => setPrivacyFilter(p)}
                      className={`px-2 py-0.5 rounded capitalize font-medium ${
                        privacyFilter === p ? 'bg-white dark:bg-slate-900 shadow-xs text-brand-600 dark:text-brand-400 font-bold' : 'text-slate-500'
                      }`}
                    >
                      {p}
                    </button>
                  ))}
                </div>

                <div className="flex items-center gap-1 rounded-lg bg-slate-100 dark:bg-slate-800 p-0.5">
                  {(['all', 'torrent', 'usenet'] as const).map((prot) => (
                    <button
                      key={prot}
                      type="button"
                      onClick={() => setProtocolFilter(prot)}
                      className={`px-2 py-0.5 rounded capitalize font-medium ${
                        protocolFilter === prot ? 'bg-white dark:bg-slate-900 shadow-xs text-brand-600 dark:text-brand-400 font-bold' : 'text-slate-500'
                      }`}
                    >
                      {prot}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Schemas List */}
            {schemasLoading ? (
              <div className="py-8 text-center text-xs text-slate-500">Loading catalog...</div>
            ) : filteredSchemas.length > 0 ? (
              <div className="max-h-72 overflow-y-auto space-y-2 pr-1">
                {filteredSchemas.slice(0, 50).map((s) => (
                  <button
                    key={s.name}
                    type="button"
                    onClick={() => handleSelectSchema(s)}
                    className="w-full text-left p-3 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-brand-500 bg-slate-50/50 dark:bg-slate-950/50 hover:bg-white dark:hover:bg-slate-900 transition flex items-center justify-between"
                  >
                    <div>
                      <div className="font-bold text-xs text-slate-900 dark:text-white flex items-center gap-2">
                        {s.name}
                        <span className="text-[10px] uppercase font-normal text-slate-400">
                          {s.protocol}
                        </span>
                        {s.privacy && (
                          <span className="text-[10px] text-slate-400">({s.privacy})</span>
                        )}
                      </div>
                      {s.description && (
                        <p className="text-[11px] text-slate-500 line-clamp-1 mt-0.5">
                          {s.description}
                        </p>
                      )}
                    </div>
                    <Plus className="h-4 w-4 text-brand-600 dark:text-brand-400 shrink-0" />
                  </button>
                ))}
              </div>
            ) : (
              <div className="py-6 text-center text-xs text-slate-500">No matching indexers found.</div>
            )}
          </div>
        ) : (
          /* Configure Selected Schema Form */
          <form onSubmit={handleCreateIndexer} className="space-y-4">
            <div className="p-3 rounded-xl bg-brand-50 dark:bg-brand-950/40 text-xs text-brand-900 dark:text-brand-200">
              Configuring <span className="font-bold">{selectedSchema.name}</span>. Most public indexers require no special settings.
            </div>

            {selectedSchema.required_fields && selectedSchema.required_fields.length > 0 ? (
              <div className="space-y-3 max-h-64 overflow-y-auto pr-1">
                {selectedSchema.required_fields.map((f) => (
                  <div key={f.name}>
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                      {f.label || f.name}
                    </label>
                    <input
                      type={f.type === 'password' ? 'password' : 'text'}
                      value={(formFields[f.name] as string) || ''}
                      onChange={(e) =>
                        setFormFields((prev) => ({ ...prev, [f.name]: e.target.value }))
                      }
                      placeholder={f.helpText || ''}
                      className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-3 py-2 text-xs"
                    />
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-500">
                This indexer is ready to be added with default community settings.
              </p>
            )}

            <div className="flex justify-between items-center pt-2">
              <button
                type="button"
                onClick={() => setSelectedSchema(null)}
                className="text-xs font-semibold text-slate-500 hover:text-slate-800"
              >
                ← Back to list
              </button>

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setAddModalOpen(false)}
                  className="rounded-xl px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={addingIndexer}
                  className="rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold px-4 py-1.5 shadow-xs transition"
                >
                  {addingIndexer ? 'Adding...' : 'Add Indexer'}
                </button>
              </div>
            </div>
          </form>
        )}
      </Modal>

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={!!deleteId}
        onClose={() => setDeleteId(null)}
        onConfirm={handleDelete}
        title="Remove Indexer"
        description="Are you sure you want to delete this indexer? Prowlarr will remove it from Radarr and Sonarr automatically."
        confirmLabel="Remove"
        isDestructive
      />
    </div>
  );
};
