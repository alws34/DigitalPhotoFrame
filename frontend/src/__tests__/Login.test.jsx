import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthContext } from '../context/AuthContext';
import Login from '../pages/Login';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Render Login with a fake AuthContext value so we don't need a real API. */
function renderLogin(loginFn = vi.fn()) {
  const authValue = { login: loginFn, user: null, loading: false };
  return render(
    <AuthContext.Provider value={authValue}>
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('Login form', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the sign-in button', () => {
    renderLogin();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });

  it('renders email/username and password inputs', () => {
    renderLogin();
    expect(screen.getByLabelText(/email or username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it('shows an error when submitting with an empty identity field', async () => {
    renderLogin();
    const passwordInput = screen.getByLabelText(/password/i);
    fireEvent.change(passwordInput, { target: { value: 'secret123' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText(/please enter your email or username/i)).toBeInTheDocument();
    });
  });

  it('shows an error when submitting with an empty password field', async () => {
    renderLogin();
    const identityInput = screen.getByLabelText(/email or username/i);
    fireEvent.change(identityInput, { target: { value: 'user@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText(/please enter your password/i)).toBeInTheDocument();
    });
  });

  it('does NOT call login when the identity field is empty', async () => {
    const mockLogin = vi.fn();
    renderLogin(mockLogin);
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));
    await waitFor(() => expect(mockLogin).not.toHaveBeenCalled());
  });

  it('calls login with the correct credentials on valid submit', async () => {
    const mockLogin = vi.fn().mockResolvedValue({});
    renderLogin(mockLogin);

    fireEvent.change(screen.getByLabelText(/email or username/i), {
      target: { value: 'admin' },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'password123' },
    });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith({
        username: 'admin',
        password: 'password123',
      });
    });
  });

  it('shows the server error message when login rejects', async () => {
    const mockLogin = vi.fn().mockRejectedValue({
      response: { data: { error: 'Invalid credentials' } },
    });
    renderLogin(mockLogin);

    fireEvent.change(screen.getByLabelText(/email or username/i), {
      target: { value: 'admin' },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'wrongpass' },
    });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText('Invalid credentials')).toBeInTheDocument();
    });
  });

  it('shows a generic error message when the server returns no message', async () => {
    const mockLogin = vi.fn().mockRejectedValue(new Error('Network Error'));
    renderLogin(mockLogin);

    fireEvent.change(screen.getByLabelText(/email or username/i), {
      target: { value: 'admin' },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'pass' },
    });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText('Login failed')).toBeInTheDocument();
    });
  });
});
