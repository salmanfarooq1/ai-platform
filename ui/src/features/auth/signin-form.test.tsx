import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { SignInForm } from './signin-form'

describe('SignInForm', () => {
  it('keeps the submit button disabled until a key is typed, and masks the key', async () => {
    const user = userEvent.setup()
    render(<SignInForm onSubmit={vi.fn()} />)
    const button = screen.getByRole('button', { name: 'Sign in' })
    const input = screen.getByLabelText('API key')
    expect(button).toBeDisabled()
    expect(input).toHaveAttribute('type', 'password')
    await user.type(input, 'gap_abc_secret')
    expect(button).toBeEnabled()
  })

  it('submits the trimmed key', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<SignInForm onSubmit={onSubmit} />)
    await user.type(screen.getByLabelText('API key'), '  gap_abc_secret  ')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(onSubmit).toHaveBeenCalledWith('gap_abc_secret')
  })

  it('shows the error message, code and request id when the key is rejected', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockRejectedValue(new ApiError(401, 'invalid_credentials', 'Invalid credentials.', 'req-9'))
    render(<SignInForm onSubmit={onSubmit} />)
    await user.type(screen.getByLabelText('API key'), 'bad')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Invalid credentials.')
    expect(alert).toHaveTextContent('invalid_credentials')
    expect(alert).toHaveTextContent('req-9')
    expect(screen.getByLabelText('API key')).toHaveAttribute('aria-invalid', 'true')
  })

  it('offers the read-only preview only when a handler is given', async () => {
    const user = userEvent.setup()
    const { rerender } = render(<SignInForm onSubmit={vi.fn()} />)
    expect(screen.queryByRole('button', { name: 'Continue in read-only preview' })).not.toBeInTheDocument()
    const onPreview = vi.fn().mockResolvedValue(undefined)
    rerender(<SignInForm onSubmit={vi.fn()} onPreview={onPreview} />)
    await user.click(screen.getByRole('button', { name: 'Continue in read-only preview' }))
    expect(onPreview).toHaveBeenCalledOnce()
  })
})
