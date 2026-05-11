import { useState, useEffect } from 'react';
import axios from 'axios';
import { Upload, Trash2, Image as ImageIcon, Loader2 } from 'lucide-react';

export default function GalleryView() {
  const [images, setImages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  const fetchImages = async () => {
    try {
      const res = await axios.get('/api/images');
      setImages(res.data);
    } catch (err) {
      console.error('Failed to fetch images', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchImages();
  }, []);

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
        alert(`Upload finished with ${errorCount} batch error(s). Some photos may not have been saved.`);
      }
    } finally {
      setUploading(false);
      setUploadProgress(0);
      e.target.value = '';
    }
  };

  const handleDelete = async (filename) => {
    if (!window.confirm(`Are you sure you want to delete ${filename}?`)) return;
    
    try {
      await axios.delete(`/api/images/${encodeURIComponent(filename)}`);
      setImages(images.filter(img => img.name !== filename));
    } catch (err) {
      console.error('Delete failed', err);
      alert('Delete failed');
    }
  };

  return (
    <div style={{ padding: '2rem', maxWidth: '1400px', margin: '0 auto' }}>
      <header style={{ marginBottom: '2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '2rem', fontWeight: 600 }}>Gallery</h1>
          <p style={{ margin: '0.5rem 0 0', color: 'var(--text-muted)' }}>Manage {images.length} photos on your frame</p>
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

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '4rem', color: 'var(--text-muted)' }}>
          <Loader2 size={32} className="spin" />
        </div>
      ) : images.length === 0 ? (
        <div className="glass-panel fade-in" style={{ padding: '4rem 2rem', textAlign: 'center' }}>
          <ImageIcon size={48} color="var(--text-muted)" style={{ marginBottom: '1rem', opacity: 0.5 }} />
          <h3>No Photos Found</h3>
          <p style={{ color: 'var(--text-muted)' }}>Upload some photos to see them here.</p>
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
                animationDelay: `${idx * 0.05}s`
              }}
            >
              <div style={{ aspectRatio: '4/3', backgroundColor: '#000', position: 'relative' }}>
                <img 
                  src={`/api/images/thumb/${encodeURIComponent(img.name)}?w=400`} 
                  alt={img.name}
                  loading="lazy"
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  onError={(e) => {
                    // Fallback to full image if thumb fails
                    e.target.src = `/api/images/${encodeURIComponent(img.name)}`;
                  }}
                />
                
                {/* Overlay actions */}
                <div 
                  className="image-actions"
                  style={{
                    position: 'absolute',
                    top: 0, left: 0, right: 0, bottom: 0,
                    background: 'rgba(0,0,0,0.5)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    opacity: 0,
                    transition: 'opacity 0.2s ease',
                  }}
                >
                  <button 
                    className="danger"
                    onClick={() => handleDelete(img.name)}
                    style={{ padding: '0.5rem', borderRadius: '50%', display: 'flex' }}
                    title="Delete Image"
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
              </div>
              
              <div style={{ padding: '1rem' }}>
                <div style={{ 
                  whiteSpace: 'nowrap', 
                  overflow: 'hidden', 
                  textOverflow: 'ellipsis',
                  fontWeight: 500,
                  fontSize: '0.95rem'
                }} title={img.name}>
                  {img.name}
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                  {img.date_added ? new Date(img.date_added).toLocaleDateString() : 'Unknown date'}
                </div>
              </div>

              {/* Add hover style via inline JS since we can't easily do it in pure inline style without styled-components */}
              <style>{`
                .glass-panel:hover .image-actions { opacity: 1 !important; }
                .spin { animation: spin 1s linear infinite; }
                @keyframes spin { 100% { transform: rotate(360deg); } }
              `}</style>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
