import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { Upload, Trash2, Image as ImageIcon, Loader2, X } from 'lucide-react';

function encodeImagePath(p) {
  return p.split('/').map(encodeURIComponent).join('/');
}

const overlayStyle = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
};
const modalStyle = {
  background: 'rgba(20,25,40,0.98)', border: '1px solid var(--glass-border)',
  borderRadius: '16px', padding: '2rem', width: '520px', maxWidth: '92vw',
  boxShadow: 'var(--glass-shadow)', maxHeight: '90vh', overflowY: 'auto',
};

export default function GalleryView() {
  const [images, setImages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [activeAlbum, setActiveAlbum] = useState(null);
  const activeAlbumRef = useRef(null);
  const [alerts, setAlerts] = useState([]);

  const [selectedImage, setSelectedImage] = useState(null);
  const [editState, setEditState] = useState({ filename: '', uploader: '', location: '' });
  const [metaHash, setMetaHash] = useState(null);
  const [metaLoading, setMetaLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');

  const dismissAlert = (idx) => setAlerts((prev) => prev.filter((_, i) => i !== idx));

  const fetchImages = async () => {
    setFetchError('');
    try {
      const res = await axios.get('/api/images');
      setImages(res.data);
    } catch (err) {
      if (err?.response?.status !== 401) {
        console.error('Failed to fetch images', err);
        setFetchError(err?.response?.data?.error || 'Failed to load photos. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchImages();

    const poll = async () => {
      try {
        const res = await axios.get('/api/albums/active', { withCredentials: true });
        const id = res.data?.album_id ?? null;
        if (id !== activeAlbumRef.current) {
          activeAlbumRef.current = id;
          setActiveAlbum(res.data);
          fetchImages();
        } else if (id && id !== 'all') {
          fetchImages();
        }
      } catch {
        // ignore — AlbumManager may not be available
      }
    };
    poll();
    const timer = setInterval(poll, 5000);
    return () => clearInterval(timer);
  }, []);

  const openModal = async (img) => {
    setSelectedImage(img);
    setEditState({ filename: img.name, uploader: '', location: '' });
    setMetaHash(null);
    setSaveError('');
    setMetaLoading(true);
    try {
      const res = await axios.get(`/api/images/metadata?filename=${encodeURIComponent(img.name)}`);
      const meta = res.data;
      setMetaHash(meta.hash || null);
      setEditState({
        filename: meta.filename || img.name,
        uploader: meta.uploader || '',
        location: meta.location || '',
      });
    } catch (err) {
      console.error('Failed to fetch metadata', err);
    } finally {
      setMetaLoading(false);
    }
  };

  const closeModal = () => {
    setSelectedImage(null);
    setMetaHash(null);
    setSaveError('');
  };

  const handleSave = async () => {
    if (!metaHash) return;
    setSaving(true);
    setSaveError('');
    try {
      const originalName = selectedImage.name;
      const res = await axios.post('/api/images/metadata', {
        hash: metaHash,
        uploader: editState.uploader,
        location: editState.location,
        caption: '',
        new_filename: editState.filename !== originalName ? editState.filename : undefined,
      });
      const updatedName = res.data.filename || editState.filename;
      await fetchImages();
      setSelectedImage({ ...selectedImage, name: updatedName });
      setEditState((s) => ({ ...s, filename: updatedName }));
    } catch (err) {
      setSaveError(err?.response?.data?.error || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleFileUpload = async (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;

    setUploading(true);
    setUploadProgress(0);

    const BATCH_SIZE = 5;
    const batches = [];
    for (let i = 0; i < files.length; i += BATCH_SIZE) {
      batches.push(files.slice(i, i + BATCH_SIZE));
    }

    let completedBatches = 0;
    let errorCount = 0;

    try {
      for (const batch of batches) {
        const formData = new FormData();
        batch.forEach(f => formData.append('file[]', f));

        try {
          await axios.post('/api/images/upload', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
            onUploadProgress: ({ loaded, total }) => {
              const batchFraction = total ? loaded / total : 0;
              const overall = Math.round(((completedBatches + batchFraction) / batches.length) * 100);
              setUploadProgress(Math.min(overall, 99));
            },
          });
        } catch (err) {
          errorCount++;
          console.error('Batch upload error', err);
        }

        completedBatches++;
        setUploadProgress(Math.round((completedBatches / batches.length) * 100));
      }

      await fetchImages();

      if (errorCount > 0) {
        setAlerts((prev) => [
          ...prev,
          `Upload finished with ${errorCount} batch error(s). Some photos may not have been saved.`,
        ]);
      }
    } finally {
      setUploading(false);
      setUploadProgress(0);
      e.target.value = '';
    }
  };

  const handleDelete = async (filename) => {
    if (!window.confirm(`Delete ${filename}?`)) return;
    try {
      await axios.delete(`/api/images/${encodeImagePath(filename)}`);
      setImages(prev => prev.filter(img => img.name !== filename));
      if (selectedImage?.name === filename) closeModal();
    } catch (err) {
      console.error('Delete failed', err);
      setAlerts((prev) => [
        ...prev,
        err?.response?.data?.error || 'Delete failed. Please try again.',
      ]);
    }
  };

  return (
    <div style={{ padding: '2rem', maxWidth: '1400px', margin: '0 auto' }}>
      <header style={{ marginBottom: '2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '2rem', fontWeight: 600 }}>Gallery</h1>
          <p style={{ margin: '0.5rem 0 0', color: 'var(--text-secondary)' }}>
            {activeAlbum && activeAlbum.name ? `${activeAlbum.name} · ` : ''}{images.length} photos
          </p>
        </div>

        <div>
          <label
            htmlFor="upload-images"
            className="primary"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.6em 1.2em',
              borderRadius: '8px',
              backgroundColor: 'var(--primary)',
              color: 'white',
              cursor: uploading ? 'not-allowed' : 'pointer',
              opacity: uploading ? 0.7 : 1,
              fontWeight: 500
            }}
          >
            {uploading ? <Loader2 size={18} className="spin" /> : <Upload size={18} />}
            {uploading ? `Uploading… ${uploadProgress}%` : 'Upload Photos'}
          </label>
          <input
            type="file"
            id="upload-images"
            multiple
            accept="image/*,.heic,.heif"
            style={{ display: 'none' }}
            onChange={handleFileUpload}
            disabled={uploading}
          />
        </div>
      </header>

      {/* Fetch error banner */}
      {fetchError && (
        <div style={{
          background: 'rgba(220,50,50,0.15)', border: '1px solid var(--danger)',
          borderRadius: '8px', padding: '0.75rem 1rem', marginBottom: '1rem',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem',
        }}>
          <span style={{ color: 'var(--danger)', fontSize: '0.9rem' }}>{fetchError}</span>
          <button
            onClick={() => fetchImages()}
            style={{ fontSize: '0.85rem', padding: '0.3rem 0.8rem', flexShrink: 0 }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Dismissible alert list */}
      {alerts.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '1rem' }}>
          {alerts.map((msg, idx) => (
            <div
              key={idx}
              style={{
                background: 'rgba(220,50,50,0.15)', border: '1px solid var(--danger)',
                borderRadius: '8px', padding: '0.75rem 1rem',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem',
              }}
            >
              <span style={{ color: 'var(--danger)', fontSize: '0.9rem' }}>{msg}</span>
              <button
                onClick={() => dismissAlert(idx)}
                aria-label="Dismiss"
                style={{ background: 'none', border: 'none', padding: '2px', color: 'var(--danger)', cursor: 'pointer', display: 'flex', flexShrink: 0 }}
              >
                <X size={16} />
              </button>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '4rem', color: 'var(--text-secondary)' }}>
          <Loader2 size={32} className="spin" />
        </div>
      ) : images.length === 0 ? (
        <div className="glass-panel fade-in" style={{ padding: '4rem 2rem', textAlign: 'center' }}>
          <ImageIcon size={48} color="var(--text-secondary)" style={{ marginBottom: '1rem', opacity: 0.5 }} />
          <h3>No Photos Found</h3>
          <p style={{ color: 'var(--text-secondary)' }}>Upload some photos to see them here.</p>
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))',
          gap: '1.5rem'
        }}>
          {images.map((img, idx) => (
            <div
              key={img.name}
              className="glass-panel fade-in"
              style={{
                overflow: 'hidden',
                position: 'relative',
                animationDelay: `${idx * 0.05}s`,
                cursor: 'pointer',
              }}
              onClick={() => openModal(img)}
            >
              <div style={{ aspectRatio: '4/3', backgroundColor: '#000' }}>
                <img
                  src={`/api/images/thumb/${encodeImagePath(img.name)}?w=400`}
                  alt={img.name}
                  loading="lazy"
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  onError={(e) => {
                    e.target.src = `/api/images/${encodeImagePath(img.name)}`;
                  }}
                />
              </div>

              <div style={{ padding: '0.75rem 1rem' }}>
                <div style={{
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  fontWeight: 500,
                  fontSize: '0.9rem'
                }} title={img.name}>
                  {img.name}
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                  {img.date_added ? new Date(img.date_added).toLocaleDateString() : 'Unknown date'}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Image detail modal */}
      {selectedImage && (
        <div style={overlayStyle} onClick={closeModal}>
          <div style={modalStyle} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
              <h2 style={{ margin: 0, fontSize: '1.2rem' }}>Photo Details</h2>
              <button
                onClick={closeModal}
                aria-label="Close"
                style={{ background: 'none', border: 'none', padding: '4px', display: 'flex', color: 'var(--text-secondary)' }}
              >
                <X size={20} />
              </button>
            </div>

            <img
              src={`/api/images/thumb/${encodeImagePath(selectedImage.name)}?w=600`}
              alt={selectedImage.name}
              style={{ width: '100%', borderRadius: '8px', marginBottom: '1.5rem', maxHeight: '280px', objectFit: 'contain', background: '#000' }}
              onError={e => { e.target.src = `/api/images/${encodeImagePath(selectedImage.name)}`; }}
            />

            {metaLoading ? (
              <div style={{ display: 'flex', justifyContent: 'center', padding: '1.5rem' }}>
                <Loader2 size={24} className="spin" />
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                  <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>Filename</span>
                  <input
                    value={editState.filename}
                    onChange={e => setEditState(s => ({ ...s, filename: e.target.value }))}
                    disabled={!metaHash}
                  />
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                  <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>Uploader</span>
                  <input
                    value={editState.uploader}
                    onChange={e => setEditState(s => ({ ...s, uploader: e.target.value }))}
                    disabled={!metaHash}
                    placeholder="Who uploaded this?"
                  />
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                  <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>Location</span>
                  <input
                    value={editState.location}
                    onChange={e => setEditState(s => ({ ...s, location: e.target.value }))}
                    disabled={!metaHash}
                    placeholder="Where was this taken?"
                  />
                </label>

                {saveError && (
                  <p style={{ color: 'var(--danger)', fontSize: '0.85rem', margin: 0 }}>{saveError}</p>
                )}
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1.5rem', gap: '0.75rem' }}>
              <button
                className="danger"
                onClick={() => handleDelete(selectedImage.name)}
                style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}
              >
                <Trash2 size={15} /> Delete
              </button>
              <div style={{ display: 'flex', gap: '0.75rem' }}>
                <button onClick={closeModal}>Cancel</button>
                <button
                  className="primary"
                  onClick={handleSave}
                  disabled={saving || !metaHash || metaLoading}
                >
                  {saving ? <Loader2 size={15} className="spin" style={{ display: 'inline' }} /> : 'Save'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <style>{`
        .spin { animation: spin 1s linear infinite; }
        @keyframes spin { 100% { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
