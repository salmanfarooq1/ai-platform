import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { Button } from './button'
import { Card } from './card'
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from './dialog'
import { Input } from './input'
import { Segmented } from './segmented'
import { Skeleton } from './skeleton'

describe('Button', () => {
  it('is ink by default, not the seal color', () => {
    render(<Button>Save</Button>)
    const cls = screen.getByRole('button', { name: 'Save' }).className
    expect(cls).toMatch(/bg-ink/)
    expect(cls).not.toMatch(/seal|brand/)
  })

  it('has secondary, ghost and danger variants, and sizes', () => {
    render(<><Button variant="secondary">A</Button><Button variant="ghost">B</Button><Button variant="danger" size="sm">C</Button></>)
    expect(screen.getByRole('button', { name: 'A' }).className).toMatch(/border-hairline/)
    expect(screen.getByRole('button', { name: 'B' }).className).toMatch(/text-fg-secondary/)
    expect(screen.getByRole('button', { name: 'C' }).className).toMatch(/text-deny/)
    expect(screen.getByRole('button', { name: 'C' }).className).toMatch(/h-8/)
  })

  it('is disabled and does not fire', async () => {
    const onClick = vi.fn()
    render(<Button disabled onClick={onClick}>Go</Button>)
    await userEvent.click(screen.getByRole('button', { name: 'Go' }))
    expect(onClick).not.toHaveBeenCalled()
  })

  it('can render as a link with asChild', () => {
    render(<Button asChild><a href="/x">Open</a></Button>)
    expect(screen.getByRole('link', { name: 'Open' })).toHaveAttribute('href', '/x')
  })
})

describe('Card', () => {
  it('is 8px in the console and 12px in the workspace', () => {
    render(<><Card data-testid="c">a</Card><Card surface="workspace" data-testid="w">b</Card></>)
    expect(screen.getByTestId('c').className).toMatch(/rounded-sm/)
    expect(screen.getByTestId('w').className).toMatch(/rounded-md/)
  })
})

describe('Input', () => {
  it('uses the seal color for its focus ring and marks an invalid value', () => {
    render(<Input aria-label="Key" aria-invalid />)
    const input = screen.getByLabelText('Key')
    expect(input.className).toMatch(/outline-seal/)
    expect(input).toHaveAttribute('aria-invalid', 'true')
  })
})

describe('Segmented', () => {
  function Harness({ onChange }: { onChange: (v: string) => void }) {
    const [v, setV] = useState('a')
    return <Segmented label="Pick" value={v} onChange={(x) => { setV(x); onChange(x) }} options={[{ value: 'a', label: 'One' }, { value: 'b', label: 'Two' }]} />
  }

  it('is a labelled single-select radio group', async () => {
    const onChange = vi.fn()
    render(<Harness onChange={onChange} />)
    expect(screen.getByRole('radiogroup', { name: 'Pick' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'One' })).toBeChecked()
    await userEvent.click(screen.getByRole('radio', { name: 'Two' }))
    expect(onChange).toHaveBeenCalledWith('b')
    expect(screen.getByRole('radio', { name: 'Two' })).toBeChecked()
  })

  it('does not let the selection be cleared by clicking it again', async () => {
    const onChange = vi.fn()
    render(<Harness onChange={onChange} />)
    await userEvent.click(screen.getByRole('radio', { name: 'One' }))
    expect(onChange).not.toHaveBeenCalled()
    expect(screen.getByRole('radio', { name: 'One' })).toBeChecked()
  })
})

describe('Skeleton', () => {
  it('is hidden from assistive technology', () => {
    const { container } = render(<Skeleton className="h-6" />)
    expect(container.firstElementChild).toHaveAttribute('aria-hidden', 'true')
  })
})

describe('Dialog', () => {
  it('opens, names itself, and closes with Escape', async () => {
    render(
      <Dialog>
        <DialogTrigger>Open</DialogTrigger>
        <DialogContent><DialogTitle>Title</DialogTitle><DialogDescription>Text</DialogDescription></DialogContent>
      </Dialog>,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Open' }))
    expect(screen.getByRole('dialog', { name: 'Title' })).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open' })).toHaveFocus()
  })
})
