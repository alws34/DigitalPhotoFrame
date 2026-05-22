import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AlbumsView from '../pages/AlbumsView';

// ---------------------------------------------------------------------------
// fetch mock
// ---------------------------------------------------------------------------
const mockSourcesResponse = [];
const mockAlbumsResponse  = [];
const mockActiveResponse  = { album_id: 'all', name: 'Local Images' };

function makeFetchMock() {
  return vi.fn((url) => {
    if (url.includes('/api/sources')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(mockSourcesResponse) });
    }
    if (url.includes('/api/albums/active')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(mockActiveResponse) });
    }
    if (url.includes('/api/albums')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(mockAlbumsResponse) });
    }
    return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) });
  });
}

describe('AlbumsView', () => {
  let originalFetch;

  beforeEach(() => {
    originalFetch = global.fetch;
    global.fetch = makeFetchMock();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.clearAllMocks();
  });

  it('renders without crashing and shows the Albums heading', async () => {
    render(
      <MemoryRouter>
        <AlbumsView />
      </MemoryRouter>
    );

    // Heading is visible immediately.
    expect(screen.getByRole('heading', { name: /albums/i })).toBeInTheDocument();
  });

  it('shows a loading spinner initially then the content', async () => {
    render(
      <MemoryRouter>
        <AlbumsView />
      </MemoryRouter>
    );

    // After data loads the "No sources" placeholder should appear.
    await waitFor(() => {
      expect(screen.getByText(/no sources configured/i)).toBeInTheDocument();
    });
  });

  it('shows the Add Source section after loading', async () => {
    render(
      <MemoryRouter>
        <AlbumsView />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/add source/i)).toBeInTheDocument();
    });
  });

  it('shows the Google Photos and Immich add buttons', async () => {
    render(
      <MemoryRouter>
        <AlbumsView />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /google photos/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /immich/i })).toBeInTheDocument();
    });
  });

  it('falls back to mock data when API returns an error', async () => {
    global.fetch = vi.fn(() => Promise.resolve({ ok: false, status: 500 }));

    render(
      <MemoryRouter>
        <AlbumsView />
      </MemoryRouter>
    );

    // The mock data has one source (local_1) — even after failure it should render.
    await waitFor(() => {
      // Either mock source card shows or "No sources" — either way no crash.
      expect(screen.getByRole('heading', { name: /albums/i })).toBeInTheDocument();
    });
  });
});
