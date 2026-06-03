import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { api } from '@/lib/api'
import type { Product } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Plus, ExternalLink, ChevronRight } from 'lucide-react'

const schema = z.object({
  name: z.string().min(1, 'Required'),
  url: z.string().url('Must be a valid URL'),
  description: z.string().optional(),
})
type FormData = z.infer<typeof schema>

export default function ProductsPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)

  const { data: products = [], isLoading } = useQuery<Product[]>({
    queryKey: ['products'],
    queryFn: () => api.get('/products'),
  })

  const { register, handleSubmit, reset, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
  })

  const create = useMutation({
    mutationFn: (data: FormData) => api.post<Product>('/products', data),
    onSuccess: (product) => {
      qc.invalidateQueries({ queryKey: ['products'] })
      setOpen(false)
      reset()
      navigate(`/products/${product.id}`)
    },
  })

  return (
    <div className="p-8 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold">Products</h1>
        <Button onClick={() => setOpen(true)} className="bg-cyan-500 hover:bg-cyan-400 text-black">
          <Plus className="h-4 w-4 mr-2" />
          New product
        </Button>
      </div>

      <div className="mb-6 rounded-lg border border-white/10 bg-white/5 px-4 py-4 text-sm text-gray-400 space-y-3">
        <p className="font-medium text-white">What this does</p>
        <p>
          Point the agent at a URL. It crawls the site, understands what's there, writes a test suite
          for it, and runs that suite against the live product — with no selectors, no step definitions,
          and no test code to maintain.
        </p>
        <ul className="space-y-1.5 text-xs">
          <li>
            A <span className="font-medium text-white">Product</span> is a target site.{' '}
            <span className="font-medium text-white">Scanning</span> it sends the LLM-driven
            analyst to explore it and produce{' '}
            <span className="font-medium text-white">Specs</span> — Gherkin feature files
            containing <span className="font-medium text-white">Scenarios</span> (one
            Given/When/Then test case each). Scans also surface{' '}
            <span className="font-medium text-white">Issues</span>: console errors, broken
            images, and failed network requests the agent observes while crawling.
          </li>
          <li>
            A <span className="font-medium text-white">Run</span> executes your approved
            scenarios against the live product. The executor LLM interprets each step, drives the
            browser, and reports pass/fail with the reasoning behind every verdict.
          </li>
        </ul>
        <p className="text-xs">
          Because the LLM reads the page like a human (via the accessibility tree, not selectors),
          the same spec keeps working when the UI is restyled or restructured.
        </p>
      </div>

      {isLoading ? (
        <p className="text-muted-foreground text-sm">Loading…</p>
      ) : products.length === 0 ? (
        <div className="border border-white/10 rounded-lg p-12 text-center text-gray-400">
          <p className="mb-4">No products yet.</p>
          <Button variant="outline" onClick={() => setOpen(true)} className="border-white/20 text-gray-300 hover:bg-white/10 hover:text-white">
            <Plus className="h-4 w-4 mr-2" />
            Add your first product
          </Button>
        </div>
      ) : (
        <div className="border border-white/10 rounded-lg overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="border-b border-white/10 hover:bg-transparent">
                <TableHead className="text-gray-400">Name</TableHead>
                <TableHead className="text-gray-400">URL</TableHead>
                <TableHead className="text-gray-400">Status</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {products.map(p => (
                <TableRow
                  key={p.id}
                  className="cursor-pointer border-b border-white/10 hover:bg-white/5"
                  onClick={() => navigate(`/products/${p.id}`)}
                >
                  <TableCell className="font-medium text-white">{p.name}</TableCell>
                  <TableCell>
                    <span
                      className="text-gray-400 text-sm flex items-center gap-1 hover:text-white"
                      onClick={e => { e.stopPropagation(); window.open(p.url, '_blank') }}
                    >
                      {p.url}
                      <ExternalLink className="h-3 w-3" />
                    </span>
                  </TableCell>
                  <TableCell>
                    <Badge className={p.active
                      ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                      : 'bg-white/5 text-gray-400 border border-white/10'}>
                      {p.active ? 'active' : 'inactive'}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <ChevronRight className="h-4 w-4 text-gray-500" />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-[#0d1024] border border-white/10 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">New product</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit(d => create.mutate(d))}>
            <div className="space-y-4 py-2">
              <div className="space-y-1.5">
                <Label className="text-gray-300">Name</Label>
                <Input
                  {...register('name')}
                  placeholder="My App"
                  className="bg-white/5 border-white/10 text-white placeholder:text-gray-600 focus:border-cyan-500/50"
                />
                {errors.name && <p className="text-xs text-red-400">{errors.name.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label className="text-gray-300">URL</Label>
                <Input
                  {...register('url')}
                  placeholder="https://myapp.example.com"
                  className="bg-white/5 border-white/10 text-white placeholder:text-gray-600 focus:border-cyan-500/50"
                />
                {errors.url && <p className="text-xs text-red-400">{errors.url.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label className="text-gray-300">
                  Description <span className="text-gray-500 font-normal">(optional)</span>
                </Label>
                <Textarea
                  {...register('description')}
                  placeholder="Short description for the analyst"
                  rows={3}
                  className="bg-white/5 border-white/10 text-white placeholder:text-gray-600 focus:border-cyan-500/50 resize-none"
                />
              </div>
            </div>
            <DialogFooter className="mt-6">
              <Button
                type="button"
                variant="ghost"
                onClick={() => { setOpen(false); reset() }}
                className="text-gray-400 hover:bg-white/10 hover:text-white"
              >
                Cancel
              </Button>
              <Button type="submit" disabled={create.isPending} className="bg-cyan-500 hover:bg-cyan-400 text-black">
                {create.isPending ? 'Creating…' : 'Create'}
              </Button>
            </DialogFooter>
            {create.isError && (
              <p className="text-xs text-red-400 mt-2">
                {create.error instanceof Error ? create.error.message : 'Error'}
              </p>
            )}
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
