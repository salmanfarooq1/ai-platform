import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { api } from '@/api/endpoints'
import { isApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'

interface UploadDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  kb: string
  onDone: () => void
}

export function UploadDialog({ open, onOpenChange, kb, onDone }: UploadDialogProps) {
  const [file, setFile] = useState<File | null>(null)
  const m = useMutation({
    mutationFn: (f: File) => api.ingest(f, kb),
    onSuccess: () => { onDone() },
  })

  function submit(e: FormEvent) {
    e.preventDefault()
    if (file) m.mutate(file)
  }
  function change(next: boolean) {
    if (!next) { setFile(null); m.reset() }
    onOpenChange(next)
  }

  return (
    <Dialog open={open} onOpenChange={change}>
      <DialogContent>
        <DialogTitle>Add documents</DialogTitle>
        <DialogDescription>The file is split into passages in the <code className="mono">{kb}</code> knowledge base.</DialogDescription>
        <form onSubmit={submit} className="mt-4 flex flex-col gap-3">
          <label htmlFor="upload-file" className="text-callout font-medium">File</label>
          <Input id="upload-file" type="file" accept=".pdf,.txt,.md,.docx,.html,.csv" className="h-auto py-1.5" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          {m.error ? (
            <p role="alert" className="text-callout text-deny">
              {m.error instanceof Error ? m.error.message : 'Upload failed.'}
              <span className="mono ml-2 text-footnote">{isApiError(m.error) ? `${m.error.code} ${m.error.requestId ?? ''}` : ''}</span>
            </p>
          ) : null}
          {m.data ? (
            <p role="status" className="text-callout text-allow">
              Queued: {file?.name ?? 'the file'} is stored and will be ingested. Close this and watch its status in the table.
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => change(false)}>Close</Button>
            <Button type="submit" disabled={!file || m.isPending}>{m.isPending ? 'Uploading' : 'Upload'}</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
