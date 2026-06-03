import { useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { lazy, Suspense } from 'react'
import { api } from '@/lib/api'
import type { Spec } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { ArrowLeft, Save, CheckCircle2, Loader2 } from 'lucide-react'
import { useToast } from '@/hooks/use-toast'

const MonacoEditor = lazy(() => import('@monaco-editor/react'))

function monacoLang(filename: string): string {
  if (filename.endsWith('.yaml') || filename.endsWith('.yml')) return 'yaml'
  if (filename.endsWith('.json')) return 'json'
  return 'plaintext'
}

export default function SpecEditorPage() {
  const { id, '*': filename = '' } = useParams<{ id: string; '*': string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { toast } = useToast()
  const [draft, setDraft] = useState<string | undefined>(undefined)
  const [dirty, setDirty] = useState(false)

  const { data: spec, isLoading } = useQuery<Spec>({
    queryKey: ['spec', id, filename],
    queryFn: () => api.get(`/products/${id}/specs/${filename}`),
    enabled: !!id && !!filename,
  })

  const handleEditorChange = useCallback((value: string | undefined) => {
    setDraft(value)
    setDirty(value !== spec?.content)
  }, [spec?.content])

  const save = useMutation({
    mutationFn: () => api.put(`/products/${id}/specs/${filename}`, { content: draft ?? spec?.content }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['spec', id, filename] })
      qc.invalidateQueries({ queryKey: ['specs', id] })
      setDirty(false)
      toast({ title: 'Saved' })
    },
    onError: (e) => toast({ title: 'Save failed', description: e instanceof Error ? e.message : 'Error', variant: 'destructive' }),
  })

  const approve = useMutation({
    mutationFn: (approved: boolean) =>
      api.post(`/products/${id}/specs/${filename}/approve`, { approved }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['spec', id, filename] })
      qc.invalidateQueries({ queryKey: ['specs', id] })
      toast({ title: spec?.approved ? 'Approval removed' : 'Approved' })
    },
    onError: (e) => toast({ title: 'Failed', description: e instanceof Error ? e.message : 'Error', variant: 'destructive' }),
  })

  if (isLoading) return <div className="p-8 text-sm text-muted-foreground">Loading…</div>
  if (!spec) return <div className="p-8 text-sm text-muted-foreground">Spec not found.</div>

  const content = draft ?? spec.content

  return (
    <div className="flex flex-col h-screen">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-2 border-b bg-background">
        <button
          onClick={() => navigate(`/products/${id}`)}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          {filename}
        </button>
        <Separator orientation="vertical" className="h-4" />
        {filename !== 'config.yaml' && (
          <Badge variant={spec.approved ? 'default' : 'secondary'}>
            {spec.approved ? 'approved' : 'draft'}
          </Badge>
        )}

        <div className="ml-auto flex items-center gap-2">
          {filename !== 'config.yaml' && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => approve.mutate(!spec.approved)}
              disabled={approve.isPending || dirty}
              title={dirty ? 'Save before approving' : undefined}
            >
              {approve.isPending
                ? <Loader2 className="h-4 w-4 animate-spin" />
                : <CheckCircle2 className="h-4 w-4" />
              }
              {spec.approved ? 'Unapprove' : 'Approve'}
            </Button>
          )}
          <Button
            size="sm"
            onClick={() => save.mutate()}
            disabled={!dirty || save.isPending}
          >
            {save.isPending
              ? <Loader2 className="h-4 w-4 mr-1 animate-spin" />
              : <Save className="h-4 w-4 mr-1" />
            }
            Save
          </Button>
        </div>
      </div>

      {/* Editor */}
      <div className="flex-1 overflow-hidden">
        <Suspense fallback={
          <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin mr-2" /> Loading editor…
          </div>
        }>
          <MonacoEditor
            height="100%"
            language={monacoLang(filename)}
            value={content}
            onChange={handleEditorChange}
            options={{
              minimap: { enabled: false },
              fontSize: 13,
              lineNumbers: 'on',
              wordWrap: 'on',
              scrollBeyondLastLine: false,
              tabSize: 2,
            }}
          />
        </Suspense>
      </div>
    </div>
  )
}
